"""
Claude Code provider — full support.

Data sources:
  - Prompt index: ~/.claude/history.jsonl
  - Full transcripts: ~/.claude/projects/*/*.jsonl
"""

import json
import re
import glob
from pathlib import Path

from .base import (
    CLAUDE_DIR, cutoff_ms, make_prompt_record, distinctive_term,
)


def load_prompts(days=None, project=None):
    """Load prompt index from Claude Code history.jsonl."""
    history = CLAUDE_DIR / "history.jsonl"
    if not history.exists():
        return []
    cutoff = cutoff_ms(days)
    records = []
    with open(history, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                ts = obj.get("timestamp", 0)
                if ts < cutoff:
                    continue
                text = obj.get("display", "").strip()
                if not text:
                    continue
                proj = obj.get("project", "")
                if project and project not in proj:
                    continue
                records.append(make_prompt_record(
                    "claude-code", "Claude Code", text, ts,
                    proj.split("/")[-1] if proj else "unknown",
                    obj.get("sessionId", ""),
                    metadata={"project_path": proj},
                ))
            except Exception:
                continue
    return records


def discover():
    """Detect Claude Code data source."""
    h = CLAUDE_DIR / "history.jsonl"
    if not h.exists():
        return None
    with open(h) as f:
        prompt_count = sum(1 for _ in f)
    transcript_count = len(glob.glob(str(CLAUDE_DIR / "projects/**/*.jsonl"), recursive=True))
    return {
        "source_id": "claude-code",
        "status": "full",
        "prompt_index": str(h),
        "prompt_count": prompt_count,
        "transcript_count": transcript_count,
        "context": "full_transcript",
    }


def extract_model(sid, metadata):
    """Extract model from Claude Code session JSONL."""
    tp = metadata.get("project_path", "")
    if not tp:
        return None
    sid_short = sid[:8]
    projects_dir = CLAUDE_DIR / "projects"
    if not projects_dir.exists():
        return None
    for jsonl_file in projects_dir.rglob("*.jsonl"):
        if sid_short in jsonl_file.name and "audit" not in str(jsonl_file):
            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            if obj.get("type") == "assistant":
                                model = obj.get("message", {}).get("model", "")
                                if model:
                                    return model
                        except (json.JSONDecodeError, KeyError):
                            continue
            except OSError:
                pass
            break
    return None


def extract_context(session_id, target_prompt_text, radius=4,
                    result_after=1, result_cap=600, max_results=4):
    """
    Stage 2: Read ±radius turns of conversation context around an incident.

    A session_id from history.jsonl is not a reliable key to the transcript
    file (worktrees / resume / pasted text decouple them), so the file is
    located primarily by the prompt text, with session_id only as a tie-break.

    Assistant turns leading up to the correction (through result_after turns
    past it) keep their key tool inputs, and up to max_results tool results are
    included (each truncated to result_cap chars, nearest-to-target first). This
    lets the LLM see what the AI actually did — the diff it wrote, the output it
    got — not only which tool it called. Outer turns stay light to bound tokens.
    """
    claude_dir = CLAUDE_DIR / "projects"
    import subprocess

    def _grep_files(term, fixed=False):
        if not term:
            return []
        try:
            cmd = ["grep", "-rl"] + (["-F"] if fixed else []) + ["-e", term, str(claude_dir)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except Exception:
            return []
        return [f for f in r.stdout.strip().split("\n")
                if f.strip() and f.endswith(".jsonl")
                and "audit" not in f and "history" not in f
                and "agent-" not in f.split("/")[-1]]

    term = distinctive_term(target_prompt_text)
    sid_files = _grep_files(session_id)
    text_files = _grep_files(term, fixed=True) if term else []

    # session_id files first (the normal, least-ambiguous key); prompt-text
    # files only as a fallback for cases where the id is decoupled from the
    # transcript (worktree / resume). Text-first would pull in unrelated files
    # that merely quote the prompt (e.g. this tool's own reports).
    sid_set = set(sid_files)
    seen = set()
    ordered = []
    for f in sid_files + text_files:
        if f not in seen:
            seen.add(f)
            ordered.append(f)
    if not ordered:
        return {"error": "session_file_not_found", "session_id": session_id}

    sid_short = session_id[:8]
    ordered.sort(key=lambda f: (
        0 if sid_short in f.split("/")[-1] else 1,   # filename == session_id wins
        0 if f in sid_set else 1,                    # then files referencing the sid
    ))

    def _fmt_tool(name, inp):
        """Compact but meaningful tool descriptor (used only for near-target turns)."""
        if name == "Read":
            return f"Read({str(inp.get('file_path','')).split('/')[-1]})"
        if name in ("Edit", "Write"):
            fp = str(inp.get("file_path", "")).split("/")[-1]
            snippet = inp.get("new_string") or inp.get("content") or ""
            snippet = re.sub(r"\s+", " ", str(snippet)).strip()[:160]
            return f"{name}({fp})" + (f': "{snippet}"' if snippet else "")
        if name == "Bash":
            return f"Bash({str(inp.get('command',''))[:160]})"
        return name

    def _parse(filepath):
        """Parse one transcript file into structured user/assistant turns.

        No sessionId equality filter: the file was chosen because it contains
        the target text, and the turn is located by text below, so the file's
        internal sessionId is irrelevant.
        """
        msgs = []
        try:
            fh = open(filepath, "r", encoding="utf-8")
        except Exception:
            return msgs
        with fh as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                t = obj.get("type")

                if t == "user":
                    msg = obj.get("message", {})
                    c = msg.get("content", "")
                    text = ""
                    tool_results = []
                    if isinstance(c, list):
                        for b in c:
                            if not isinstance(b, dict):
                                continue
                            if b.get("type") == "text" and not text:
                                text = b.get("text", "")[:500]
                            elif b.get("type") == "tool_result":
                                rc = b.get("content", "")
                                if isinstance(rc, list):
                                    rc = " ".join(
                                        bb.get("text", "") for bb in rc
                                        if isinstance(bb, dict) and bb.get("type") == "text"
                                    )
                                rc = re.sub(r"\s+", " ", str(rc)).strip()
                                if rc:
                                    tool_results.append(rc[:result_cap])
                    elif isinstance(c, str):
                        text = c[:500]
                    text = text.strip()
                    if text and not text.startswith("<local-command") and not text.startswith("<command-name"):
                        msgs.append({"role": "user", "text": text, "tools": [], "results": []})
                    elif tool_results and msgs and msgs[-1]["role"] == "assistant":
                        msgs[-1]["results"].extend(tool_results)

                elif t == "assistant":
                    msg = obj.get("message", {})
                    content = msg.get("content", [])
                    text_parts = []
                    tools = []
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict):
                                if b.get("type") == "text":
                                    txt = b.get("text", "")[:300]
                                    if txt.strip():
                                        text_parts.append(txt.strip())
                                elif b.get("type") == "tool_use":
                                    tools.append((b.get("name", "?"), b.get("input", {})))
                    if text_parts or tools:
                        msgs.append({
                            "role": "assistant",
                            "text": text_parts[0][:300] if text_parts else "",
                            "tools": tools,
                            "results": [],
                        })
        return msgs

    target_short = target_prompt_text[:40]

    def _locate_exact(msgs):
        if not target_short:
            return None
        for i, m in enumerate(msgs):
            if m["role"] == "user" and target_short in m["text"]:
                return i
        return None

    # Try candidates until one actually contains the target prompt as a user turn.
    msgs = []
    target_idx = None
    for filepath in ordered[:5]:
        cand = _parse(filepath)
        if not cand:
            continue
        idx = _locate_exact(cand)
        if idx is not None:
            msgs, target_idx = cand, idx
            break
        if not msgs:
            msgs = cand  # keep first non-empty parse for fuzzy fallback

    if not msgs:
        return {"error": "no_messages_parsed", "session_id": session_id}

    # Fuzzy fallback when no exact text match (e.g. placeholder/reformatted prompt).
    if target_idx is None:
        import difflib
        best_ratio = 0
        for i, m in enumerate(msgs):
            if m["role"] == "user":
                ratio = difflib.SequenceMatcher(None, target_short, m["text"][:40]).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    target_idx = i

    if target_idx is None:
        return {"error": "target_not_found", "session_id": session_id}

    # The assistant tool activity leading up to the correction is where the
    # failure happened, so enrich those turns (through result_after past the
    # target) with full tool inputs, and attach up to max_results tool results
    # (nearest-to-target first) to bound tokens.
    start = max(0, target_idx - radius)
    end = min(len(msgs), target_idx + radius + 1)

    enrich_candidates = [
        i for i in range(start, end)
        if msgs[i]["role"] == "assistant" and msgs[i]["results"]
        and (i - target_idx) <= result_after
    ]
    enrich_candidates.sort(key=lambda i: abs(i - target_idx))
    enrich_set = set(enrich_candidates[:max_results])

    context_msgs = []
    for i in range(start, end):
        m = msgs[i]
        pos = i - target_idx

        content = m["text"]
        if m["role"] == "assistant" and m["tools"]:
            if -radius <= pos <= result_after:
                tool_str = " → ".join(_fmt_tool(n, inp) for n, inp in m["tools"][:5])
            else:
                tool_str = " → ".join(n for n, _ in m["tools"][:5])
            content = (content + " | " if content else "") + tool_str

        entry = {
            "role": m["role"],
            "content": content,
            "is_target": i == target_idx,
            "position": pos,
        }
        if i in enrich_set and m["results"]:
            entry["tool_results"] = m["results"][:2]
        context_msgs.append(entry)

    return {
        "session_id": session_id,
        "source_id": "claude-code",
        "total_messages": len(msgs),
        "target_index": target_idx,
        "context_radius": radius,
        "context": context_msgs,
    }

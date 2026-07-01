"""
Claude Code provider — full support.

Data sources:
  - Prompt index: ~/.claude/history.jsonl
  - Full transcripts: ~/.claude/projects/*/*.jsonl
"""

import json
import glob
import subprocess
from pathlib import Path

from .base import (
    CLAUDE_DIR, cutoff_ms, make_prompt_record, iter_jsonl, text_from_blocks,
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
            except:
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


def extract_context(session_id, target_prompt_text, radius=4):
    """
    Layer 2: Read ±radius turns of full conversation context around an incident.
    Returns structured context snippet.
    """
    claude_dir = CLAUDE_DIR / "projects"

    # Use grep to quickly locate file
    try:
        result = subprocess.run(
            ["grep", "-rl", session_id, str(claude_dir)],
            capture_output=True, text=True, timeout=15
        )
        files = [f for f in result.stdout.strip().split("\n")
                 if f.strip() and "audit" not in f and "history" not in f
                 and "agent-" not in f.split("/")[-1]]
    except:
        files = []

    if not files:
        return {"error": "session_file_not_found", "session_id": session_id}

    # Prefer files whose name contains the session ID
    sid_short = session_id[:8]
    files.sort(key=lambda f: (0 if sid_short in f.split("/")[-1] else 1))

    # Parse conversation
    msgs = []
    for filepath in files[:1]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        obj_sid = obj.get("sessionId", "")
                        if obj_sid and not session_id.startswith(obj_sid) and not obj_sid.startswith(session_id[:20]):
                            continue
                        t = obj.get("type")

                        if t == "user":
                            msg = obj.get("message", {})
                            c = msg.get("content", "")
                            text = ""
                            if isinstance(c, list):
                                for b in c:
                                    if isinstance(b, dict) and b.get("type") == "text":
                                        text = b.get("text", "")[:500]
                                        break
                            elif isinstance(c, str):
                                text = c[:500]
                            text = text.strip()
                            if text and not text.startswith("<local-command") and not text.startswith("<command-name"):
                                msgs.append({"role": "user", "content": text})

                        elif t == "assistant":
                            msg = obj.get("message", {})
                            content = msg.get("content", [])
                            text_parts = []
                            tool_parts = []
                            if isinstance(content, list):
                                for b in content:
                                    if isinstance(b, dict):
                                        if b.get("type") == "text":
                                            txt = b.get("text", "")[:300]
                                            if txt.strip():
                                                text_parts.append(txt.strip())
                                        elif b.get("type") == "tool_use":
                                            n = b.get("name", "?")
                                            inp = b.get("input", {})
                                            if n in ("Read", "Edit", "Write"):
                                                fp = str(inp.get("file_path", "")).split("/")[-1]
                                                tool_parts.append(f"{n}({fp})")
                                            elif n == "Bash":
                                                tool_parts.append(f"Bash({str(inp.get('command',''))[:40]})")
                                            else:
                                                tool_parts.append(n)
                            summary = ""
                            if text_parts:
                                summary = text_parts[0][:300]
                            if tool_parts:
                                summary += (" | " if summary else "") + " → ".join(tool_parts[:4])
                            if summary:
                                msgs.append({"role": "assistant", "content": summary})
                    except:
                        continue
        except:
            continue

    if not msgs:
        return {"error": "no_messages_parsed", "session_id": session_id}

    # Find target prompt
    target_idx = None
    target_short = target_prompt_text[:40]
    for i, m in enumerate(msgs):
        if m["role"] == "user" and target_short in m["content"]:
            target_idx = i
            break

    if target_idx is None:
        # fallback: find closest match
        import difflib
        best_ratio = 0
        for i, m in enumerate(msgs):
            if m["role"] == "user":
                ratio = difflib.SequenceMatcher(None, target_short, m["content"][:40]).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    target_idx = i

    if target_idx is None:
        return {"error": "target_not_found", "session_id": session_id}

    # Extract context
    start = max(0, target_idx - radius)
    end = min(len(msgs), target_idx + radius + 1)

    context_msgs = []
    for i in range(start, end):
        m = msgs[i]
        context_msgs.append({
            "role": m["role"],
            "content": m["content"],
            "is_target": i == target_idx,
            "position": i - target_idx,
        })

    return {
        "session_id": session_id,
        "source_id": "claude-code",
        "total_messages": len(msgs),
        "target_index": target_idx,
        "context_radius": radius,
        "context": context_msgs,
    }

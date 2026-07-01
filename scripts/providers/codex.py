"""
Codex (OpenAI CLI) provider — full support.

Data sources:
  - Prompt index: ~/.codex/history.jsonl
  - Full transcripts: ~/.codex/sessions/**/*.jsonl (rollout files)
  - Thread metadata: ~/.codex/sqlite/state_5.sqlite
"""

import json
import glob
from pathlib import Path

from .base import (
    CODEX_DIR, cutoff_ms, coerce_ts_ms, make_prompt_record,
    iter_jsonl, text_from_blocks, sqlite_fetch,
)


def _load_thread_index():
    """Read Codex thread metadata to correlate history prompts with cwd/title/rollout."""
    index = {}
    for db in [CODEX_DIR / "sqlite/state_5.sqlite", CODEX_DIR / "state_5.sqlite"]:
        rows = sqlite_fetch(
            db,
            "select id, cwd, title, rollout_path from threads"
        )
        for sid, cwd, title, rollout_path in rows:
            index[sid] = {
                "cwd": cwd or "",
                "title": title or "",
                "rollout_path": rollout_path or "",
            }
    return index


def _find_rollout(session_id, thread_index=None):
    if thread_index and session_id in thread_index:
        p = Path(thread_index[session_id].get("rollout_path") or "")
        if p.exists():
            return str(p)
    patterns = [
        str(CODEX_DIR / f"sessions/**/rollout-*{session_id}.jsonl"),
        str(CODEX_DIR / f"archived_sessions/rollout-*{session_id}.jsonl"),
    ]
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return ""


def load_prompts(days=None, project=None):
    """Load Codex history.jsonl. Full context located via rollout_path."""
    history = CODEX_DIR / "history.jsonl"
    if not history.exists():
        return []
    cutoff = cutoff_ms(days)
    thread_index = _load_thread_index()
    records = []
    for obj in iter_jsonl(history):
        ts = coerce_ts_ms(obj.get("ts"))
        if ts < cutoff:
            continue
        text = (obj.get("text") or "").strip()
        if not text:
            continue
        sid = obj.get("session_id", "")
        meta = thread_index.get(sid, {})
        cwd = meta.get("cwd", "")
        title = meta.get("title", "")
        if project and project not in cwd and project not in title:
            continue
        project_name = Path(cwd).name if cwd else (title[:40] if title else "unknown")
        records.append(make_prompt_record(
            "codex", "Codex", text, ts, project_name, sid,
            transcript_path=_find_rollout(sid, thread_index),
            metadata={"cwd": cwd, "title": title},
        ))
    return records


def discover():
    """Detect Codex data source."""
    ch = CODEX_DIR / "history.jsonl"
    if not ch.exists():
        return None
    with open(ch) as f:
        prompt_count = sum(1 for _ in f)
    transcript_count = (
        len(glob.glob(str(CODEX_DIR / "sessions/**/*.jsonl"), recursive=True)) +
        len(glob.glob(str(CODEX_DIR / "archived_sessions/*.jsonl")))
    )
    return {
        "source_id": "codex",
        "status": "full" if transcript_count else "prompt_index",
        "prompt_index": str(ch),
        "prompt_count": prompt_count,
        "transcript_count": transcript_count,
        "context": "full_transcript_when_rollout_exists",
    }


def extract_context(session_id, target_prompt_text, radius=4):
    """Layer 2: Read ±radius turns from Codex rollout file."""
    thread_index = _load_thread_index()
    path = _find_rollout(session_id, thread_index)
    msgs = []

    if path:
        for obj in iter_jsonl(path):
            t = obj.get("type")
            payload = obj.get("payload", {})
            if t == "event_msg" and payload.get("type") == "user_message":
                text = payload.get("message", "")
                if text:
                    msgs.append({"role": "user", "content": text[:500]})
                continue
            if t != "response_item":
                continue
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            text = text_from_blocks(payload.get("content", []))
            if text and not text.startswith("# AGENTS.md instructions"):
                msgs.append({"role": role, "content": text[:500]})

    if not msgs:
        # fallback: Codex history has user prompts only
        history = CODEX_DIR / "history.jsonl"
        for obj in iter_jsonl(history):
            if obj.get("session_id") == session_id:
                text = obj.get("text", "")
                if text:
                    msgs.append({"role": "user", "content": text[:500]})

    if not msgs:
        return {"error": "codex_context_not_found", "session_id": session_id, "source_id": "codex"}

    target_idx = None
    target_short = target_prompt_text[:40]
    for i, m in enumerate(msgs):
        if m["role"] == "user" and target_short in m["content"]:
            target_idx = i
            break

    if target_idx is None:
        import difflib
        best_ratio = 0
        for i, m in enumerate(msgs):
            if m["role"] != "user":
                continue
            ratio = difflib.SequenceMatcher(None, target_short, m["content"][:40]).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                target_idx = i

    if target_idx is None:
        return {"error": "target_not_found", "session_id": session_id, "source_id": "codex"}

    start = max(0, target_idx - radius)
    end = min(len(msgs), target_idx + radius + 1)
    return {
        "session_id": session_id,
        "source_id": "codex",
        "transcript_path": path,
        "total_messages": len(msgs),
        "target_index": target_idx,
        "context_radius": radius,
        "context": [
            {**msgs[i], "is_target": i == target_idx, "position": i - target_idx}
            for i in range(start, end)
        ],
    }

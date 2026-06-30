#!/usr/bin/env python3
"""
AI Interaction Analyzer — Lightweight session analysis (SessionEnd hook)

Design constraints:
- Complete within 3s timeout
- Async execution, non-blocking
- Append one JSON line to session-log.jsonl
- Zero external dependencies
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"

OUTPUT_DIR = Path.home() / ".ai-interaction-analyzer"
SESSION_LOG = OUTPUT_DIR / "session-log.jsonl"

SLASH_CMD_PATTERN = re.compile(r"^/\w+")
NEGATION_PATTERNS = re.compile(
    r"不对|不是|重[来做]|改[一下]|错了|换[一个种]|别这样|不要这[样么个]|重新"
    r"|wrong|incorrect|undo|revert|redo|not right|start over"
)


def get_current_session_id():
    """Get current session ID from env or recent history."""
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid

    if not HISTORY_FILE.exists():
        return None

    last_lines = []
    with open(HISTORY_FILE, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        lines_found = 0
        while pos > 0 and lines_found < 20:
            pos -= 1
            f.seek(pos)
            if f.read(1) == b"\n":
                lines_found += 1
        last_lines = f.read().decode("utf-8", errors="ignore").strip().split("\n")

    for line in reversed(last_lines):
        try:
            obj = json.loads(line)
            if obj.get("sessionId"):
                return obj["sessionId"]
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def analyze_session(session_id):
    """Analyze prompt data for the given session."""
    if not HISTORY_FILE.exists():
        return None

    session_prompts = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                if obj.get("sessionId") == session_id:
                    session_prompts.append(obj)
            except (json.JSONDecodeError, KeyError):
                continue

    if not session_prompts:
        return None

    real_prompts = [p for p in session_prompts if not SLASH_CMD_PATTERN.match(p.get("display", "").strip())]
    turns = len(session_prompts)
    negation_count = sum(1 for p in session_prompts if NEGATION_PATTERNS.search(p.get("display", "")))
    first_shot = turns <= 3 and negation_count == 0

    avg_length = 0
    if real_prompts:
        avg_length = sum(len(p.get("display", "")) for p in real_prompts) // len(real_prompts)

    anti_pattern_count = 0
    if negation_count >= 2:
        anti_pattern_count += 1
    short_count = sum(1 for p in real_prompts if len(p.get("display", "")) < 10)
    if short_count >= 3:
        anti_pattern_count += 1
    if turns > 50:
        anti_pattern_count += 1

    project = session_prompts[0].get("project", "unknown").split("/")[-1] if session_prompts else "unknown"

    return {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "project": project,
        "turns": turns,
        "real_prompts": len(real_prompts),
        "avg_prompt_length": avg_length,
        "negation_count": negation_count,
        "first_shot": first_shot,
        "anti_pattern_count": anti_pattern_count,
    }


def main():
    session_id = get_current_session_id()
    if not session_id:
        sys.exit(0)

    result = analyze_session(session_id)
    if not result:
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(SESSION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

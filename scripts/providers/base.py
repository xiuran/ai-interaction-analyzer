"""
Shared utilities for all providers.
"""

import os
import sys
import json
import glob
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# ─── Directories ──────────────────────────────────────────────

CLAUDE_DIR = Path.home() / ".claude"
CODEX_DIR = Path.home() / ".codex"
QODER_DIR = Path.home() / ".qoder"   # full plaintext JSONL transcripts live here
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = SKILL_DIR / "config"
USER_CONFIG_DIR = Path.home() / ".config" / "ai-interaction-analyzer"


def _app_data_dirs(app_name):
    """Platform-specific application data directories for a given app."""
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library/Application Support" / app_name]
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", str(home / "AppData/Roaming"))
        localappdata = os.environ.get("LOCALAPPDATA", str(home / "AppData/Local"))
        return [Path(appdata) / app_name, Path(localappdata) / app_name]
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
        return [Path(xdg) / app_name]


CURSOR_DATA_DIRS = _app_data_dirs("Cursor")
QODER_APP_DIRS = _app_data_dirs("Qoder")


# ─── Custom config ────────────────────────────────────────────

def load_custom_config():
    for d in [USER_CONFIG_DIR, CONFIG_DIR]:
        f = d / "custom_patterns.json"
        if f.exists():
            try:
                return json.load(open(f, encoding="utf-8"))
            except Exception:
                pass
    return {}


CUSTOM = load_custom_config()


# ─── Timestamp helpers ────────────────────────────────────────

def coerce_ts_ms(value):
    """Normalize seconds/ms/ISO timestamps to epoch milliseconds."""
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value if value > 10_000_000_000 else value * 1000)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0
        if re.fullmatch(r"\d+(\.\d+)?", s):
            return coerce_ts_ms(float(s))
        try:
            return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return 0
    return 0


def iso_from_ms(ts_ms):
    if not ts_ms:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000).isoformat()


def cutoff_ms(days):
    return int((datetime.now() - timedelta(days=days)).timestamp() * 1000) if days else 0


# ─── Record builders ─────────────────────────────────────────

def make_prompt_record(source_id, source_name, text, timestamp_ms=0, project="unknown",
                       session_id="", message_id="", transcript_path="", metadata=None):
    return {
        "source_id": source_id,
        "source": source_name,
        "text": (text or "").strip(),
        "timestamp_ms": int(timestamp_ms or 0),
        "timestamp": iso_from_ms(timestamp_ms),
        "project": project or "unknown",
        "session_id": session_id or "",
        "message_id": message_id or "",
        "transcript_path": transcript_path or "",
        "metadata": metadata or {},
    }


# ─── File I/O helpers ────────────────────────────────────────

def iter_jsonl(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def sqlite_fetch(path, sql, params=()):
    if not Path(path).exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return list(conn.execute(sql, params))
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def text_from_blocks(content):
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            txt = block.get("text") or block.get("input_text") or block.get("output_text")
            if txt:
                parts.append(str(txt))
    return "\n".join(parts)


def parse_sources(value):
    if not value:
        return None
    return {x.strip().lower() for x in value.split(",") if x.strip()}


def distinctive_term(text):
    """A grep-safe, single-line slice of a prompt used to locate it in a
    transcript. Empty for placeholder prompts (pasted text / images / tags),
    which cannot be matched against transcript content."""
    t = (text or "").strip()
    if not t or t.startswith("[Pasted") or t.startswith("[Image") or t.startswith("<"):
        return ""
    first_line = t.splitlines()[0].strip()
    term = first_line if len(first_line) >= 6 else t
    return term[:40]


# ─── Generic JSON user message extractor ─────────────────────

def extract_json_user_messages(obj, inherited_session="", source_hint=""):
    """Best-effort extractor for Cursor/Cline/Roo/Gemini/ChatGPT export-like JSON."""
    found = []

    def text_value(value):
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return text_from_blocks(value)
        if isinstance(value, dict):
            for key in ("text", "content", "message", "prompt", "query"):
                if isinstance(value.get(key), str):
                    return value[key]
        return ""

    def walk(node, session_id):
        if isinstance(node, dict):
            sid = str(node.get("sessionId") or node.get("session_id") or node.get("conversation_id")
                      or node.get("composerId") or node.get("id") or session_id or inherited_session)
            role = str(node.get("role") or node.get("author") or node.get("sender") or "").lower()
            if role in ("user", "human"):
                text = text_value(node.get("content") or node.get("text") or node.get("message") or node)
                ts = coerce_ts_ms(node.get("timestamp") or node.get("createdAt") or node.get("create_time"))
                if text and len(text.strip()) > 1:
                    found.append((sid, text.strip(), ts))
            for value in node.values():
                walk(value, sid)
        elif isinstance(node, list):
            for item in node:
                walk(item, session_id)

    walk(obj, inherited_session)
    dedup = []
    seen = set()
    for sid, text, ts in found:
        key = (sid, text[:120], ts)
        if key not in seen:
            seen.add(key)
            dedup.append((sid, text, ts))
    return dedup

#!/usr/bin/env python3
"""
AI Interaction Analyzer — Layered analysis engine

Layer 1 (lightweight): scan all prompts, extract frustration signals
  → valuable without context: what phrases does the user keep saying?
Layer 2 (targeted deep-dive): for each frustration signal, read ±4 turns
  of context from session JSONL
  → what did AI do before? why is user unhappy? did AI correct?

Outputs JSON to stdout for AI to present diagnosis in conversation.
Zero external dependencies — stdlib only.
"""

import json
import os
import re
import sys
import argparse
import glob
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

CLAUDE_DIR = Path.home() / ".claude"
CODEX_DIR = Path.home() / ".codex"
SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "config"
USER_CONFIG_DIR = Path.home() / ".config" / "ai-interaction-analyzer"

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


def parse_sources(value):
    if not value:
        return None
    return {x.strip().lower() for x in value.split(",") if x.strip()}


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
    if not path.exists():
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

# ─── Frustration signal patterns (Layer 1 core) ──────────────

FRUSTRATION_CATEGORIES = {
    "fabrication": {
        "label": {"en": "AI fabrication", "zh": "AI 编造瞎猜"},
        "pattern": re.compile(r"胡编乱造|瞎编|编的吧|瞎猜|别猜|不要猜|瞎说|乱说|胡说|你在编|你编的|捏造|杜撰|fabricat|hallucin|making.?up|made.?up|invented"),
        "meaning": "AI output false information or speculative content",
    },
    "incorrect": {
        "label": {"en": "Incorrect output", "zh": "AI 做错了"},
        "pattern": re.compile(r"不对|错了|搞错|弄错|改错|写错|放错|用错|选错|wrong|incorrect|that'?s not|not right"),
        "meaning": "AI output did not match user expectation",
    },
    "low_effort": {
        "label": {"en": "Shallow thinking", "zh": "AI 不够认真"},
        "pattern": re.compile(r"仔细[想看看看]|深度思考|认真[一点些]|用心|好好[想看]|动动脑|think.?hard|think.?deep|carefully|pay attention|more thought"),
        "meaning": "User feels AI was lazy or lacked depth",
    },
    "repeated_mistake": {
        "label": {"en": "Repeated mistakes", "zh": "AI 重复犯错"},
        "pattern": re.compile(r"又[来是错]|还是[这那]样|老是|不要老|反复|一直在|again|keep|still|same mistake|same error"),
        "meaning": "AI keeps making the same mistake",
    },
    "overreach": {
        "label": {"en": "Overreach", "zh": "越权操作"},
        "pattern": re.compile(r"谁让你|我[没没有]说|我[没没有]让|我要的是|我说的是|不是让你|别[瞎乱]改|不要[随瞎乱]便|didn'?t ask|not what I|don't change|never asked"),
        "meaning": "AI exceeded instructions or misunderstood intent",
    },
    "undo_redo": {
        "label": {"en": "Undo / redo", "zh": "撤销重来"},
        "pattern": re.compile(r"撤[销回]|回滚|重[来做写]|还原|恢复|全[部都]删|undo|revert|rollback|start over|redo|go back"),
        "meaning": "AI output needs to be completely discarded",
    },
    "distrust": {
        "label": {"en": "Distrust", "zh": "质疑/不信任"},
        "pattern": re.compile(r"你确[定认]|真的吗|靠谱吗|能[行用]吗|有[没]有问题|are you sure|really\?|is that right|does that work"),
        "meaning": "User doubts AI output accuracy",
    },
}


def classify_frustration(text):
    """Classify frustration signals. Returns [(category, matched_text)]."""
    hits = []
    for cat, info in FRUSTRATION_CATEGORIES.items():
        match = info["pattern"].search(text)
        if match:
            hits.append((cat, match.group()))
    return hits


# ─── Data loading: Provider-based ─────────────────────────────

def load_claude_prompts(days=None, project=None):
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
                if ts < cutoff: continue
                text = obj.get("display", "").strip()
                if not text: continue
                proj = obj.get("project", "")
                if project and project not in proj: continue
                records.append(make_prompt_record(
                    "claude-code", "Claude Code", text, ts,
                    proj.split("/")[-1] if proj else "unknown",
                    obj.get("sessionId", ""),
                    metadata={"project_path": proj},
                ))
            except: continue
    return records


def load_codex_thread_index():
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


def find_codex_rollout(session_id, thread_index=None):
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


def load_codex_prompts(days=None, project=None):
    """Load Codex history.jsonl. Full context located via rollout_path."""
    history = CODEX_DIR / "history.jsonl"
    if not history.exists():
        return []
    cutoff = cutoff_ms(days)
    thread_index = load_codex_thread_index()
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
            transcript_path=find_codex_rollout(sid, thread_index),
            metadata={"cwd": cwd, "title": title},
        ))
    return records


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


def load_cursor_prompts(days=None, project=None):
    """Best-effort Cursor SQLite reader. Schema varies across versions."""
    cutoff = cutoff_ms(days)
    roots = [
        Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb",
        *glob.glob(str(Path.home() / "Library/Application Support/Cursor/User/workspaceStorage/*/state.vscdb")),
    ]
    records = []
    for db in roots:
        db = Path(db)
        rows = sqlite_fetch(
            db,
            "select key, value from ItemTable where lower(key) like '%chat%' "
            "or lower(key) like '%composer%' or lower(key) like '%conversation%'"
        )
        for key, value in rows:
            try:
                obj = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                continue
            for sid, text, ts in extract_json_user_messages(obj, inherited_session=str(key), source_hint="cursor"):
                if cutoff and ts and ts < cutoff:
                    continue
                workspace = db.parent.name if db.parent.name != "globalStorage" else "global"
                if project and project not in workspace and project not in str(db):
                    continue
                records.append(make_prompt_record(
                    "cursor", "Cursor", text, ts, workspace, sid,
                    metadata={"db": str(db), "key": key},
                ))
    return records


def load_json_file_prompts(source_id, source_name, paths, days=None, project=None):
    cutoff = cutoff_ms(days)
    records = []
    for path in paths:
        path = Path(path)
        if not path.exists() or not path.is_file():
            continue
        objs = []
        if path.suffix == ".jsonl":
            objs = list(iter_jsonl(path))
        else:
            try:
                objs = [json.load(open(path, encoding="utf-8"))]
            except (OSError, json.JSONDecodeError):
                continue
        for obj in objs:
            for sid, text, ts in extract_json_user_messages(obj, inherited_session=path.parent.name, source_hint=source_id):
                if cutoff and ts and ts < cutoff:
                    continue
                proj = path.parent.name
                if project and project not in proj and project not in str(path):
                    continue
                records.append(make_prompt_record(
                    source_id, source_name, text, ts, proj, sid,
                    transcript_path=str(path),
                    metadata={"path": str(path)},
                ))
    return records


def load_cline_roo_prompts(days=None, project=None):
    roots = [
        Path.home() / "Library/Application Support/Code/User/globalStorage",
        Path.home() / "Library/Application Support/Cursor/User/globalStorage",
        Path.home() / ".vscode/extensions",
    ]
    files = []
    for root in roots:
        if root.exists():
            files.extend(root.rglob("ui_messages.json"))
            files.extend(root.rglob("api_conversation_history.json"))
    return load_json_file_prompts("cline-roo", "Cline/Roo Code", files, days, project)


def load_gemini_prompts(days=None, project=None):
    root = Path.home() / ".gemini"
    files = []
    if root.exists():
        files.extend(root.rglob("*.json"))
        files.extend(root.rglob("*.jsonl"))
    return load_json_file_prompts("gemini", "Gemini CLI", files[:200], days, project)


def load_chatgpt_export_prompts(days=None, project=None):
    candidates = [
        Path.home() / "Downloads/conversations.json",
        Path.home() / "Downloads/chatgpt-export/conversations.json",
        Path.home() / "chatgpt-export/conversations.json",
    ]
    candidates.extend(Path.home().glob("Downloads/**/conversations.json"))
    return load_json_file_prompts("chatgpt-export", "ChatGPT Export", candidates[:50], days, project)


def load_prompts(days=None, project=None, sources=None):
    """Load prompt index from all supported providers."""
    selected = parse_sources(sources) if isinstance(sources, str) else sources
    loaders = [
        ("claude-code", load_claude_prompts),
        ("codex", load_codex_prompts),
        ("cursor", load_cursor_prompts),
        ("cline-roo", load_cline_roo_prompts),
        ("gemini", load_gemini_prompts),
        ("chatgpt-export", load_chatgpt_export_prompts),
    ]
    records = []
    for source_id, loader in loaders:
        if selected and source_id not in selected:
            continue
        records.extend(loader(days=days, project=project))
    records = [r for r in records if r.get("text")]
    records.sort(key=lambda r: r.get("timestamp_ms") or 0)
    return records


def find_session_file(session_id):
    """Find the JSONL file containing this session."""
    project_dir = CLAUDE_DIR / "projects"
    if not project_dir.exists():
        return None

    sid_short = session_id[:8]
    filename_matches = []
    for jsonl_file in project_dir.rglob("*.jsonl"):
        if "audit" in str(jsonl_file) or "history" in jsonl_file.name:
            continue
        if session_id in jsonl_file.name or sid_short in jsonl_file.name:
            filename_matches.append(jsonl_file)
    if filename_matches:
        filename_matches.sort(key=lambda p: len(str(p)))
        return filename_matches[0]

    for jsonl_file in CLAUDE_DIR.joinpath("projects").rglob("*.jsonl"):
        if "audit" in str(jsonl_file) or "history" in jsonl_file.name:
            continue
        try:
            with open(jsonl_file) as f:
                for line in f:
                    if session_id in line:
                        return jsonl_file
        except: continue
    return None


def extract_context_by_turn(session_file, session_id, target_turn):
    """
    Layer 2: Read session JSONL and extract context around target_turn.
    Returns {ai_before, user_complaint, ai_after}.
    """
    if not session_file:
        return None

    messages = []  # (type, content_summary, turn_number)
    user_turn = 0

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line.strip())
                    if obj.get("sessionId") and obj.get("sessionId") != session_id:
                        continue
                    t = obj.get("type")

                    if t == "user":
                        user_turn += 1
                        msg = obj.get("message", {})
                        content = msg.get("content", "")
                        text = ""
                        if isinstance(content, list):
                            for b in content:
                                if isinstance(b, dict) and b.get("type") == "text":
                                    text = b.get("text", "")[:300]
                                    break
                        elif isinstance(content, str):
                            text = content[:300]
                        if text.strip() and not text.startswith("<"):
                            messages.append(("user", text.strip(), user_turn))

                    elif t == "assistant":
                        msg = obj.get("message", {})
                        content = msg.get("content", [])
                        summary_parts = []
                        if isinstance(content, list):
                            for b in content:
                                if isinstance(b, dict):
                                    if b.get("type") == "text":
                                        txt = b.get("text", "")[:200]
                                        if txt.strip():
                                            summary_parts.append(f"said: {txt}")
                                    elif b.get("type") == "tool_use":
                                        name = b.get("name", "?")
                                        inp = b.get("input", {})
                                        if name in ("Read", "Edit", "Write"):
                                            fp = inp.get("file_path", "?").split("/")[-1]
                                            summary_parts.append(f"{name}({fp})")
                                        elif name == "Bash":
                                            cmd = str(inp.get("command", ""))[:60]
                                            summary_parts.append(f"Bash({cmd})")
                                        else:
                                            summary_parts.append(name)
                        if summary_parts:
                            messages.append(("assistant", " → ".join(summary_parts[:3]), user_turn))
                except: continue
    except: return None

    # Find messages around target_turn
    target_idx = None
    for i, (role, text, turn) in enumerate(messages):
        if role == "user" and turn == target_turn:
            target_idx = i
            break

    if target_idx is None:
        return None

    # Last AI message before complaint
    ai_before = None
    for i in range(target_idx - 1, max(target_idx - 4, -1), -1):
        if i >= 0 and messages[i][0] == "assistant":
            ai_before = messages[i][1][:300]
            break

    # User complaint
    user_complaint = messages[target_idx][1][:300]

    # AI response after
    ai_after = None
    for i in range(target_idx + 1, min(target_idx + 4, len(messages))):
        if messages[i][0] == "assistant":
            ai_after = messages[i][1][:300]
            break

    return {
        "ai_before": ai_before,
        "user_complaint": user_complaint,
        "ai_after": ai_after,
    }


# ─── Layer 1: Frustration signal scanning ─────────────────────

def scan_frustration_signals(prompts):
    """Scan all prompts, collect frustration signals."""
    signals = []
    category_counts = Counter()

    for i, p in enumerate(prompts):
        hits = classify_frustration(p["text"])
        if hits:
            for cat, matched in hits:
                category_counts[cat] += 1
                signals.append({
                    "category": cat,
                    "matched_text": matched,
                    "full_prompt": p["text"][:200],
                    "source": p.get("source", "unknown"),
                    "source_id": p.get("source_id", "unknown"),
                    "project": p["project"],
                    "session_id": p["session_id"],
                    "timestamp": p["timestamp"],
                    "prompt_index": i,
                })

    # Dedup: keep first per session+category
    seen = set()
    deduped = []
    for s in signals:
        key = (s.get("source_id"), s["session_id"], s["category"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return deduped, dict(category_counts)


# ─── Layer 2: Targeted deep-dive ─────────────────────────────

def deep_dive_incidents(signals, max_incidents=8):
    """Targeted context analysis for frustration signals."""
    priority_order = [
        "fabrication", "incorrect", "low_effort",
        "overreach", "undo_redo", "repeated_mistake", "distrust",
    ]

    by_cat = defaultdict(list)
    for s in signals:
        by_cat[s["category"]].append(s)

    selected = []
    for cat in priority_order:
        items = by_cat.get(cat, [])
        if items and len(selected) < max_incidents:
            selected.append(items[0])
            if len(items) > 2 and len(selected) < max_incidents:
                selected.append(items[len(items)//2])

    incidents = []
    for s in selected[:max_incidents]:
        # Determine turn number
        turn = None
        prompts_in_session = []
        if s.get("source_id") == "claude-code":
            try:
                with open(CLAUDE_DIR / "history.jsonl") as f:
                    for line in f:
                        obj = json.loads(line)
                        if obj.get("sessionId") == s["session_id"]:
                            prompts_in_session.append(obj.get("display", ""))
            except: pass

        for i, text in enumerate(prompts_in_session):
            if text[:50] == s["full_prompt"][:50]:
                turn = i + 1
                break

        ctx = extract_context(s["session_id"], s["full_prompt"], radius=4, source=s.get("source_id"))
        incidents.append({
            **s,
            "turn_in_session": turn,
            "total_turns_in_session": len(prompts_in_session),
            "context": ctx,
        })

    return incidents


# ─── Helper statistics ──────────────────────────────────────

def compute_session_stats(prompts):
    """Basic session statistics."""
    sessions = defaultdict(list)
    for p in prompts:
        if p["session_id"]:
            sessions[(p.get("source_id", "unknown"), p["session_id"])].append(p)

    turns_list = [len(v) for v in sessions.values()]
    return {
        "total_sessions": len(sessions),
        "avg_turns": round(mean(turns_list), 1) if turns_list else 0,
        "max_turns": max(turns_list) if turns_list else 0,
        "turns_distribution": {
            "quick_1_5": sum(1 for t in turns_list if t <= 5),
            "medium_6_15": sum(1 for t in turns_list if 6 <= t <= 15),
            "deep_16_30": sum(1 for t in turns_list if 16 <= t <= 30),
            "marathon_30plus": sum(1 for t in turns_list if t > 30),
        },
    }


def compute_high_frequency_phrases(prompts, top_n=10):
    """Find high-frequency phrases the user repeats (CJK + English)."""
    phrase_counter = Counter()
    for p in prompts:
        text = p["text"].strip()
        if len(text) < 4 or text.startswith("/") or text.startswith("<"):
            continue
        for ph in re.findall(r'[一-鿿]{2,6}', text):
            phrase_counter[ph] += 1
        for ph in re.findall(r'\b[a-zA-Z]{3,}\s+[a-zA-Z]{3,}(?:\s+[a-zA-Z]{3,})?\b', text.lower()):
            phrase_counter[ph] += 1

    stopwords = {
        "一下", "这个", "那个", "什么", "怎么", "不要", "可以", "需要", "已经",
        "现在", "然后", "但是", "如果", "因为", "所以", "或者", "还有", "以及",
        "之前", "之后", "一个", "没有", "不是", "的话", "时候", "问题",
        "the file", "this file", "the code", "this code", "can you",
        "please help", "help me", "i want", "i need", "make sure",
        "let me", "want to", "need to", "how to", "what is",
    }
    filtered = [(ph, c) for ph, c in phrase_counter.most_common(80)
                if ph not in stopwords and c >= 3]
    return filtered[:top_n]


def discover_sources():
    """Discover available data sources."""
    sources = {}

    h = CLAUDE_DIR / "history.jsonl"
    if h.exists():
        with open(h) as f:
            prompt_count = sum(1 for _ in f)
        transcript_count = len(glob.glob(str(CLAUDE_DIR / "projects/**/*.jsonl"), recursive=True))
        sources["Claude Code"] = {
            "source_id": "claude-code",
            "status": "full",
            "prompt_index": str(h),
            "prompt_count": prompt_count,
            "transcript_count": transcript_count,
            "context": "full_transcript",
        }

    ch = CODEX_DIR / "history.jsonl"
    if ch.exists():
        with open(ch) as f:
            prompt_count = sum(1 for _ in f)
        transcript_count = (
            len(glob.glob(str(CODEX_DIR / "sessions/**/*.jsonl"), recursive=True)) +
            len(glob.glob(str(CODEX_DIR / "archived_sessions/*.jsonl")))
        )
        sources["Codex"] = {
            "source_id": "codex",
            "status": "full" if transcript_count else "prompt_index",
            "prompt_index": str(ch),
            "prompt_count": prompt_count,
            "transcript_count": transcript_count,
            "context": "full_transcript_when_rollout_exists",
        }

    cursor_dbs = glob.glob(str(Path.home() / "Library/Application Support/Cursor/User/**/state.vscdb"), recursive=True)
    if cursor_dbs or (Path.home() / ".cursor").exists():
        cursor_prompt_count = len(load_cursor_prompts(days=None))
        sources["Cursor"] = {
            "source_id": "cursor",
            "status": "best_effort" if cursor_prompt_count else "detected_metadata_only",
            "db_count": len(cursor_dbs),
            "prompt_count": cursor_prompt_count,
            "context": "sqlite_schema_varies",
        }

    cline_files = []
    for root in [
        Path.home() / "Library/Application Support/Code/User/globalStorage",
        Path.home() / "Library/Application Support/Cursor/User/globalStorage",
        Path.home() / ".vscode/extensions",
    ]:
        if root.exists():
            cline_files.extend(root.rglob("ui_messages.json"))
            cline_files.extend(root.rglob("api_conversation_history.json"))
    if cline_files or glob.glob(str(Path.home() / ".vscode/extensions/*cline*")):
        sources["Cline/Roo Code"] = {
            "source_id": "cline-roo",
            "status": "best_effort" if cline_files else "detected_no_history",
            "history_file_count": len(cline_files),
            "prompt_count": len(load_cline_roo_prompts(days=None)) if cline_files else 0,
            "context": "json_history",
        }

    if (Path.home() / ".gemini").exists():
        sources["Gemini CLI"] = {
            "source_id": "gemini",
            "status": "best_effort",
            "prompt_count": len(load_gemini_prompts(days=None)),
            "context": "json_history_if_present",
        }

    chatgpt_exports = list(Path.home().glob("Downloads/**/conversations.json"))
    if chatgpt_exports:
        sources["ChatGPT Export"] = {
            "source_id": "chatgpt-export",
            "status": "best_effort",
            "file_count": len(chatgpt_exports),
            "prompt_count": len(load_chatgpt_export_prompts(days=None)),
            "context": "export_file",
        }

    if (Path.home() / ".config/github-copilot").exists():
        sources["GitHub Copilot"] = {
            "source_id": "copilot",
            "status": "detected_config_only",
            "context": "no_stable_local_chat_parser",
        }

    for path, label in [
        (Path.home() / ".continue", "Continue"),
        (Path.home() / ".aider.chat.history.md", "Aider"),
        (Path.home() / ".local/share/opencode", "OpenCode"),
        (Path.home() / "Library/Application Support/Windsurf", "Windsurf"),
        (Path.home() / "Library/Application Support/Claude", "Claude Desktop"),
    ]:
        if path.exists():
            sources[label] = {
                "source_id": label.lower().replace(" ", "-"),
                "status": "detected_provider_todo",
                "path": str(path),
                "context": "detected_not_parsed_yet",
            }

    return sources


# ─── Main flow ────────────────────────────────────────────────

def analyze(days=30, project=None, deep=True, sources=None):
    prompts = load_prompts(days=days, project=project, sources=sources)
    if not prompts:
        return {"error": "no_conversation_data_found", "data_sources": discover_sources()}

    # Layer 1
    signals, category_counts = scan_frustration_signals(prompts)

    # Layer 2 (optional)
    incidents = []
    if deep and signals:
        incidents = deep_dive_incidents(signals, max_incidents=6)

    # Helper stats
    session_stats = compute_session_stats(prompts)
    high_freq = compute_high_frequency_phrases(prompts)

    # Count frustration signals by project
    project_frustration = Counter()
    for s in signals:
        project_frustration[s["project"]] += 1

    return {
        "period": {
            "start": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "end": datetime.now().strftime("%Y-%m-%d"),
        },
        "overview": {
            "total_prompts": len(prompts),
            "total_sessions": session_stats["total_sessions"],
            "data_sources": discover_sources(),
            "source_prompt_counts": dict(Counter(p.get("source", "unknown") for p in prompts)),
        },
        "category_labels": {k: v["label"] for k, v in FRUSTRATION_CATEGORIES.items()},
        "layer1_frustration": {
            "total_signals": len(signals),
            "category_counts": category_counts,
            "frustration_rate": round(len(signals) / max(len(prompts), 1) * 100, 1),
            "top_projects": dict(project_frustration.most_common(5)),
            "signals_sample": [
                {"category": s["category"], "prompt": s["full_prompt"][:150],
                 "source": s.get("source"), "project": s["project"], "timestamp": s["timestamp"]}
                for s in signals[:20]
            ],
        },
        "layer2_incidents": [
            {
                "category": inc["category"],
                "prompt": inc["full_prompt"][:200],
                "source": inc.get("source"),
                "project": inc["project"],
                "turn": inc.get("turn_in_session"),
                "total_turns": inc.get("total_turns_in_session"),
                "context": inc.get("context"),
            }
            for inc in incidents
        ],
        "session_stats": session_stats,
        "high_frequency_phrases": high_freq,
    }


def scope_check():
    """Stage 0: Determine analysis scope."""
    sources = discover_sources()
    counts = {}
    for label, days in [("15d", 15), ("30d", 30), ("60d", 60)]:
        prompts = load_prompts(days=days)
        counts[label] = len(prompts)

    recommended = 30
    if counts["30d"] > 500:
        recommended = 15
    elif counts["30d"] < 50:
        recommended = 60

    return {
        "data_sources": sources,
        "prompt_counts": counts,
        "source_counts_30d": dict(Counter(p.get("source", "unknown") for p in load_prompts(days=30))),
        "recommended_days": recommended,
        "reason": f"30d has {counts['30d']} prompts" + (
            ", too many — shrink to 15d" if recommended == 15 else
            ", too few — expand to 60d" if recommended == 60 else
            ", good volume"
        ),
    }


def extract_claude_context(session_id, target_prompt_text, radius=4):
    """
    Stage 2: Read ±radius turns of full conversation context around an incident.
    Returns structured context snippet.
    """
    claude_dir = CLAUDE_DIR / "projects"

    # Use grep to quickly locate file
    import subprocess
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
            "position": i - target_idx,  # -4 ~ +4
        })

    return {
        "session_id": session_id,
        "source_id": "claude-code",
        "total_messages": len(msgs),
        "target_index": target_idx,
        "context_radius": radius,
        "context": context_msgs,
    }


def extract_codex_context(session_id, target_prompt_text, radius=4):
    thread_index = load_codex_thread_index()
    path = find_codex_rollout(session_id, thread_index)
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


def extract_context(session_id, target_prompt_text, radius=4, source=None):
    source = (source or "").lower()
    if source in ("", "claude-code", "claude"):
        ctx = extract_claude_context(session_id, target_prompt_text, radius)
        if source in ("", "claude-code", "claude") and not ctx.get("error"):
            return ctx
        if source:
            return ctx
    if source in ("", "codex"):
        ctx = extract_codex_context(session_id, target_prompt_text, radius)
        if source == "codex" or not ctx.get("error"):
            return ctx
    return {
        "error": "context_not_supported_for_source",
        "source_id": source or "unknown",
        "session_id": session_id,
        "note": "This provider currently supports prompt index/signal scanning only, no stable full transcript parsing yet.",
    }


def main():
    parser = argparse.ArgumentParser(description="AI Interaction Analyzer v4")
    parser.add_argument("--mode", choices=["analyze", "setup", "signals", "scope", "context"], default="analyze")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--project", type=str, default=None)
    parser.add_argument("--source", type=str, default=None, help="comma-separated source ids, e.g. claude-code,codex")
    parser.add_argument("--session", type=str, default=None, help="session ID for context extraction")
    parser.add_argument("--prompt", type=str, default=None, help="target prompt text for context extraction")
    parser.add_argument("--radius", type=int, default=4, help="context radius (default ±4 turns)")
    parser.add_argument("--no-deep", action="store_true")
    args = parser.parse_args()

    if args.mode == "setup":
        print(json.dumps({"data_sources": discover_sources(), "python": sys.version,
                           "frustration_categories": list(FRUSTRATION_CATEGORIES.keys())},
                          ensure_ascii=False, indent=2))

    elif args.mode == "scope":
        result = scope_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.mode == "signals":
        prompts = load_prompts(days=args.days, project=args.project, sources=args.source)
        signals, counts = scan_frustration_signals(prompts)
        # Also find positive signals (successful sessions)
        sessions = defaultdict(list)
        neg_re = re.compile(r'不对|错了|瞎|重[来做]|撤销|恢复|胡编|别瞎')
        for p in prompts:
            if p["session_id"]:
                sessions[(p.get("source_id", "unknown"), p["session_id"])].append(p)
        quick_wins = []
        for (source_id, sid), ps in sessions.items():
            real = [p for p in ps if not p["text"].startswith("/") and len(p["text"]) > 10
                    and not p["text"].startswith("<")]
            if 1 <= len(real) <= 5 and not any(neg_re.search(p["text"]) for p in real):
                if real and len(real[0]["text"]) > 30:
                    quick_wins.append({
                        "session_id": sid,
                        "source_id": source_id,
                        "turns": len(real),
                        "first_prompt": real[0]["text"][:200],
                        "source": real[0].get("source"),
                        "project": real[0]["project"],
                    })

        print(json.dumps({
            "total_prompts": len(prompts),
            "frustration": {"total": len(signals), "categories": counts,
                "signals": [{"cat": s["category"], "text": s["full_prompt"][:200],
                             "source": s.get("source"), "project": s["project"],
                             "session_id": s["session_id"]}
                            for s in signals]},
            "success": {"total": len(quick_wins),
                "sessions": quick_wins[:10]},
        }, ensure_ascii=False, indent=2))

    elif args.mode == "context":
        if not args.session or not args.prompt:
            print(json.dumps({"error": "requires --session and --prompt arguments"}, ensure_ascii=False))
            sys.exit(1)
        result = extract_context(args.session, args.prompt, radius=args.radius, source=args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:  # analyze
        result = analyze(days=args.days, project=args.project, deep=not args.no_deep, sources=args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

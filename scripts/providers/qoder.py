"""
Qoder IDE provider — full support via plaintext JSONL transcripts.

Data sources:
  - ~/.qoder/projects/<project-path>/transcript/<session-id>.jsonl
  - ~/.qoder/cache/projects/<project-hash>/conversation-history/<id>/<id>.jsonl
"""

import json

from .base import (
    QODER_DIR, QODER_APP_DIRS, cutoff_ms, coerce_ts_ms, make_prompt_record,
)


def load_prompts(days=None, project=None):
    """Load Qoder conversation prompts from JSONL transcript files."""
    records = []
    cutoff = cutoff_ms(days)
    transcript_dirs = []
    if QODER_DIR.exists():
        for d in [QODER_DIR / "projects", QODER_DIR / "cache" / "projects"]:
            if d.exists():
                transcript_dirs.append(d)

    jsonl_files = []
    for base in transcript_dirs:
        jsonl_files.extend(base.rglob("*.jsonl"))

    for jsonl_path in jsonl_files:
        session_id = jsonl_path.stem
        parts = str(jsonl_path.relative_to(QODER_DIR)).split("/")
        project_name = "unknown"
        if len(parts) >= 2:
            raw = parts[1]
            segments = raw.rsplit("-", 1)
            if len(segments) == 2 and len(segments[1]) == 8 and all(c in '0123456789abcdef' for c in segments[1]):
                project_name = segments[0]
            else:
                name_parts = [p for p in raw.strip("-").split("-") if p]
                skip = {"Users", "home", "Project", "Projects", "workspace"}
                meaningful = [p for p in name_parts if p not in skip and len(p) > 1]
                project_name = meaningful[-1] if meaningful else name_parts[-1] if name_parts else raw

        if project and project not in project_name:
            continue

        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    obj_type = obj.get("type", "")
                    obj_role = obj.get("role", "")
                    if obj_type not in ("user",) and obj_role not in ("user", "human"):
                        continue

                    msg = obj.get("message", {}) if obj_type == "user" else obj
                    if not isinstance(msg, dict):
                        continue

                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content.strip()
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = (block.get("content", "") or block.get("text", "")).strip()
                                break
                        if not text:
                            continue

                    if not text or len(text) < 3:
                        continue
                    if text.startswith("Command completed") or text.startswith("Contents of /"):
                        continue

                    ts_ms = coerce_ts_ms(obj.get("timestamp", ""))
                    if cutoff and ts_ms and ts_ms < cutoff:
                        continue

                    records.append(make_prompt_record(
                        "qoder", "Qoder", text, ts_ms,
                        project_name, session_id,
                        transcript_path=str(jsonl_path),
                        metadata={"mode": "agent"},
                    ))
        except OSError:
            continue

    return records


def discover():
    """Detect Qoder data source."""
    qoder_transcripts = []
    for base in [QODER_DIR / "projects", QODER_DIR / "cache" / "projects"]:
        if base.exists():
            qoder_transcripts.extend(base.rglob("*.jsonl"))
    qoder_app_found = any(d.exists() for d in QODER_APP_DIRS)
    if not qoder_transcripts and not qoder_app_found:
        return None
    return {
        "source_id": "qoder",
        "status": "full" if qoder_transcripts else "detected_app_only",
        "transcript_count": len(qoder_transcripts),
        "context": "full_transcript" if qoder_transcripts else "no_transcripts_found",
    }


def extract_model(sid, metadata):
    """Extract model from Qoder JSONL (assistant record obj.model or obj.message.model)."""
    for base in [QODER_DIR / "projects", QODER_DIR / "cache" / "projects"]:
        if not base.exists():
            continue
        for jsonl in base.rglob("*.jsonl"):
            if sid[:12] not in jsonl.stem:
                continue
            try:
                for line in open(jsonl, "r", encoding="utf-8"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("role") == "assistant" or obj.get("type") == "assistant":
                        model = obj.get("model") or obj.get("message", {}).get("model", "")
                        if model and model != "auto":
                            return model
                        if model == "auto":
                            provider = obj.get("provider", "")
                            return f"qoder:{provider}" if provider else "qoder:auto"
            except OSError:
                pass
            return None
    return None


def extract_context(session_id, target_prompt_text, radius=4):
    """Extract conversation context from Qoder JSONL transcripts."""
    transcript_file = None
    for base in [QODER_DIR / "projects", QODER_DIR / "cache" / "projects"]:
        if not base.exists():
            continue
        for jsonl in base.rglob("*.jsonl"):
            if session_id in jsonl.stem:
                transcript_file = jsonl
                break
        if transcript_file:
            break

    if not transcript_file:
        return {"error": "qoder_transcript_not_found", "session_id": session_id, "source_id": "qoder"}

    msgs = []
    try:
        with open(transcript_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                t = obj.get("type", "")
                msg = obj.get("message", {})
                if not isinstance(msg, dict):
                    continue

                if t == "user":
                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content.strip()
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = (block.get("content", "") or block.get("text", "")).strip()
                                break
                    if text and len(text) > 2 and not text.startswith("Command completed") and not text.startswith("Contents of /"):
                        msgs.append({"role": "user", "content": text[:500]})

                elif t == "assistant":
                    content = msg.get("content", [])
                    summary_parts = []
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "text":
                                    txt = (block.get("text", "") or block.get("content", ""))[:300]
                                    if txt.strip():
                                        summary_parts.append(txt)
                                elif block.get("type") == "tool_use":
                                    name = block.get("name", "?")
                                    inp = block.get("input", {})
                                    if name in ("read_file", "Read", "Edit", "Write", "SearchReplace"):
                                        fp = str(inp.get("file_path", "?")).split("/")[-1]
                                        summary_parts.append(f"{name}({fp})")
                                    elif name in ("Bash", "run_in_terminal"):
                                        cmd = str(inp.get("command", ""))[:60]
                                        summary_parts.append(f"Bash({cmd})")
                                    else:
                                        summary_parts.append(name)
                    elif isinstance(content, str) and content.strip():
                        summary_parts.append(content[:300])
                    if summary_parts:
                        msgs.append({"role": "assistant", "content": " | ".join(summary_parts[:3])})
    except OSError:
        return {"error": "qoder_transcript_read_error", "session_id": session_id, "source_id": "qoder"}

    if not msgs:
        return {"error": "qoder_context_empty", "session_id": session_id, "source_id": "qoder"}

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
        return {"error": "target_not_found", "session_id": session_id, "source_id": "qoder"}

    start = max(0, target_idx - radius)
    end = min(len(msgs), target_idx + radius + 1)
    return {
        "session_id": session_id,
        "source_id": "qoder",
        "transcript_path": str(transcript_file),
        "total_messages": len(msgs),
        "target_index": target_idx,
        "context_radius": radius,
        "context": [
            {**msgs[i], "is_target": i == target_idx, "position": i - target_idx}
            for i in range(start, end)
        ],
    }

"""
Cursor provider — best-effort SQLite parsing (schema varies across versions).

Data sources:
  - ~/Library/Application Support/Cursor/User/**/state.vscdb
"""

import json
import glob
from pathlib import Path

from .base import (
    CURSOR_DATA_DIRS, cutoff_ms, coerce_ts_ms, make_prompt_record,
    sqlite_fetch, extract_json_user_messages,
)


def load_prompts(days=None, project=None):
    """Best-effort Cursor SQLite reader. Schema varies across versions."""
    cutoff = cutoff_ms(days)
    roots = []
    for d in CURSOR_DATA_DIRS:
        roots.append(d / "User/globalStorage/state.vscdb")
        roots.extend(glob.glob(str(d / "User/workspaceStorage/*/state.vscdb")))
    records = []
    for db in roots:
        db = Path(db)
        workspace = db.parent.name if db.parent.name != "globalStorage" else "global"

        gen_index = {}
        gen_rows = sqlite_fetch(db, "select value from ItemTable where key='aiService.generations'")
        for (val,) in gen_rows:
            try:
                for g in json.loads(val):
                    desc = (g.get("textDescription") or "").strip()
                    if desc:
                        gen_index[desc[:80]] = coerce_ts_ms(g.get("unixMs"))
            except (TypeError, json.JSONDecodeError):
                pass

        prompt_rows = sqlite_fetch(db, "select value from ItemTable where key='aiService.prompts'")
        for (val,) in prompt_rows:
            try:
                for p in json.loads(val):
                    text = (p.get("text") or "").strip()
                    if not text or len(text) < 3:
                        continue
                    ts = gen_index.get(text[:80], 0)
                    if cutoff and ts and ts < cutoff:
                        continue
                    if project and project not in workspace:
                        continue
                    records.append(make_prompt_record(
                        "cursor", "Cursor", text, ts, workspace, "",
                        metadata={"db": str(db), "key": "aiService.prompts"},
                    ))
            except (TypeError, json.JSONDecodeError):
                pass

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
                if project and project not in workspace and project not in str(db):
                    continue
                records.append(make_prompt_record(
                    "cursor", "Cursor", text, ts, workspace, sid,
                    metadata={"db": str(db), "key": key},
                ))
    return records


def discover():
    """Detect Cursor data source."""
    cursor_dbs = []
    for d in CURSOR_DATA_DIRS:
        cursor_dbs.extend(glob.glob(str(d / "User/**/state.vscdb"), recursive=True))
    if not cursor_dbs and not (Path.home() / ".cursor").exists():
        return None
    return {
        "source_id": "cursor",
        "status": "best_effort" if cursor_dbs else "detected_metadata_only",
        "db_count": len(cursor_dbs),
        "context": "sqlite_schema_varies",
    }

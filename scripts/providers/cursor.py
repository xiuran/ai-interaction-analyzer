"""
Cursor provider — best-effort SQLite parsing.

Data sources:
  - SQLite databases in ~/Library/Application Support/Cursor/User/
"""

import json
import glob
from pathlib import Path

from .base import (
    cutoff_ms, coerce_ts_ms, make_prompt_record, sqlite_fetch, extract_json_user_messages,
)


def load_prompts(days=None, project=None):
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


def discover():
    """Detect Cursor data source."""
    cursor_dbs = glob.glob(str(Path.home() / "Library/Application Support/Cursor/User/**/state.vscdb"), recursive=True)
    if not cursor_dbs and not (Path.home() / ".cursor").exists():
        return None
    cursor_prompt_count = len(load_prompts(days=None))
    return {
        "source_id": "cursor",
        "status": "best_effort" if cursor_prompt_count else "detected_metadata_only",
        "db_count": len(cursor_dbs),
        "prompt_count": cursor_prompt_count,
        "context": "sqlite_schema_varies",
    }

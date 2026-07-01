"""
Qoder IDE provider — best-effort SQLite parsing.

Data sources:
  - ~/Library/Application Support/Qoder/SharedClientCache/cache/db/local.db
  - Tables: chat_session (plaintext titles), chat_message (encrypted content, plaintext metadata)

Limitations:
  - Message content is encrypted; only session_title and message summaries are readable
  - Layer 2 context extraction not supported (no plaintext conversation body)
"""

from pathlib import Path

from .base import QODER_DIR, cutoff_ms, make_prompt_record, sqlite_fetch


def load_prompts(days=None, project=None):
    """Load prompts from Qoder IDE SQLite database.

    Session titles (first user prompt) are plaintext and usable for signal scanning.
    Also extracts user message summaries when available.
    """
    db_path = QODER_DIR / "SharedClientCache" / "cache" / "db" / "local.db"
    if not db_path.exists():
        return []
    cutoff = cutoff_ms(days)
    records = []

    # Load session titles (plaintext first prompt) as primary prompt data
    sessions = sqlite_fetch(
        db_path,
        "SELECT session_id, session_title, project_name, mode, gmt_create "
        "FROM chat_session WHERE mode IN ('agent','execute','spec','long_running','experts') "
        "AND session_title != '' ORDER BY gmt_create"
    )
    for sid, title, proj, mode, ts in sessions:
        ts_ms = int(ts) if ts else 0
        if cutoff and ts_ms and ts_ms < cutoff:
            continue
        if project and project not in (proj or ""):
            continue
        records.append(make_prompt_record(
            "qoder", "Qoder", title, ts_ms,
            proj or "unknown", sid,
            metadata={"mode": mode},
        ))

    # Also try to extract user message summaries (if available and non-empty)
    user_msgs = sqlite_fetch(
        db_path,
        "SELECT m.session_id, m.summary, m.gmt_create, s.project_name "
        "FROM chat_message m JOIN chat_session s ON m.session_id = s.session_id "
        "WHERE m.role = 'user' AND m.summary IS NOT NULL AND m.summary != '' "
        "AND s.mode IN ('agent','execute','spec','long_running','experts') "
        "ORDER BY m.gmt_create"
    )
    for sid, summary, ts, proj in user_msgs:
        ts_ms = int(ts) if ts else 0
        if cutoff and ts_ms and ts_ms < cutoff:
            continue
        if project and project not in (proj or ""):
            continue
        records.append(make_prompt_record(
            "qoder", "Qoder", summary, ts_ms,
            proj or "unknown", sid,
            metadata={"from_summary": True},
        ))

    return records


def discover():
    """Detect Qoder data source."""
    db_path = QODER_DIR / "SharedClientCache" / "cache" / "db" / "local.db"
    if not db_path.exists():
        return None
    session_count = 0
    prompt_count = 0
    rows = sqlite_fetch(db_path, "SELECT count(*) FROM chat_session WHERE mode IN ('agent','execute','spec','long_running','experts')")
    if rows:
        session_count = rows[0][0]
    rows = sqlite_fetch(db_path, "SELECT count(*) FROM chat_message WHERE role = 'user'")
    if rows:
        prompt_count = rows[0][0]
    return {
        "source_id": "qoder",
        "status": "best_effort",
        "db_path": str(db_path),
        "session_count": session_count,
        "prompt_count": prompt_count,
        "context": "session_title_plaintext_content_encrypted",
        "note": "Message content encrypted; session titles and metadata available for analysis",
    }

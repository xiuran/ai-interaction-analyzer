"""
Provider registry — unified entry point for loading prompts and discovering data sources.

Each provider module exposes:
  - load_prompts(days, project) → list of prompt records
  - discover() → source info dict or None
  - extract_context(session_id, target_prompt_text, radius) → context dict (optional)

Adding a new provider:
  1. Create a new .py file in this directory
  2. Implement load_prompts() and discover()
  3. Add it to PROVIDER_REGISTRY below
"""

from . import claude_code, codex, cursor, qoder
from .base import parse_sources

# ─── Provider Registry ────────────────────────────────────────
# Each entry: (source_id, module)
# Order matters for context extraction fallback

PROVIDER_REGISTRY = [
    ("claude-code", claude_code),
    ("codex", codex),
    ("cursor", cursor),
    ("qoder", qoder),
]


def load_prompts(days=None, project=None, sources=None):
    """Load prompt index from all supported providers."""
    selected = parse_sources(sources) if isinstance(sources, str) else sources
    records = []
    for source_id, module in PROVIDER_REGISTRY:
        if selected and source_id not in selected:
            continue
        records.extend(module.load_prompts(days=days, project=project))
    records = [r for r in records if r.get("text")]
    records.sort(key=lambda r: r.get("timestamp_ms") or 0)
    return records


def discover_sources():
    """Discover all available data sources."""
    sources = {}
    for source_id, module in PROVIDER_REGISTRY:
        info = module.discover()
        if info:
            # Use a display name derived from source_id
            name = info.get("source_id", source_id).replace("-", " ").title()
            # Map to canonical display names
            display_names = {
                "claude-code": "Claude Code",
                "codex": "Codex",
                "cursor": "Cursor",
                "qoder": "Qoder",
            }
            sources[display_names.get(source_id, name)] = info

    return sources


def extract_context(session_id, target_prompt_text, radius=4, source=None):
    """Extract conversation context around a target prompt. Tries providers in order."""
    source = (source or "").lower()

    if source in ("", "claude-code", "claude"):
        ctx = claude_code.extract_context(session_id, target_prompt_text, radius)
        if source in ("", "claude-code", "claude") and not ctx.get("error"):
            return ctx
        if source:
            return ctx

    if source in ("", "codex"):
        ctx = codex.extract_context(session_id, target_prompt_text, radius)
        if source == "codex" or not ctx.get("error"):
            return ctx

    if source in ("", "qoder"):
        ctx = qoder.extract_context(session_id, target_prompt_text, radius)
        if source == "qoder" or not ctx.get("error"):
            return ctx

    return {
        "error": "context_not_supported_for_source",
        "source_id": source or "unknown",
        "session_id": session_id,
        "note": "This provider currently supports prompt index/signal scanning only, no stable full transcript parsing yet.",
    }


# ─── Per-source model extraction ──────────────────────────────
# Providers that can recover which model produced a session expose extract_model.

_MODEL_EXTRACTORS = {
    "claude-code": claude_code.extract_model,
    "codex": codex.extract_model,
    "qoder": qoder.extract_model,
}


def extract_model(source_id, session_id, metadata):
    """Return the model for a session via the owning provider, or None."""
    fn = _MODEL_EXTRACTORS.get(source_id)
    if not fn:
        return None
    try:
        return fn(session_id, metadata)
    except Exception:
        return None

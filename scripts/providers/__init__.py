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

from pathlib import Path

from . import claude_code, codex, cursor, cline_roo, gemini, chatgpt, qoder
from .base import parse_sources

# ─── Provider Registry ────────────────────────────────────────
# Each entry: (source_id, module)
# Order matters for context extraction fallback

PROVIDER_REGISTRY = [
    ("claude-code", claude_code),
    ("codex", codex),
    ("cursor", cursor),
    ("cline-roo", cline_roo),
    ("gemini", gemini),
    ("chatgpt-export", chatgpt),
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
                "cline-roo": "Cline/Roo Code",
                "gemini": "Gemini CLI",
                "chatgpt-export": "ChatGPT Export",
                "qoder": "Qoder",
            }
            sources[display_names.get(source_id, name)] = info

    # Also detect tools we know about but can't parse yet
    detected_paths = [
        (Path.home() / ".config/github-copilot", "GitHub Copilot", "copilot", "no_stable_local_chat_parser"),
        (Path.home() / ".continue", "Continue", "continue", "detected_not_parsed_yet"),
        (Path.home() / ".aider.chat.history.md", "Aider", "aider", "detected_not_parsed_yet"),
        (Path.home() / ".local/share/opencode", "OpenCode", "opencode", "detected_not_parsed_yet"),
        (Path.home() / "Library/Application Support/Windsurf", "Windsurf", "windsurf", "detected_not_parsed_yet"),
        (Path.home() / "Library/Application Support/Claude", "Claude Desktop", "claude-desktop", "detected_not_parsed_yet"),
    ]
    for path, label, sid, context in detected_paths:
        if path.exists() and label not in sources:
            sources[label] = {
                "source_id": sid,
                "status": "detected_config_only" if context == "no_stable_local_chat_parser" else "detected_provider_todo",
                "path": str(path),
                "context": context,
            }

    return sources


def extract_context(session_id, target_prompt_text, radius=4, source=None):
    """Extract conversation context around a target prompt. Tries providers in order."""
    source = (source or "").lower()

    # Try Claude Code
    if source in ("", "claude-code", "claude"):
        ctx = claude_code.extract_context(session_id, target_prompt_text, radius)
        if source in ("", "claude-code", "claude") and not ctx.get("error"):
            return ctx
        if source:
            return ctx

    # Try Codex
    if source in ("", "codex"):
        ctx = codex.extract_context(session_id, target_prompt_text, radius)
        if source == "codex" or not ctx.get("error"):
            return ctx

    return {
        "error": "context_not_supported_for_source",
        "source_id": source or "unknown",
        "session_id": session_id,
        "note": "This provider currently supports prompt index/signal scanning only, no stable full transcript parsing yet.",
    }

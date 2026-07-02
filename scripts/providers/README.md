# providers/ — one module per AI tool

Each AI tool stores conversations differently, so each gets its own provider
module here. `analyzer.py` owns the source-agnostic analysis engine and reads
all data through this package — it contains no tool-specific loading logic.

## Interface

Every provider module exposes:

- `load_prompts(days=None, project=None) -> list[record]` — required. Each record
  is built with `base.make_prompt_record(...)`.
- `discover() -> dict | None` — required. Source info for the scope report, or
  `None` if this tool has no data on the machine.
- `extract_context(session_id, target_prompt_text, radius=4) -> dict` — optional.
  Layer-2 conversation context around a prompt. Omit if the tool has no stable
  full transcript.
- `extract_model(session_id, metadata) -> str | None` — optional. The model that
  produced a session, if recoverable.

The registry and the `load_prompts` / `discover_sources` / `extract_context` /
`extract_model` dispatchers live in `__init__.py`. Shared helpers (record
builder, JSONL/SQLite readers, timestamp coercion, JSON message extraction) live
in `base.py` — put anything reusable there, not in individual providers.

## Adding a new tool

1. Create `providers/<tool>.py` implementing `load_prompts()` and `discover()`
   (plus `extract_context` / `extract_model` if the data supports them).
2. Import it and add `("<source-id>", <module>)` to `PROVIDER_REGISTRY` in
   `__init__.py`. If it can recover models, add it to `_MODEL_EXTRACTORS` too.
3. Run `python3 scripts/analyzer.py --mode=scope` to confirm it's detected.

No changes to `analyzer.py` are needed to add a tool.

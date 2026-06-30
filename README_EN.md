<p align="center">
  <h1 align="center">AI Interaction Analyzer</h1>
  <p align="center">
    <strong>Turn your AI conversation history into actionable collaboration rules.</strong>
  </p>
  <p align="center">
    <a href="#installation"><img alt="Install" src="https://img.shields.io/badge/install-30s-brightgreen?style=flat-square"></a>
    <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square"></a>
    <img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8+-yellow?style=flat-square">
    <img alt="Dependencies" src="https://img.shields.io/badge/dependencies-0-orange?style=flat-square">
    <br>
    <a href="README.md">中文文档</a>
  </p>
</p>

---

Most AI coding tools generate conversation logs — but nobody reads them. This tool does.

It scans your local conversation history across **6 AI tools**, detects where collaboration broke down (and where it worked), then produces **installable prompt rules** you can drop into any AI tool's config file.

> [!NOTE]
> **100% local. Zero dependencies. No data leaves your machine.**
> Runs on Python stdlib only — clone and go.

## What You Get

```
╔══════════════════════════════════════════════════════════╗
║              AI Interaction Analyzer                     ║
║              Collaboration Quality Diagnosis              ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  📅 2026-06-01 → 2026-06-30    💬 287 prompts · 42 sessions║
║  🔧 Claude Code · Codex · Cursor                        ║
║                                                          ║
║  ┌──────────────────────────────────────────────┐       ║
║  │  Health  ████████████░░░░  72%                │       ║
║  │                                              │       ║
║  │  🔴 35 corrections  🟢 7 first-shot  📝 12 rules     ║
║  └──────────────────────────────────────────────┘       ║
║                                                          ║
║  Problem Distribution                                    ║
║  fabrication   ████████░░  10                            ║
║  incorrect     ██████░░░░   6                            ║
║  low_effort    ████░░░░░░   4                            ║
║  overreach     ██░░░░░░░░   2                            ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

The full output includes:
- **Health dashboard** with problem distribution
- **Incident deep-dives** — ±4 turns of real conversation context per issue
- **Root cause analysis** — why AI went wrong, traced to specific behavior
- **Success pattern extraction** — what you're doing right, keep doing it
- **Prompt Rules** — universal rules with source tracing, ready to install

## Supported Tools

| Tool | Status | What's Analyzed |
|------|--------|----------------|
| **Claude Code** | Full support | Prompt history + full session transcripts |
| **Codex** | Full support | History + rollout transcripts |
| **Cursor** | Best-effort | SQLite chat/composer data |
| **Cline / Roo Code** | Best-effort | JSON conversation history |
| **Gemini CLI** | Best-effort | JSON history files |
| **ChatGPT** (export) | Best-effort | Exported `conversations.json` |

## How It Works

```
  Your conversation logs (local files, never uploaded)
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  Layer 1: Signal Scan           │  Scan all prompts for frustration
  │  "wrong" "undo" "are you sure"  │  and success signals (ZH + EN)
  └───────────────┬─────────────────┘
                  │ incidents found
                  ▼
  ┌─────────────────────────────────┐
  │  Layer 2: Context Deep-Dive     │  Read ±4 turns around each
  │  What did AI do? Why wrong?     │  incident for root cause
  └───────────────┬─────────────────┘
                  │ loop until no new patterns
                  ▼
  ┌─────────────────────────────────┐
  │  Synthesis                      │  Dashboard + Rules +
  │  Prompt Rules + Best Practices  │  Quick Install for any tool
  └─────────────────────────────────┘
```

> [!TIP]
> Signal detection is **bilingual** (Chinese + English). Patterns like `"错了"`, `"wrong"`, `"瞎编"`, `"hallucinating"` are all caught.

## Installation

### Quick Start (30 seconds)

```bash
# Clone into Claude Code skills directory
git clone https://github.com/xiuran/ai-interaction-analyzer ~/.claude/skills/ai-interaction-analyzer

# Verify it works
python3 ~/.claude/skills/ai-interaction-analyzer/scripts/analyzer.py --mode=setup
```

Then type `/ai-trace` in Claude Code.

### As a Claude Code Plugin

```bash
# In Claude Code:
/plugin marketplace add xiuran/ai-interaction-analyzer
```

### Standalone CLI

```bash
git clone https://github.com/xiuran/ai-interaction-analyzer
cd ai-interaction-analyzer

# Scope check — what data do you have?
python3 scripts/analyzer.py --mode=scope

# Full analysis (last 30 days)
python3 scripts/analyzer.py --mode=analyze --days=30

# Signal scan only (faster)
python3 scripts/analyzer.py --mode=signals --days=15

# Deep-dive a specific incident
python3 scripts/analyzer.py --mode=context --session=<ID> --prompt="<TEXT>"

# Filter by tool
python3 scripts/analyzer.py --mode=analyze --source=claude-code,codex
```

<details>
<summary><strong>Optional: SessionEnd Hook</strong></summary>

Auto-log session quality metrics after each Claude Code session:

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionEnd": [{
      "type": "command",
      "command": "python3 ~/.claude/skills/ai-interaction-analyzer/scripts/mini_analyzer.py",
      "timeout": 3
    }]
  }
}
```

Logs are written to `~/.ai-interaction-analyzer/session-log.jsonl`.

</details>

## Output: Quick Install

The analyzer produces rules you can copy-paste into any AI tool:

| Tool | Config File |
|------|------------|
| Claude Code | `CLAUDE.md` |
| Codex | `AGENTS.md` |
| Cursor | `.cursorrules` |
| Cline | `.clinerules` |
| Windsurf | `.windsurfrules` |
| Any tool | System Prompt |

Rules come in two tiers:
- **Universal rules** — patterns applicable to any user, any project (e.g., "read docs before writing code")
- **Custom findings** — personal patterns for your specific workflow (marked optional)

## Custom Configuration

```bash
mkdir -p ~/.config/ai-interaction-analyzer
cp config/custom_patterns.example.json ~/.config/ai-interaction-analyzer/custom_patterns.json
```

Customize:
- Extra confirmation phrases (reduce false positives)
- Custom negation patterns for your language/style
- Task type keywords for your domain
- Projects to exclude from analysis

## Privacy & Security

> [!IMPORTANT]
> This tool is designed with privacy as a hard constraint.

- **100% local** — all analysis runs on your machine
- **Read-only** — never modifies your AI tool configs, logs, or any files
- **No network calls** — zero external API calls, no tracking
- **No dependencies** — Python stdlib only, nothing to audit

## Project Structure

```
ai-interaction-analyzer/
├── SKILL.md                          # AI instruction file (skill entry point)
├── .claude-plugin/marketplace.json   # Claude Code plugin manifest
├── scripts/
│   ├── analyzer.py                   # Main analysis engine (~1200 lines)
│   ├── mini_analyzer.py              # Lightweight session hook
│   └── setup.sh                      # One-command installer
├── config/
│   └── custom_patterns.example.json  # Configuration template
├── references/                       # Scoring models & anti-pattern library
├── README.md                         # 中文文档 (default)
├── README_EN.md                      # English
└── LICENSE (MIT)
```

## License

[MIT](LICENSE)

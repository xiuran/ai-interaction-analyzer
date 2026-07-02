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

AI tools generate conversation logs every day — coding, debugging, writing docs, designing solutions — but nobody reads them. This tool does.

It scans your local conversation history across AI tools (**Claude Code / Codex / Qoder / Cursor**), detects where collaboration broke down (and where it worked), then produces **installable prompt rules** you can drop into any AI tool's config file.

> [!NOTE]
> **100% local. Zero dependencies. No data leaves your machine.**
> Runs on Python stdlib only — clone and go.

## What You Get

Here's output from a real full-history analysis (project names anonymized):

```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║                        AI Interaction Analyzer                           ║
║                     Collaboration Quality Diagnosis                      ║
║                                                                          ║
║    📅  Full year · 365 days                                               ║
║    💬  1902 prompts · 344 sessions                                       ║
║    🔧  Claude Code (1824) · Cursor (33) · Codex (25) · Qoder (20)       ║
║                                                                          ║
║    ┌──────────────────────────────────────────────────────────┐          ║
║    │                                                          │          ║
║    │   Health    █████████████████████░░░░  90.5%              │          ║
║    │                                                          │          ║
║    │   🔴  181 corrections   🟢  111 first-shot successes      │          ║
║    │   📊  ~20 high-density sessions (≥3 corrections)          │          ║
║    │   📝  8 universal rules + 3 custom findings               │          ║
║    │                                                          │          ║
║    └──────────────────────────────────────────────────────────┘          ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

**--- 1. Tool & Model Analysis ---**

```
┌───────────────────────────────────────────────────────────────────────────┐
│  ──── By Tool ─────────────────────────────────────────────────────────── │
│                                                                           │
│  Tool              Prompts   Issues   Rate    Top Problems                │
│  Claude Code       1824      163     8.9%   incorrect(55) shallow(54)    │
│  ████████████████████████████████████████████████████████  1824           │
│  Cursor              33        5    15.2%   incorrect(3) shallow(1)      │
│  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  33            │
│  Codex               25        3    12.0%   shallow(1) overreach(1)      │
│  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  25            │
│  Qoder               20       10    50.0%   incorrect(5) shallow(6)      │
│  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  20            │
│                                                                           │
│  ──── By Model ────────────────────────────────────────────────────────── │
│                                                                           │
│  Model                  Prompts   Issues   Rate    Source                  │
│  claude-opus-4-8           106        4     3.8%   Claude Code            │
│  ██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  106            │
│  gpt-5.5                    27        1     3.7%   Codex                  │
│  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  27             │
│  claude-opus-4-7           392       36     9.2%   Claude Code            │
│  ██████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░  392            │
│  claude-opus-4-6           848       81     9.6%   Claude Code            │
│  ████████████████████████████████████████████████████████  848            │
│  gpt-5.3-codex              20        2    10.0%   Codex                  │
│  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  20             │
│                                                                           │
│  💡 Findings                                                               │
│  · opus-4-8 issue rate 3.8% ≈ 1/3 of opus-4-6 — upgrading pays off      │
│  · opus-4-7 vs opus-4-6 difference is small (9.2% vs 9.6%)               │
│  · Tool differences < Model differences                                  │
└───────────────────────────────────────────────────────────────────────────┘
```

**--- 2. Problem Overview ---**

```
┌───────────────────────────────────────────────────────────────────────────┐
│  ──── Problem Types ───────────────────────────────────────────────────── │
│                                                                           │
│   Incorrect output ██████████████████████████████████████████████  63     │
│   Shallow thinking ████████████████████████████████████████████░░  62     │
│   AI fabrication   █████████████████████████░░░░░░░░░░░░░░░░░░░░  38     │
│   Repeated mistake ██████████████████████░░░░░░░░░░░░░░░░░░░░░░░  33     │
│   Distrust         █████████████████████░░░░░░░░░░░░░░░░░░░░░░░░  31     │
│   Overreach        ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  12     │
│   Undo / redo      █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   8     │
│                                                                           │
│  ──── By Project (normalized issue rate) ─────────────────────────────── │
│   📌 Business code projects: 14-16% issue rate                            │
│   📌 Knowledge management:   6.5% issue rate — 2x lower                  │
└───────────────────────────────────────────────────────────────────────────┘
```

**--- 3. Prompt Quality & Efficiency ---**

```
┌───────────────────────────────────────────────────────────────────────────┐
│  ──── Prompt Information Completeness (form, max 100) ─────────────────── │
│                                                                           │
│   Average: 40.8/100                                                       │
│                                                                           │
│   Complete (80-100) ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  161   11%   │
│   Adequate (60-79)  █████████████░░░░░░░░░░░░░░░░░░░░░░░░░░  214   14%   │
│   Sparse (40-59)    █████████████████████████████████░░░░░░  521   34%   │
│   Minimal (0-39)    ███████████████████████████████████████  629   41%   │
│                                                                           │
│   ⚠ Measures how much info a prompt gives, NOT quality — minimal ≠ bad.   │
│   Underspecified rate: 30.3% (>10 chars, no file ref, no goal verb)       │
│                                                                           │
│  ──── Efficiency ──────────────────────────────────────────────────────── │
│   First-shot success   57.4%   Sessions with ≤3 turns and no negation    │
│   Negation rate        30.8%   Sessions with negation keywords           │
│   Efficiency score     58.7/100                                           │
│                                                                           │
│  ──── Task Types ──────────────────────────────────────────────────────── │
│   Debugging ██████████████████████████████████████████  256   17%         │
│   Research  ████████████████████████████░░░░░░░░░░░░░░  175   11%         │
│   Coding    ██████████████████████░░░░░░░░░░░░░░░░░░░░  134    9%         │
│   Writing   ██████████████████░░░░░░░░░░░░░░░░░░░░░░░░  114    7%         │
│   Config    ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   78    5%         │
│                                                                           │
│  ──── Collaboration Style ─────────────────────────────────────────────── │
│   Directive  71%  │  Review 14%  │  Delegation 10%  │  Collaborative 5%  │
└───────────────────────────────────────────────────────────────────────────┘
```

**--- 4. Session Anti-patterns ---**

```
┌───────────────────────────────────────────────────────────────────────────┐
│   Goal drift (task type switches ≥3)      81 sessions                     │
│   Negation loop (≥2 consecutive)          26 sessions                     │
│   Short commands (≥3 under 10 chars)      13 sessions                     │
└───────────────────────────────────────────────────────────────────────────┘
```

**--- 5–9: Incident Analysis, Success Patterns, Rules, Advice, Quick Install ---**

See the [Chinese README](README.md) for full examples of all 9 sections.

## Supported Tools

| Tool | Status | Data Path | What's Analyzed |
|------|--------|-----------|----------------|
| **Claude Code** | Full support | `~/.claude/` | Prompt history + full session transcripts + model stats |
| **Codex** | Full support | `~/.codex/` | History + rollout transcripts + model stats |
| **Qoder** | Full support | `~/.qoder/` | JSONL transcripts + model info |
| **Cursor** | Best-effort | `~/Library/.../Cursor/` | SQLite database (schema varies across versions) |

## How It Works

```
  Your local conversation logs (never uploaded)
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  Layer 1: Signal Scan + Quality │  Frustration/success signals + model stats
  │  + Efficiency + Anti-patterns   │  + 5-dim prompt scoring + task classification
  │  + Task Types + Collab Style    │  + collaboration style + session anti-patterns
  └───────────────┬─────────────────┘
                  │ incidents found
                  ▼
  ┌─────────────────────────────────┐
  │  Layer 2: Context Deep-Dive     │  Read ±4 turns around each incident
  │  What did AI do? Why wrong?     │  for root cause analysis
  │  → Loop until no new patterns   │  Group by behavior pattern
  └───────────────┬─────────────────┘
                  ▼
  ┌─────────────────────────────────┐
  │  Synthesis (9 sections)         │  Dashboard + Models + Quality & Efficiency
  │  Prompt Rules + Best Practices  │  + Anti-patterns + Root causes + Advice
  └─────────────────────────────────┘
```

## Installation

### Quick Start (30 seconds)

```bash
# Clone into Claude Code skills directory
git clone https://github.com/xiuran/ai-interaction-analyzer ~/.claude/skills/ai-interaction-analyzer

# Verify data sources are detected
python3 ~/.claude/skills/ai-interaction-analyzer/scripts/analyzer.py --mode=scope
```

Then type `/ai-trace` in Claude Code.

### Standalone CLI

```bash
git clone https://github.com/xiuran/ai-interaction-analyzer
cd ai-interaction-analyzer

# Scope check — what data do you have?
python3 scripts/analyzer.py --mode=scope

# Full analysis (default: last 60 days, auto-adjusts based on volume)
python3 scripts/analyzer.py --mode=analyze --days=60

# Analyze ALL history (omit --days for no time filter)
python3 scripts/analyzer.py --mode=analyze

# Signal scan only (faster, no deep-dive)
python3 scripts/analyzer.py --mode=signals --days=15

# Deep-dive a specific incident
python3 scripts/analyzer.py --mode=context --session=<ID> --prompt="<TEXT>"
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

Rules can be installed into any AI tool's config file:

| Tool | Project-level | Global |
|------|--------------|--------|
| Claude Code | `CLAUDE.md` | `~/.claude/CLAUDE.md` |
| Codex | `AGENTS.md` | `~/.codex/AGENTS.md` |
| Cursor | `.cursor/rules/*.mdc` | Settings → Rules for AI |
| Cline | `.clinerules/` | `~/Documents/Cline/Rules/` |
| Windsurf | `.windsurf/rules/*.md` | Settings → AI Rules |
| Any tool | — | System Prompt / Instructions |

Rules come in two tiers:
- **Rules** — behavior patterns abstracted from root causes (copy-paste ready)
- **Custom findings** — patterns specific to your workflow (marked optional)

Example rules from a real analysis (ready to copy into your config):

```
1. Before calling any third-party API, Read source code or decompile to confirm method signatures. Never guess.
2. When referencing old code for new features, Read the method body (not just the signature) to find diff points.
3. During debugging, never give definitive conclusions with insufficient data. List "confirmed facts" and "missing info" first.
4. After receiving feedback, change only what was mentioned. Use precise Edit, not full rewrite.
5. After code changes, globally check for stale imports/comments/constants. Use enums instead of magic strings.
6. After generating frontend code, verify visual output. If unable to screenshot, explicitly state "UI needs manual review".
7. No process talk in deliverables. No design rationale, no "this section relates to X". Just the content.
8. When writing specs from code, use git diff to distinguish production code from unmerged changes.
```

> Each rule traces back to a specific root cause pattern and incident count in the full report.

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
├── scripts/
│   ├── analyzer.py                   # Main analysis engine
│   ├── mini_analyzer.py              # Lightweight session hook
│   ├── setup.sh                      # One-command installer
│   └── providers/                    # One module per AI tool
│       ├── base.py                   #   Shared helpers (record builder / JSONL / SQLite / timestamps)
│       ├── claude_code.py            #   Claude Code (history + full transcript)
│       ├── codex.py                  #   Codex (history + rollout transcript)
│       ├── qoder.py                  #   Qoder (JSONL transcript)
│       ├── cursor.py                 #   Cursor (SQLite, best-effort)
│       └── README.md                 #   How to add a new provider
├── config/
│   └── custom_patterns.example.json  # Configuration template
├── references/                       # Anti-patterns (user + AI side) / metrics / quality model
├── README.md                         # 中文文档 (default)
├── README_EN.md                      # English
└── LICENSE (MIT)
```

## License

[MIT](LICENSE)

---
name: ai-interaction-analyzer
description: |
  Multi-round cyclic analysis of user conversations with AI coding tools
  (Claude Code / Cursor / Codex / Cline / Copilot / Gemini CLI, etc.).
  Scans inputs for signals first, then reads context for deeper analysis,
  looping until no new findings remain.
  Output: installable Prompt Rules + Best Practices, not a stats report.
  Triggers: "/ai-trace", "analyze my AI conversations", "AI collaboration analysis",
  "prompt quality", "look at my AI chat issues".
---

# AI Interaction Analyzer

Analyze your real conversation logs through multi-round cyclic analysis to find AI problem patterns and success patterns, producing collaboration rules that can be directly installed into any AI tool.

---

## When to Use

Trigger when the user shows any of these intents:
- "Analyze my AI conversation quality"
- "How is my prompt quality lately"
- "/ai-trace"
- "Analyze my Cursor/Claude Code/Codex usage"

---

## Input Validation

| Check | Pass Condition | Failure Handling |
|-------|---------------|-----------------|
| At least one data source exists | See "Supported Data Sources" | Inform user of detected source status |
| Python 3.8+ available | `python3 --version` | Run `setup.sh` for auto-install |

---

## Supported Data Sources

| Tool | Prompt Index | Full Conversation (incl. AI replies) |
|------|-------------|-------------------------------------|
| Claude Code | `~/.claude/history.jsonl` | `~/.claude/projects/*/*.jsonl` |
| Codex | `~/.codex/history.jsonl` | `~/.codex/sessions/**/*.jsonl` |
| Cursor | `~/Library/Application Support/Cursor/` | Session files in same directory |
| Cline/Roo | `~/.vscode/extensions/saoudrizwan.claude-dev-*/` | globalStorage |
| Copilot | `~/.config/github-copilot/` | Same directory |
| Gemini CLI | `~/.gemini/history/` | Same directory |

<HARD-GATE>
Read-only local analysis. No data upload, no modification of user data.
</HARD-GATE>

---

## Execution Flow — Multi-Round Cyclic Analysis

The overall flow has 4 stages. Stages 2-3 loop until no new findings.

### Stage 0: Determine Analysis Scope

```bash
python3 <SKILL_DIR>/scripts/analyzer.py --mode=scope
```

The script scans data sources and returns data volumes for each time range.

Scope rules (first match wins):
1. Last 30 days prompts > 500 → shrink to 15 days (too much data hurts quality)
2. Last 30 days prompts < 50 → expand to 60 days (too few for pattern extraction)
3. Otherwise → 30 days

Inform the user of the analysis scope, then begin.

### Stage 1: Layer 1 — Scan Inputs, Extract Signals

```bash
python3 <SKILL_DIR>/scripts/analyzer.py --mode=signals --days=<N>
```

The script scans all prompt text, extracting by category:
- **Frustration signals**: User corrections of AI (fabrication/mistakes/poor quality/overreach/repeated errors)
- **Positive signals**: User approval of AI (praise/trust delegation/solution reuse)
- **Successful sessions**: ≤ 5 turns, no negations

Output: list of incidents for deep analysis + list of successful sessions worth extracting.

### Stage 2: Layer 2 — Read Context, Deep Analysis (Loop)

For each incident / successful session, read ±4 turns of full conversation around the complaint/success point:

```bash
python3 <SKILL_DIR>/scripts/analyzer.py --mode=context --session=<SID> --prompt="<TEXT>"
```

AI reads context and analyzes:
- **What AI did**: tool calls, output content
- **Why it failed / succeeded**: root cause
- **How user corrected / why they approved**: correction direction
- **Whether to go deeper**: does this incident relate to other sessions?

<HARD-GATE>
Context reading limited to ±4 turns around the complaint/success point (8 turns total).
Never read entire sessions to avoid token explosion.
</HARD-GATE>

### Stage 3: Continue or Stop (Loop Exit)

After each Layer 2 round, evaluate whether to continue:

Priority rules (first match wins):
1. Found new problem patterns not covered → continue, read more incidents
2. Same issue type across multiple projects → continue, compare differences
3. Incident links to earlier/later sessions → continue, trace connections
4. Analyzed incidents cover all major problem types → stop
5. 2 consecutive rounds with no new findings → stop

After stopping, proceed to Stage 4.

### Stage 4: Synthesis & Output

Based on all rounds of analysis, produce complete diagnosis:

1. **Dashboard Overview**: Health score, problem distribution charts, session distribution
2. **Efficiency Data**: First-shot success rate, negation rate, Read:Edit ratio, cache efficiency, token usage
3. **Incident Deep Analysis**: Context + root cause + extracted rules for each incident
4. **Success Pattern Analysis**: Best Practices from successful sessions
5. **Dimension Breakdown**: By project/task type (only when differences are significant)
6. **Prompt Rules + Quick Install**: Rules copyable to any AI tool

---

## Analysis Dimensions (9)

| # | Dimension | Data Source | Output |
|---|-----------|------------|--------|
| 1 | Model Analysis | session JSONL (message.model) | Per-model complaint rate + problem characteristics + cross-version trends |
| 2 | Frustration Signal Classification | history.jsonl prompt text | Problem distribution chart + incident list |
| 3 | Positive Signal Extraction | history.jsonl + session JSONL | Success patterns + Best Practices |
| 4 | Incident Deep Analysis | session JSONL (±4 turn context) | Root cause + traceable Prompt Rules |
| 5 | Efficiency Data | session JSONL (usage field) | First-shot rate / negation rate / token ROI |
| 6 | AI Behavior Quality | session JSONL (tool_use) | Read:Edit ratio / no-Read-before-Edit ratio |
| 7 | Collaboration Profile | prompt text + session stats | Style classification / task type efficiency / peak hours |
| 8 | Dimension Breakdown | Cross-tabulation | By project/task type/model (only when significant) |
| 9 | High-Frequency Phrases | prompt text | Phrases user says repeatedly → workflow characteristics |

---

## Output Node Decision Rules

| Node | Output When | Skip When |
|------|------------|-----------|
| Dashboard (health + distribution + sessions) | Always | Never |
| Model Analysis | session JSONL has model data | Only single model |
| Efficiency Table | session JSONL has usage data | Only history.jsonl, no usage |
| Incident Analysis | ≥ 1 incident with context | No incidents |
| Success Session Analysis | ≥ 1 success case with context | No success cases |
| Collaboration Profile | ≥ 50 prompts | < 50 prompts |
| Dimension Breakdown | Significant differences across dimensions | Not significant |
| Prompt Rules | ≥ 1 generalizable rule | No rules |
| Best Practices | ≥ 1 generalizable pattern | No patterns |
| Quick Install | When Prompt Rules output exists | No rules |

---

## Output Template

Output directly in conversation. Match the user's language (Chinese or English).

IMPORTANT: The analyzer outputs `category_labels` in JSON with both `en` and `zh` display names.
Always use the human-readable label from `category_labels`, NEVER show raw keys like `low_effort` or `fabrication`.

ALWAYS use this structure:

```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║                        AI Interaction Analyzer                           ║
║                        ── 协 作 质 量 诊 断 ──                            ║
║                                                                          ║
║    📅  {start} ~ {end} ({N}天)                                           ║
║    💬  {prompts} prompts · {sessions} sessions                           ║
║    🔧  {tool (count)} · {tool (count)}                                   ║
║                                                                          ║
║    ┌──────────────────────────────────────────────────────────┐          ║
║    │                                                          │          ║
║    │   健 康 度    ████████████████████░░░░  90%                │          ║
║    │                                                          │          ║
║    │   🔴  {n} 次纠正       🟢  {n} 次一次成功                  │          ║
║    │   📊  {n} 个高密度 session（≥3 次纠正）                    │          ║
║    │   📝  {n} 条通用规则 + {n} 条定制发现                      │          ║
║    │                                                          │          ║
║    └──────────────────────────────────────────────────────────┘          ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝

--- 1. Model Analysis ---

Use box drawing. Show each model as a row with bar chart + stats.
Bar charts use █ and ░ directly, no curly braces:

┌───────────────────────────────────────────────────────────────────────────┐
│  模型                总 prompt   问题数   问题率   主要问题                 │
│  ──────────────────────────────────────────────────────────────────────── │
│  claude-opus-4-6       605       32     5.3%   编造(12) 不认真(10)        │
│  ████████████████████████████████████████████████░░░░░░░  605             │
│                                                                           │
│  claude-opus-4-7       432        8     1.9%   不认真(4) 重复(3)          │
│  ██████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░  432             │
│                                                                           │
│  💡 发现                                                                   │
│  · Which model has lowest issue rate and why                              │
│  · Common issues across all versions                                      │
│  · Version-specific patterns                                              │
└───────────────────────────────────────────────────────────────────────────┘

--- 2. Problem Overview ---

Use box drawing. Three sub-sections. Bar charts use █ and ░ directly, no curly braces:

┌───────────────────────────────────────────────────────────────────────────┐
│  ──── 问题类型 ────────────────────────────────────────────────────────── │
│   AI 不够认真    ███████████████████████████████████████████   40         │
│   AI 编造/瞎猜   ██████████████████████████░░░░░░░░░░░░░░░░   25         │
│   AI 做错了      ████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░   15         │
│   ...                                                                     │
│                                                                           │
│  ──── Session 长度 ────────────────────────────────────────────────────── │
│   1-5 轮       ████████████████████████████████████████████   92   63%   │
│   6-15 轮      ██████████████████░░░░░░░░░░░░░░░░░░░░░░░░░   38   26%   │
│   16-30 轮     ██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   12    8%   │
│   30+ 轮       ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    5    3%   │
│                                                                           │
│  ──── 按项目（归一化问题率，差异显著）──────────────────────────────────── │
│   项目            总prompt  问题数  问题率  主要问题                       │
│   projectA          80      12    15.0%  编造+不认真                      │
│   projectB          60       6    10.0%  做错+编造                        │
│   ...                                                                     │
└───────────────────────────────────────────────────────────────────────────┘

--- 3. Incident Deep Analysis ---

CRITICAL: Do NOT list incidents one by one. Instead:
1. First analyze all incidents
2. Group them by ROOT CAUSE PATTERN (e.g. "fabrication when info unavailable",
   "overreach on modifications", "misunderstanding user intent")
3. Name each pattern (Pattern A, B, C...) with a descriptive title
4. Under each pattern, show 2-3 real cases with full conversation context

Each pattern uses this box format:

┌───────────────────────────────────────────────────────────────────────────┐
│  Covers {N} incidents · projects: {project1} / {project2}                │
│                                                                           │
│  Case 1  {project} · {task description}                                  │
│  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄       │
│  👤 {what user asked}                                                     │
│  🤖 {what AI did wrong} → {specific wrong action}                        │
│  👤 {user's correction — verbatim quote}                                  │
│  → {what happened after}                                                  │
│                                                                           │
│  Case 2  ...                                                              │
│                                                                           │
│  Root cause: {one-sentence root cause}                                    │
│  Context: {when this pattern typically occurs}                            │
└───────────────────────────────────────────────────────────────────────────┘

--- 4. Success Session Analysis ---

CRITICAL: Do NOT list sessions one by one. Instead:
1. Analyze all successful sessions (≤5 turns, no negation)
2. Group them into NAMED REUSABLE PATTERNS
3. Each pattern shows a real example prompt and explains why it works

Format:

┌───────────────────────────────────────────────────────────────────────────┐
│  ✅ Pattern A  {pattern name} (~{N}% of successful sessions)             │
│  ─────────────────────────────────────────────────────────────────────    │
│  "{example first prompt from a real session}"                             │
│  → {why this works: specific elements that made it succeed}              │
│                                                                           │
│  ✅ Pattern B  ...                                                        │
│  ...                                                                     │
└───────────────────────────────────────────────────────────────────────────┘

--- 5. Prompt Rules ---

Two-tier output in box format:

┌───────────────────────────────────────────────────────────────────────────┐
│  Universal Rules — applicable to any user, any AI tool                   │
│                                                                           │
│  1. {rule text}                                                           │
│     ── Source: Pattern {X}, {N} incidents, {description}                  │
│                                                                           │
│  2. ...                                                                   │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│  Custom Findings — valuable for this user only, optional to keep         │
│                                                                           │
│  a. {finding}                                                             │
│  b. ...                                                                   │
└───────────────────────────────────────────────────────────────────────────┘

Rules MUST be generalized from specific incidents to universal patterns:
  ❌ "Project X's AB experiment needs to read the wiki docs first" — too specific
  ✅ "When user provides documentation, must read it first; if unreadable, say so" — universal
Each rule annotated with source pattern and incident count (higher density = more credible).

--- 6. Quick Install ---

┌───────────────────────────────────────────────────────────────────────────┐
│  Copy rules to your AI tool's config file:                               │
│                                                                           │
│   Claude Code → CLAUDE.md            Cursor    → .cursorrules            │
│   Codex      → AGENTS.md             Cline     → .clinerules             │
│   Windsurf   → .windsurfrules        General   → System Prompt           │
└───────────────────────────────────────────────────────────────────────────┘

Then output THREE copyable sections:

## Universal Rules (copy directly)
{numbered list of all universal rules, plain text, no box drawing}

## Best Practices (copy directly)
{lettered list of success patterns, one line each: pattern name + key elements}

## Custom Findings (optional)
{lettered list of custom findings}
```

---

## Fixed Output Rules

### Content Rules
1. **Report outputs directly in conversation**. Save to file only when user requests.
2. **Incident analysis must be based on real context**. Never generalize rules without reading context — better to output less than to fabricate.
3. **Every rule must trace to specific incidents**. No untraceable generic advice like "improve prompt quality".
4. **Include both positive and negative analysis**. Only looking at problems is one-sided.
5. **Context-aware**: `git commit`, `continue`, `ok` are perfectly normal in conversation, not problems.
6. **Dimension breakdown only when differences are significant**. Don't default to per-project tables.
7. **Quick Install is tool-agnostic**. List all major AI tool config paths, user chooses.
8. **Rules must be generalized**. Abstract from specific incidents to pattern-level. Custom findings listed separately.
9. **Don't be lazy**. Layer 2 must cover all high-density sessions (signal ≥ 3), not just 2-3 then stop.

### Visual Rules
1. **Every major section needs numbered headings** (1, 2, 3...) for quick scanning.
2. **Use charts not prose**: problem distribution → bar chart, session distribution → bar chart, model comparison → table + chart.
3. **Incidents use bordered structure**: prior context / complaint / correction / root cause — four sections clearly separated.
4. **Success sessions use card style**: one card per pattern with first prompt + why successful + extracted pattern.
5. **Separate universal and custom rules**: universal rules get copyable text, custom findings marked "personal, optional to keep".

---

## Constraints & Anti-Patterns

<HARD-GATE>
- Pure local analysis, no data upload, no external API calls
- Read-only on user data files, never modify AI tool config or logs
- No value judgments on the user, only point out specific improvable items
- Each incident context limited to ±4 turns, never read entire sessions
</HARD-GATE>

### Anti-Pattern 1: Generalizing rules without reading context
❌ Seeing prompt "deployed but still broken" → generalizing "switch paths when stuck"
✅ Reading context reveals AI didn't read docs before writing code → generalize "must read docs before writing code"

### Anti-Pattern 2: Outputting stats reports
❌ "Vagueness rate 58%, negation rate 30%, first-shot rate 50%"
✅ Specific incident analysis + traceable rules

### Anti-Pattern 3: Rules too vague
❌ "Suggest improving prompt specificity"
✅ "When introducing concepts, give entity identity first (what/who made it/open source?), then use analogies"

### Anti-Pattern 4: Only looking at negatives
❌ All problems no highlights
✅ Also show successful session patterns, tell user what practices to keep

### Anti-Pattern 5: Tool-specific binding
❌ Quick Install only writes CLAUDE.md
✅ List Claude Code / Cursor / Codex / Cline / Windsurf and all tool config paths

### Anti-Pattern 6: Rules too specific, not universal
❌ "Project X's AB experiment needs to read the wiki docs first"
✅ "When user provides doc links, must read docs first; if unreadable, say so"
Custom findings (project-specific patterns) go in the "Custom Findings" section

### Anti-Pattern 7: Lazy analysis only looking at a few incidents
❌ 51 problem sessions but only deep-analyzed 3 before outputting report
✅ Cover all sessions with signal ≥ 3, loop until no new patterns

### Anti-Pattern 8: Editing one thing but losing others
❌ Receiving feedback then heavily rewriting, deleting previously polished efficiency data/charts/profile
✅ Incremental improvement: add new content, keep existing good content, precisely update conflicts

---

## Installation

```bash
# One-command install (checks environment, creates symlink, scans data sources)
bash <SKILL_DIR>/scripts/setup.sh
```

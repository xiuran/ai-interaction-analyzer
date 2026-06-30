# Metrics Definition & Formulas

## 1. Prompt Quality Score

### Formula

Single prompt score = Length + Reference + Goal + Context + Focus

| Dimension | Max Score | Criteria |
|-----------|----------|---------|
| Appropriate length | 20 | 50-500 chars = 20, 20-50 = 10, 500+ = 15 |
| Specific reference | 25 | Contains file path or `file:line` format |
| Clear goal | 20 | Contains goal keywords (implement/fix/add/delete, etc.) |
| Context provided | 20 | Contains reason/background keywords (because/currently/before, etc.) |
| Single focus | 15 | 1-2 goal keywords = 15, 3+ = 5 |

Total = mean(all real prompt scores), capped at 100.

### Exclusions

- Slash commands (`/xxx`) are excluded from quality scoring
- Pure numbers or single symbols are excluded

### Vagueness Rate

Vague prompt = length > 10 chars, but no file reference AND no goal keywords.
Vagueness rate = vague prompts / total real prompts × 100%

---

## 2. Conversation Efficiency Score

### Formula

Efficiency = first-shot rate × 40% + (1 - negation rate) × 30% + tool density × 30%

| Component | Weight | Definition |
|-----------|--------|-----------|
| First-shot rate | 40% | Sessions with ≤ 3 turns and no negation / total sessions |
| No-negation rate | 30% | Sessions without negation words / total sessions |
| Tool density | 30% | min(tool_events / prompts, 2) / 2 |

### Negation Keywords

Chinese: `不对` `不是` `重来` `重做` `改一下` `错了` `换一个` `换一种` `别这样` `不要这样` `不要这么` `不要这个` `重新`

English: `wrong` `incorrect` `undo` `revert` `redo` `not right` `start over` `go back` `that's not`

### Turn Categories

| Category | Range | Notes |
|----------|-------|-------|
| Quick | 1-3 | Completed in one shot or simple confirmation |
| Medium | 4-10 | Normal complexity task |
| Deep | 11-30 | Complex task or exploratory conversation |
| Marathon | 30+ | Watch for session bloat |

---

## 3. Communication Patterns

### Collaboration Style Classification

| Style | Trigger Words | Description |
|-------|--------------|-------------|
| Delegation | help me / do it / give me / just do it | Fully delegated to AI |
| Collaboration | we / together / let's think / discuss / what do you think | Both parties thinking |
| Review | check / review / look at / inspect / audit | User leads, AI validates |
| Direct command | (other) | Clear instructions without collaboration signals |

### Task Type Classification

| Type | Keyword Matches |
|------|----------------|
| Coding | write code / implement / develop / function / method / class / interface / import / def |
| Debugging | bug / error / exception / failure / not working / fix / debug / trace |
| Research | search / investigate / find / compare / evaluate / how to / what is |
| Writing | write article / document / summary / report / blog / README |
| Config | configure / setup / install / deploy / environment / hook / settings / config |

---

## 4. Anti-Pattern Detection Rules

| Anti-Pattern | Trigger Condition | Severity |
|-------------|-------------------|----------|
| Repeated negation | ≥ 2 consecutive prompts with negation words in same session | 🔴 High |
| Too-short commands | ≥ 3 prompts < 10 chars (non-slash) in same session | 🟡 Medium |
| Session bloat | Single session > 50 turns | 🟢 Low |
| Goal drift | Task type switches ≥ 3 times in same session | 🟡 Medium |

### Exclusions

- Slash commands don't count as "too-short commands"
- Coding sessions naturally have many turns; the 50+ threshold is a reference only
- Goal drift detection is based on consecutive type changes (adjacent same types are merged)

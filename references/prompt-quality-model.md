# Prompt Quality Scoring Model

## Design Philosophy

A good prompt doesn't have to be long, but must let AI understand the intent without guessing.

Core principles:
1. **Information completeness** > information volume: 10 clear words beat 100 unclear words
2. **Actionable** > understandable: AI should be able to start working immediately
3. **Don't penalize brevity**: slash commands and clear short directives should not be penalized

## Five-Dimension Scoring Model

### Dimension 1: Appropriate Length (max 20)

| Range | Score | Reason |
|-------|-------|--------|
| < 10 chars | 0 | Likely insufficient info (unless a clear command) |
| 10-19 | 5 | Short but possibly sufficient |
| 20-49 | 10 | Concise and reasonable |
| 50-500 | 20 | Sweet spot for information density |
| 500+ | 15 | Detailed but may be redundant |

### Dimension 2: Specific Reference (max 25)

Match patterns:
- File path: `/path/to/file.ext` or `~/xxx`
- Line reference: `filename.ext:42`
- Code symbol: `ClassName.methodName`

Present → +25. This is the key dimension separating "vague request" from "actionable instruction."

### Dimension 3: Clear Goal (max 20)

Keywords: `I want` `need` `goal` `expect` `hope` `require` `implement` `complete` `fix` `modify` `add` `delete`

Present → +20. Indicates the user expressed a clear intent verb.

### Dimension 4: Context Provided (max 20)

Keywords: `because` `reason` `background` `before` `currently` `the problem is` `context`

Present → +20. Indicates the user provided "why" information.

### Dimension 5: Goal Focus (max 15)

| Goal keyword count | Score | Interpretation |
|-------------------|-------|---------------|
| 0 | 0 | No clear goal |
| 1-2 | 15 | Focused, good |
| 3 | 10 | Slightly many but acceptable |
| 4+ | 5 | Multi-objective mix, risk of omission |

## Scoring Examples

### High Score (100/100)

> Fix the null pointer exception in src/services/auth.ts:47, currently getSession() returns null when user is not logged in but the caller doesn't handle it

- Length: 20 (50-500 chars)
- Reference: 25 (`src/services/auth.ts:47`)
- Goal: 20 ("Fix")
- Context: 20 ("currently...when user is not logged in...")
- Focus: 15 (single goal)
- **Total: 100**

### Medium Score (45/100)

> Help me fix that login bug

- Length: 10 (20-49 chars)
- Reference: 0 (no file path)
- Goal: 20 ("fix")
- Context: 0 (no background)
- Focus: 15 (single goal)
- **Total: 45**

### Low Score (5/100)

> fixed it

- Length: 0 (< 10 chars)
- Reference: 0
- Goal: 0 ("fixed" is past tense, not a goal)
- Context: 0
- Focus: 0
- **Total: 0 → floor at 5**

## Future Directions

1. **LLM-assisted scoring**: use a small model to judge prompt "actionability"
2. **Personalized weights**: adjust dimension weights based on user collaboration style
3. **Comparative scoring**: compare different prompt phrasings for the same task
4. **Cross-session tracking**: when same topic spans sessions, track if prompt quality improves

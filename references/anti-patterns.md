# Anti-Pattern Library

A growing collection of AI collaboration anti-patterns. Add new patterns to the appropriate category as they're discovered.

---

## 1. Information Deficit

### 1.1 Naked Command

**Symptom**: Prompt has only a verb, no object or context.
**Examples**: `fix it` `optimize` `refactor` `done`
**Impact**: AI must guess the target, likely guesses wrong → wastes 1-2 rounds.
**Fix**: At minimum, include a filename or function name.

### 1.2 Anchorless Reference

**Symptom**: Mentions "that file", "the one before", "the thing above" without a specific path.
**Examples**: `change that interface` `the class above has a problem`
**Impact**: AI may reference the wrong context.
**Fix**: Use full path or `filename:line` format.

### 1.3 Implicit Expectation

**Symptom**: Says "wrong" but doesn't say what's wrong or what's expected.
**Examples**: `not like this` `wrong` `try another way`
**Impact**: AI guesses the rejection reason, often tweaks in the same wrong direction.
**Fix**: State "what's wrong" + "what's expected."

---

## 2. Efficiency

### 2.1 Negation Loop

**Symptom**: 3+ consecutive rounds of rejecting AI output.
**Root cause**: Initial prompt lacked clear goals, or user has a specific image in mind but didn't express it.
**Signal**: Negation word density > 30% in a session.
**Fix**: On the 2nd rejection, stop and write a more complete prompt.

### 2.2 Session Bloat

**Symptom**: Single session exceeds 50 turns with unclear deliverables.
**Root cause**: Goal drift, mid-stream scope additions, or cramming unrelated tasks into one session.
**Signal**: turns > 50 and task type switches ≥ 2 times.
**Fix**: One session, one goal. Split complex tasks into separate sessions.

### 2.3 Excessive Confirmation

**Symptom**: AI asks for confirmation at every step, user keeps saying "continue."
**Root cause**: Prompt didn't pre-authorize autonomous execution.
**Signal**: > 30% of prompts in session are `continue/ok/yes/right/go ahead`.
**Fix**: Include "execute directly, no step-by-step confirmation needed" in initial prompt.

---

## 3. Behavioral Patterns

### 3.1 Goal Drift

**Symptom**: Task direction changes 3+ times within one session.
**Examples**: `write an API` → `actually check the logs first` → `fix this bug first` → `let's write docs instead`
**Root cause**: User discovers new issues during exploration without realizing they've drifted.
**Fix**: When drift is detected, start a new session. Keep original session focused.

### 3.2 Over-Delegation

**Symptom**: Delegating tasks that would be faster to do manually.
**Examples**: `how many lines in this file` `how do you spell this variable`
**Signal**: Many < 10 char non-command prompts.
**Impact**: Waiting for AI response may take longer than doing it yourself.
**Fix**: Use CLI tools directly for simple lookups.

### 3.3 Context Fragmentation

**Symptom**: Multiple consecutive prompts with no logical connection, each requiring context rebuild.
**Root cause**: User has a complete task chain in mind but only sends one step at a time.
**Fix**: Write one complete prompt describing the entire task chain (step 1 → step 2 → step 3).

---

## 4. Quality

### 4.1 Copy-Paste Prompt

**Symptom**: Pastes an entire error log or code block without any explanation.
**Impact**: AI can only guess the intent (fix? explain? ignore?).
**Fix**: After pasting, add one sentence: "please explain this error" or "please fix this issue."

### 4.2 Multi-Objective Soup

**Symptom**: One prompt contains 4+ unrelated objectives.
**Examples**: `write an API, also fix that bug, and check performance, oh and update the docs too`
**Impact**: AI may miss some objectives or handle all of them superficially.
**Fix**: Split complex requests into multiple prompts, each focused on one objective.

---

## How to Use This Document

1. The analysis engine references this document when detecting anti-patterns to provide improvement suggestions
2. New patterns should be appended to the appropriate category
3. Each pattern must include: symptom, root cause/signal, and fix
4. The analyzer engine pulls matching suggestions based on detection results

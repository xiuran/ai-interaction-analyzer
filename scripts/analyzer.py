#!/usr/bin/env python3
"""
AI Interaction Analyzer — Layered analysis engine

Layer 1 (lightweight): scan all prompts, extract frustration signals
  → valuable without context: what phrases does the user keep saying?
Layer 2 (targeted deep-dive): for each frustration signal, read ±4 turns
  of context from session JSONL
  → what did AI do before? why is user unhappy? did AI correct?

Outputs JSON to stdout for AI to present diagnosis in conversation.
Zero external dependencies — stdlib only.
"""

import json
import os
import re
import sys
import argparse
import glob
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

# Source-specific loading / context / model extraction lives in providers/;
# analyzer.py owns the source-agnostic analysis engine and delegates data access.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from providers import (  # noqa: E402
    load_prompts, discover_sources, extract_context, extract_model,
)

CLAUDE_DIR = Path.home() / ".claude"
SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "config"
USER_CONFIG_DIR = Path.home() / ".config" / "ai-interaction-analyzer"


# ─── Custom config ────────────────────────────────────────────

def load_custom_config():
    for d in [USER_CONFIG_DIR, CONFIG_DIR]:
        f = d / "custom_patterns.json"
        if f.exists():
            try:
                return json.load(open(f, encoding="utf-8"))
            except Exception:
                pass
    return {}

CUSTOM = load_custom_config()


# ─── AI-side anti-pattern library ─────────────────────────────
# Loaded from references/antipatterns.json. An incident's user-correction text
# is matched against these patterns; on a hit the curated root_cause + fix_rule
# are attached to the incident. Unmatched incidents fall back to LLM analysis.

REFERENCES_DIR = SKILL_DIR / "references"


def _compile_antipattern_entries(entries, default_id="custom"):
    compiled = []
    for entry in entries or []:
        det = entry.get("detection", "")
        if not det:
            continue
        try:
            rx = re.compile(det, re.IGNORECASE)
        except re.error:
            continue
        compiled.append({
            "id": entry.get("id", default_id),
            "label": entry.get("label", {}),
            "regex": rx,
            "root_cause": entry.get("root_cause", {}),
            "fix_rule": entry.get("fix_rule", {}),
            "scenario": entry.get("scenario", {}),
        })
    return compiled


def load_antipatterns():
    """Load the AI-side anti-pattern library (shipped + user-contributed)."""
    patterns = []
    f = REFERENCES_DIR / "antipatterns.json"
    if f.exists():
        try:
            data = json.load(open(f, encoding="utf-8"))
            patterns.extend(_compile_antipattern_entries(data.get("ai_side")))
        except Exception:
            pass
    # Users can extend recall without touching shipped files.
    patterns.extend(_compile_antipattern_entries(CUSTOM.get("extra_antipatterns")))
    return patterns


ANTIPATTERNS = load_antipatterns()


def match_antipatterns(*texts):
    """Match text(s) against the AI-side library. Returns matched pattern dicts."""
    blob = " ".join(t for t in texts if t)
    if not blob.strip() or not ANTIPATTERNS:
        return []
    matched = []
    for p in ANTIPATTERNS:
        m = p["regex"].search(blob)
        if m:
            matched.append({
                "id": p["id"],
                "label": p["label"],
                "root_cause": p["root_cause"],
                "fix_rule": p["fix_rule"],
                "scenario": p["scenario"],
                "matched_signal": m.group()[:40],
            })
    return matched


def _span_days(timestamps):
    """Days between earliest and latest ISO timestamp in the list."""
    ds = []
    for t in timestamps:
        if not t:
            continue
        try:
            ds.append(datetime.fromisoformat(str(t).replace("Z", "+00:00")))
        except (ValueError, TypeError):
            continue
    if len(ds) < 2:
        return 0
    return (max(ds) - min(ds)).days


def scan_antipattern_matches(signals):
    """Match every frustration signal against the AI-side library.

    Returns a list keyed by pattern id, each with the pattern metadata plus
    cross-session reach: how many times it fired, across how many projects and
    sessions, and over how many days. One known root cause spanning many
    projects over weeks is a far sharper signal than a raw count.
    """
    by_id = {}
    for s in signals:
        for m in match_antipatterns(s.get("full_prompt", "")):
            slot = by_id.get(m["id"])
            if slot is None:
                slot = {
                    "id": m["id"],
                    "label": m["label"],
                    "root_cause": m["root_cause"],
                    "fix_rule": m["fix_rule"],
                    "scenario": m["scenario"],
                    "count": 0,
                    "projects": set(),
                    "sessions": set(),
                    "timestamps": [],
                    "examples": [],
                }
                by_id[m["id"]] = slot
            slot["count"] += 1
            if s.get("project"):
                slot["projects"].add(s["project"])
            if s.get("session_id"):
                slot["sessions"].add(s["session_id"])
            if s.get("timestamp"):
                slot["timestamps"].append(s["timestamp"])
            if len(slot["examples"]) < 5:
                slot["examples"].append({
                    "project": s.get("project", ""),
                    "source": s.get("source", ""),
                    "prompt": s.get("full_prompt", "")[:150],
                    "timestamp": s.get("timestamp"),
                })
    result = []
    for slot in by_id.values():
        slot["project_count"] = len(slot["projects"])
        slot["session_count"] = len(slot["sessions"])
        slot["span_days"] = _span_days(slot["timestamps"])
        slot["projects"] = sorted(slot["projects"])
        del slot["sessions"]
        del slot["timestamps"]
        result.append(slot)
    # Rank by reach: recurring + widespread first, not just frequent.
    result.sort(key=lambda x: (x["project_count"], x["count"]), reverse=True)
    return result


def compute_recurring_categories(signals):
    """Coarse cross-session view over ALL frustration signals by category.

    Complements the anti-pattern library: it covers the signals that do NOT
    match a known pattern, surfacing which problem *types* keep recurring
    across projects and time. Root cause here is a theme, not a vetted rule —
    the LLM still deep-dives these.
    """
    by_cat = defaultdict(lambda: {"count": 0, "projects": set(),
                                  "sessions": set(), "timestamps": []})
    for s in signals:
        cat = s.get("category", "unknown")
        slot = by_cat[cat]
        slot["count"] += 1
        if s.get("project"):
            slot["projects"].add(s["project"])
        if s.get("session_id"):
            slot["sessions"].add(s["session_id"])
        if s.get("timestamp"):
            slot["timestamps"].append(s["timestamp"])
    result = []
    for cat, slot in by_cat.items():
        result.append({
            "category": cat,
            "count": slot["count"],
            "project_count": len(slot["projects"]),
            "session_count": len(slot["sessions"]),
            "span_days": _span_days(slot["timestamps"]),
        })
    result.sort(key=lambda x: (x["project_count"], x["count"]), reverse=True)
    return result


# ─── Frustration signal patterns (Layer 1 core) ──────────────

FRUSTRATION_CATEGORIES = {
    "fabrication": {
        "label": {"en": "AI fabrication", "zh": "AI 编造瞎猜"},
        "pattern": re.compile(
            # direct
            r"胡编乱造|瞎编|编的吧|瞎猜|别猜|不要猜|瞎说|乱说|胡说|你在编|你编的|捏造|杜撰"
            r"|fabricat|hallucin|making.?up|made.?up|invented"
            # polite
            r"|有依据吗|哪来的结论|你验证了吗|你确认过吗|这是你猜的"
            r"|where did you get|did you verify|is this accurate|based on what"
            r"|source.?for this|evidence|did you actually check"
        ),
        "meaning": "AI output false or unverified information",
    },
    "incorrect": {
        "label": {"en": "Incorrect output", "zh": "AI 做错了"},
        "pattern": re.compile(
            # direct
            r"不对|错了|搞错|弄错|改错|写错|放错|用错|选错"
            r"|wrong|incorrect|that'?s not|not right"
            # polite
            r"|好像不太对|跟我预期的不[太一]样|这个结果有[点些]问题|不太对劲|跟我想的不一样"
            r"|not quite|not exactly|doesn'?t look right|doesn'?t seem right"
            r"|not what I expected|not what I meant|not what I had in mind"
            r"|I was expecting|that'?s off|a bit off"
        ),
        "meaning": "AI output did not match user expectation",
    },
    "low_effort": {
        "label": {"en": "Shallow thinking", "zh": "AI 不够认真"},
        "pattern": re.compile(
            # direct
            r"仔细[想看看看]|深度思考|认真[一点些]|用心|好好[想看]|动动脑"
            r"|think.?hard|think.?deep|carefully|pay attention|more thought"
            # polite
            r"|能不能再想想|再[认仔]真[看想]看|你有没有仔细|草率了|太敷衍|太笼统|太粗糙|太表面"
            r"|could you reconsider|think about it more|look more carefully|a bit superficial"
            r"|too generic|too vague|too shallow|put more thought|not thorough"
            r"|didn'?t really think|half.?baked"
        ),
        "meaning": "User feels AI was lazy or lacked depth",
    },
    "repeated_mistake": {
        "label": {"en": "Repeated mistakes", "zh": "AI 重复犯错"},
        "pattern": re.compile(
            # direct
            r"又[来是错]|还是[这那]样|老是|不要老|反复|一直在"
            r"|again|keep|still|same mistake|same error"
            # polite
            r"|上次也[是这]样|之前就说过|说了好几遍了|还是没改|怎么又"
            r"|we.?ve been over this|already told you|mentioned this before|same issue"
            r"|didn'?t we fix this|thought we resolved|happening again"
        ),
        "meaning": "AI keeps making the same mistake",
    },
    "overreach": {
        "label": {"en": "Overreach", "zh": "越权操作"},
        "pattern": re.compile(
            # direct
            r"谁让你|我[没没有]说|我[没没有]让|我要的是|我说的是|不是让你|别[瞎乱]改|不要[随瞎乱]便"
            r"|didn'?t ask|not what I|don'?t change|never asked"
            # polite
            r"|超出范围了|我没要求这个|为什么要改这[个里]|多此一举|画蛇添足"
            r"|beyond.?scope|out of scope|I only asked for|why did you change"
            r"|I didn'?t mean for you to|went too far|more than I asked"
        ),
        "meaning": "AI exceeded instructions or misunderstood intent",
    },
    "undo_redo": {
        "label": {"en": "Undo / redo", "zh": "撤销重来"},
        "pattern": re.compile(
            # direct
            r"撤[销回]|回滚|重[来做写]|还原|恢复|全[部都]删|undo|revert|rollback|start over|redo|go back"
            # polite
            r"|换[个种]思路|换[个种]方[向式法]|要不重新来|从头开始|算了不要了"
            r"|different approach|try another way|start fresh|scrap this|let'?s try something else"
            r"|back to square one|discard|throw this away"
        ),
        "meaning": "AI output needs to be completely discarded",
    },
    "distrust": {
        "label": {"en": "Distrust", "zh": "质疑/不信任"},
        "pattern": re.compile(
            # direct
            r"你确[定认]|真的吗|靠谱吗|能[行用]吗|有[没]有问题"
            r"|are you sure|really\?|is that right|does that work"
            # polite
            r"|你看过[代代码]了吗|你读了吗|我[有点]怀疑|不太放心|感觉不太靠谱"
            r"|did you actually read|did you check|I'?m not (so )?sure|doesn'?t feel right"
            r"|I have doubts|not confident|can you double.?check|seems questionable"
        ),
        "meaning": "User doubts AI output accuracy",
    },
}


def classify_frustration(text):
    """Classify frustration signals. Returns [(category, matched_text)]."""
    hits = []
    for cat, info in FRUSTRATION_CATEGORIES.items():
        match = info["pattern"].search(text)
        if match:
            hits.append((cat, match.group()))
    return hits


# ─── Positive signal detection ──────────────────────────────────

POSITIVE_CATEGORIES = {
    "praise": {
        "label": {"en": "Praise / approval", "zh": "认可/夸赞"},
        "pattern": re.compile(
            r"[很挺非常]好|不错|可以|完美|正确|对了|牛|厉害|优秀|准确|满意|靠谱"
            r"|perfect|great|good|nice|exactly|correct|well done|awesome|impressive"
            r"|这次[很挺]好|比之前好|终于对了|这样[就对]|就是这[个样]|漂亮"
        ),
    },
    "trust_delegation": {
        "label": {"en": "Trust delegation", "zh": "信任委托"},
        "pattern": re.compile(
            r"你[自己直接].*[做弄改写搞处理决定判断]|交给你|你来[决定判断]|你看着[办弄]|按你[的说]"
            r"|自己想办法|你全权|放手[做干]|I trust you|up to you|your call|go ahead"
            r"|就按你说的|听你的|你拿主意"
        ),
    },
    "reuse_pattern": {
        "label": {"en": "Pattern reuse", "zh": "复用/引用已有方案"},
        "pattern": re.compile(
            r"参考[之前上次]|像[之上]次[那一]样|用[之上]次的|按[之上]次的|复用|沿用|跟之前一样"
            r"|same as before|like last time|reuse|follow the same|as we did"
            r"|之前的[方案思路做法]|还是[用那][之上]次"
        ),
    },
    "skill_invocation": {
        "label": {"en": "Skill / workflow invocation", "zh": "Skill/工作流调用"},
        "pattern": re.compile(
            r"使用.*skill|执行.*skill|skill.*自循环|用.*skill|跑.*skill"
            r"|/[a-z][\w-]{2,}|run.*skill|use.*skill|invoke.*skill"
        ),
    },
    "context_engineering": {
        "label": {"en": "Context engineering", "zh": "主动提供上下文"},
        "pattern": re.compile(
            r"\[Pasted text.*\]|\[Image.*\]|参考.*https?://|读取.*\.md|看一下.*代码"
            r"|这是.*日志|这是.*报错|这是.*数据|以下是|如下[：:]"
        ),
    },
}


def classify_positive(text):
    """Classify positive signals. Returns [(category, matched_text)]."""
    hits = []
    for cat, info in POSITIVE_CATEGORIES.items():
        match = info["pattern"].search(text)
        if match:
            hits.append((cat, match.group()))
    return hits


def scan_positive_signals(prompts):
    """Scan all prompts for positive interaction signals."""
    signals = []
    category_counts = Counter()
    neg_re = re.compile(r'不对|错了|瞎|重[来做]|撤销|恢复|胡编|别瞎|不是|不要|不行')

    for p in prompts:
        text = p["text"].strip()
        if not text or text.startswith("/") or text.startswith("<") or len(text) <= 3:
            continue
        if neg_re.search(text):
            continue
        hits = classify_positive(text)
        for cat, matched in hits:
            category_counts[cat] += 1
            signals.append({
                "category": cat,
                "matched": matched,
                "full_prompt": text,
                "source": p.get("source"),
                "source_id": p.get("source_id"),
                "project": p.get("project", ""),
                "session_id": p.get("session_id", ""),
                "timestamp": p.get("timestamp"),
            })

    seen = set()
    deduped = []
    for s in signals:
        key = (s.get("source_id"), s["session_id"], s["category"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return deduped, dict(category_counts)


# ─── User cognitive pattern detection ───────────────────────────

COGNITIVE_PATTERNS = {
    "depth_demand": {
        "label": {"en": "Demands deep thinking", "zh": "要求深度思考"},
        "pattern": re.compile(r"深度思考|仔细[想看分析]|认真[点一]|动动脑|用心|全面分析|彻底|think deeply|think harder|carefully"),
    },
    "quality_standard": {
        "label": {"en": "High quality bar", "zh": "高质量标准"},
        "pattern": re.compile(r"审美|好看|优雅|专业|高质量|生产[环级]|不够好|太[差丑简陋粗糙]|品质|精细|打磨"),
    },
    "autonomy_expectation": {
        "label": {"en": "Expects AI autonomy", "zh": "期望AI自主"},
        "pattern": re.compile(r"自己[想做弄决定判断]|别[问老]是问|不要.*问我|自[主动]|主动|智[慧能]一[些点]|别等我"),
    },
    "persistence_demand": {
        "label": {"en": "Demands persistence", "zh": "要求坚持/重试"},
        "pattern": re.compile(r"反复[重尝试]|[重再]试|不要放弃|想办法|多试[几几种]|穷举|别.*放弃|keep trying|don.?t give up"),
    },
    "holistic_thinking": {
        "label": {"en": "Holistic / system thinking", "zh": "全局/系统思维"},
        "pattern": re.compile(r"全[局面]|整体|一致[性]|统一|保[持鲜]|端到端|闭环|体系|系统[性地化]|全链路"),
    },
    "asset_mindset": {
        "label": {"en": "Asset / accumulation mindset", "zh": "资产/沉淀思维"},
        "pattern": re.compile(r"沉淀|积累|可复用|资产|长期|持久|知识[库管理]|经验.*[总结提炼]|方法论"),
    },
}


def detect_cognitive_patterns(prompts):
    """Detect user's cognitive patterns from prompt text."""
    pattern_counts = Counter()
    pattern_examples = defaultdict(list)

    for p in prompts:
        text = p["text"].strip()
        if not text or text.startswith("/") or text.startswith("<") or len(text) <= 5:
            continue
        for pat_name, info in COGNITIVE_PATTERNS.items():
            if info["pattern"].search(text):
                pattern_counts[pat_name] += 1
                if len(pattern_examples[pat_name]) < 3:
                    pattern_examples[pat_name].append(text[:150])

    total_prompts = sum(1 for p in prompts if len(p["text"].strip()) > 5
                        and not p["text"].startswith("/") and not p["text"].startswith("<"))

    result = {}
    for pat_name, count in pattern_counts.most_common():
        result[pat_name] = {
            "label": COGNITIVE_PATTERNS[pat_name]["label"],
            "count": count,
            "rate": round(count / max(total_prompts, 1) * 100, 1),
            "examples": pattern_examples[pat_name],
        }
    return result


# ─── Data loading: Provider-based ─────────────────────────────

# ─── Layer 1: Frustration signal scanning ─────────────────────

def scan_frustration_signals(prompts):
    """Scan all prompts, collect frustration signals."""
    signals = []
    category_counts = Counter()

    for i, p in enumerate(prompts):
        hits = classify_frustration(p["text"])
        if hits:
            for cat, matched in hits:
                category_counts[cat] += 1
                signals.append({
                    "category": cat,
                    "matched_text": matched,
                    "full_prompt": p["text"][:200],
                    "source": p.get("source", "unknown"),
                    "source_id": p.get("source_id", "unknown"),
                    "project": p["project"],
                    "session_id": p["session_id"],
                    "timestamp": p["timestamp"],
                    "prompt_index": i,
                })

    # Dedup: keep first per session+category
    seen = set()
    deduped = []
    for s in signals:
        key = (s.get("source_id"), s["session_id"], s["category"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return deduped, dict(category_counts)


# ─── Layer 2: Targeted deep-dive ─────────────────────────────

def deep_dive_incidents(signals, max_incidents=8):
    """Targeted context analysis for frustration signals."""
    priority_order = [
        "fabrication", "incorrect", "low_effort",
        "overreach", "undo_redo", "repeated_mistake", "distrust",
    ]

    by_cat = defaultdict(list)
    for s in signals:
        by_cat[s["category"]].append(s)

    selected = []
    for cat in priority_order:
        items = by_cat.get(cat, [])
        if items and len(selected) < max_incidents:
            selected.append(items[0])
            if len(items) > 2 and len(selected) < max_incidents:
                selected.append(items[len(items)//2])

    incidents = []
    for s in selected[:max_incidents]:
        # Determine turn number
        turn = None
        prompts_in_session = []
        if s.get("source_id") == "claude-code":
            try:
                with open(CLAUDE_DIR / "history.jsonl") as f:
                    for line in f:
                        obj = json.loads(line)
                        if obj.get("sessionId") == s["session_id"]:
                            prompts_in_session.append(obj.get("display", ""))
            except: pass

        for i, text in enumerate(prompts_in_session):
            if text[:50] == s["full_prompt"][:50]:
                turn = i + 1
                break

        ctx = extract_context(s["session_id"], s["full_prompt"], radius=4, source=s.get("source_id"))

        # Match against the AI-side library. Scan both the correction text and
        # nearby user turns for better recall.
        ctx_user_text = ""
        if isinstance(ctx, dict):
            for m in ctx.get("context", []) or []:
                if m.get("role") == "user":
                    ctx_user_text += " " + m.get("content", "")
        matched_ap = match_antipatterns(s.get("full_prompt", ""), ctx_user_text)

        incidents.append({
            **s,
            "turn_in_session": turn,
            "total_turns_in_session": len(prompts_in_session),
            "context": ctx,
            "matched_antipatterns": matched_ap,
        })

    return incidents


# ─── Helper statistics ──────────────────────────────────────

def compute_session_stats(prompts):
    """Basic session statistics."""
    sessions = defaultdict(list)
    for p in prompts:
        if p["session_id"]:
            sessions[(p.get("source_id", "unknown"), p["session_id"])].append(p)

    turns_list = [len(v) for v in sessions.values()]
    return {
        "total_sessions": len(sessions),
        "avg_turns": round(mean(turns_list), 1) if turns_list else 0,
        "max_turns": max(turns_list) if turns_list else 0,
        "turns_distribution": {
            "quick_1_5": sum(1 for t in turns_list if t <= 5),
            "medium_6_15": sum(1 for t in turns_list if 6 <= t <= 15),
            "deep_16_30": sum(1 for t in turns_list if 16 <= t <= 30),
            "marathon_30plus": sum(1 for t in turns_list if t > 30),
        },
    }


_MODEL_SOURCES = ("claude-code", "codex", "qoder")


def compute_model_stats(prompts, signals):
    """Extract per-model prompt counts and frustration stats from session JSONL."""
    model_prompts = Counter()
    session_models = {}

    for p in prompts:
        sid = p.get("session_id", "")
        source_id = p.get("source_id", "")
        if not sid or source_id not in _MODEL_SOURCES:
            continue
        if sid in session_models:
            model_prompts[session_models[sid]] += 1
            continue
        model = extract_model(source_id, sid, p.get("metadata", {}))
        if model:
            session_models[sid] = model
            model_prompts[model] += 1
        if sid in session_models:
            model_prompts[session_models[sid]] += 1

    if not model_prompts:
        return {}

    model_frustration = Counter()
    for s in signals:
        sid = s.get("session_id", "")
        model = session_models.get(sid)
        if model:
            model_frustration[model] += 1

    result = {}
    for model, count in model_prompts.most_common(10):
        frust = model_frustration.get(model, 0)
        result[model] = {
            "total_prompts": count,
            "frustration_count": frust,
            "frustration_rate": round(frust / max(count, 1) * 100, 1),
        }
    return result


def compute_high_frequency_phrases(prompts, top_n=10):
    """Find high-frequency phrases the user repeats (CJK + English)."""
    phrase_counter = Counter()
    for p in prompts:
        text = p["text"].strip()
        if len(text) < 4 or text.startswith("/") or text.startswith("<"):
            continue
        for ph in re.findall(r'[一-鿿]{2,6}', text):
            phrase_counter[ph] += 1
        for ph in re.findall(r'\b[a-zA-Z]{3,}\s+[a-zA-Z]{3,}(?:\s+[a-zA-Z]{3,})?\b', text.lower()):
            phrase_counter[ph] += 1

    stopwords = {
        "一下", "这个", "那个", "什么", "怎么", "不要", "可以", "需要", "已经",
        "现在", "然后", "但是", "如果", "因为", "所以", "或者", "还有", "以及",
        "之前", "之后", "一个", "没有", "不是", "的话", "时候", "问题",
        "the file", "this file", "the code", "this code", "can you",
        "please help", "help me", "i want", "i need", "make sure",
        "let me", "want to", "need to", "how to", "what is",
    }
    filtered = [(ph, c) for ph, c in phrase_counter.most_common(80)
                if ph not in stopwords and c >= 3]
    return filtered[:top_n]


# ─── Prompt quality scoring (5-dimension model) ────────────────

_GOAL_VERBS = re.compile(
    r"我要|需要|目标|期望|希望|要求|实现|完成|修复|修改|添加|删除|优化|重构|部署|迁移|接入|开发|写|改|加|删|查|看|跑|测"
    r"|implement|fix|add|remove|create|update|delete|refactor|deploy|build|write|check|debug|test|run|migrate"
)
_CONTEXT_KEYWORDS = re.compile(
    r"因为|原因|背景|之前|目前|问题是|上下文|现在|由于|为了|鉴于|根据|参考|基于"
    r"|because|since|currently|the issue is|context|background|previously|given that|based on|referring to"
)
_FILE_REF = re.compile(
    r"(?:/[\w./-]+\.[\w]+|~/[\w./-]+|[\w]+\.(?:java|py|ts|js|tsx|jsx|md|json|xml|yml|yaml|html|css|sh|sql|go|rs|kt|swift|rb|php|c|cpp|h)(?::\d+)?|[\w]+#[\w]+)"
)
_CODE_SYMBOL = re.compile(r"[A-Z][a-zA-Z0-9]+[.#][a-zA-Z]\w+")


def score_prompt_quality(text):
    """Score a single prompt on 5 dimensions (0-100). Returns (score, breakdown)."""
    text = text.strip()
    if not text or text.startswith("/") or len(text) <= 2:
        return None, None

    length = len(text)
    if length < 10:
        d1 = 0
    elif length < 20:
        d1 = 5
    elif length < 50:
        d1 = 10
    elif length <= 500:
        d1 = 20
    else:
        d1 = 15

    d2 = 25 if (_FILE_REF.search(text) or _CODE_SYMBOL.search(text)) else 0

    goal_matches = _GOAL_VERBS.findall(text)
    d3 = 20 if goal_matches else 0

    d4 = 20 if _CONTEXT_KEYWORDS.search(text) else 0

    goal_count = len(set(goal_matches))
    if goal_count == 0:
        d5 = 0
    elif goal_count <= 2:
        d5 = 15
    elif goal_count == 3:
        d5 = 10
    else:
        d5 = 5

    total = d1 + d2 + d3 + d4 + d5
    breakdown = {"length": d1, "reference": d2, "goal": d3, "context": d4, "focus": d5}
    return total, breakdown


def compute_prompt_quality_stats(prompts):
    """Compute how much information prompts hand the AI to act on.

    This measures FORM (can the AI start without guessing?), not whether a
    prompt is 'good'. Terse expert commands, slash commands, and casual
    follow-ups are legitimate and are described neutrally, not scored as 'bad'.
    """
    scores = []
    sparse = []
    underspecified_count = 0

    for p in prompts:
        text = p["text"].strip()
        if not text or text.startswith("/") or text.startswith("<") or len(text) <= 2:
            continue
        score, breakdown = score_prompt_quality(text)
        if score is None:
            continue
        scores.append(score)
        if score < 40:
            missing = [k for k, v in breakdown.items() if v == 0]
            sparse.append({"text": text[:100], "score": score, "missing": missing,
                           "project": p.get("project", ""), "source": p.get("source", "")})
        if len(text) > 10 and not _FILE_REF.search(text) and not _GOAL_VERBS.search(text):
            underspecified_count += 1

    if not scores:
        return {}

    # Neutral, descriptive bands — NOT value judgments. A "minimal" prompt is
    # often perfectly fine (e.g. a terse command an expert gives on purpose).
    dist = {"complete": 0, "adequate": 0, "sparse": 0, "minimal": 0}
    for s in scores:
        if s >= 80:
            dist["complete"] += 1
        elif s >= 60:
            dist["adequate"] += 1
        elif s >= 40:
            dist["sparse"] += 1
        else:
            dist["minimal"] += 1

    sparse.sort(key=lambda x: x["score"])
    return {
        "metric_name": {"zh": "信息完整度", "en": "Information completeness"},
        "note": {
            "zh": "衡量 prompt 是否给了 AI 足够信息直接开工（形式层面），不是判断 prompt 好坏。简短指令、斜杠命令、口语化追问本身没问题，不要当成缺点。",
            "en": "Measures whether a prompt gives the AI enough to start without guessing (a form signal), NOT whether the prompt is 'good'. Terse commands, slash commands and casual follow-ups are legitimate — do not treat them as flaws."
        },
        "avg_score": round(sum(scores) / len(scores), 1),
        "total_scored": len(scores),
        "band_labels": {
            "complete": {"zh": "信息充分", "en": "Complete"},
            "adequate": {"zh": "基本够用", "en": "Adequate"},
            "sparse": {"zh": "偏简", "en": "Sparse"},
            "minimal": {"zh": "极简", "en": "Minimal"},
        },
        "score_distribution": dist,
        "underspecified_rate": round(underspecified_count / max(len(scores), 1) * 100, 1),
        "top_sparse": sparse[:5],
    }


# ─── Efficiency metrics ─────────────────────────────────────────

_NEGATION_KEYWORDS = re.compile(
    r"不对|不是|重[来做]|改一下|错了|换[一个种]|别这样|不要这[样么个]|重新"
    r"|wrong|incorrect|undo|revert|redo|not right|start over|go back|that'?s not"
)


def compute_efficiency_stats(prompts):
    """Compute conversation efficiency metrics."""
    sessions = defaultdict(list)
    for p in prompts:
        sid = p.get("session_id", "")
        if sid:
            sessions[sid].append(p)

    if not sessions:
        return {}

    total_sessions = len(sessions)
    first_success = 0
    negation_sessions = 0

    for sid, ps in sessions.items():
        real = [p for p in ps if not p["text"].startswith("/") and len(p["text"]) > 2
                and not p["text"].startswith("<")]
        has_negation = any(_NEGATION_KEYWORDS.search(p["text"]) for p in real)
        if has_negation:
            negation_sessions += 1
        if len(real) <= 3 and not has_negation:
            first_success += 1

    first_success_rate = round(first_success / max(total_sessions, 1) * 100, 1)
    negation_rate = round(negation_sessions / max(total_sessions, 1) * 100, 1)
    efficiency_score = round(
        (first_success / max(total_sessions, 1)) * 40
        + (1 - negation_sessions / max(total_sessions, 1)) * 30
        + 0.5 * 30, 1
    )

    return {
        "first_success_rate": first_success_rate,
        "negation_rate": negation_rate,
        "efficiency_score": efficiency_score,
        "total_sessions": total_sessions,
        "first_success_count": first_success,
        "negation_session_count": negation_sessions,
    }


# ─── Task type & collaboration style classification ──────────────

_TASK_TYPE_PATTERNS = [
    ("coding", re.compile(
        r"写代码|实现|开发|编码|重构|refactor|封装|抽象|加(个|一个|上)|改成|改为"
        r"|新增|删除|优化.*(代码|逻辑|性能)|字段|参数|函数|方法|类|模块|组件|接口"
        r"|前端|后端|页面|样式|sql|查询|脚本|迁移|集成|对接|引入|依赖"
        r"|function|method|class|interface|import|def |enum|DTO|Service|Controller|API")),
    ("debugging", re.compile(
        r"bug|error|报错|异常|不工作|fix|debug|trace|排查|崩溃|失败|卡住|卡死"
        r"|不生效|不好使|定位|复现|日志|log|stack|堆栈|为什么|为啥|怎么回事"
        r"|不对劲|没生效|超时|null|空指针|挂了|跑不[起通]|修复|修一下")),
    ("design", re.compile(
        r"方案|架构|系分|系统设计|设计一?[个下]|技术选型|链路梳理|拆解|评审"
        r"|怎么设计|如何设计|建模|edesign|流程图|时序图")),
    ("research", re.compile(
        r"搜索|调[查研]|查一下|对比|评估|怎么做|是什么|全网检索|了解一下|调研|选型"
        r"|有没有|能不能|可不可以|可行|推荐|建议|区别|优缺点|原理|机制|研究|找找")),
    ("writing", re.compile(
        r"写文[章档]|文档|总结|报告|博客|README|沉淀|记录|公众号|PPT|汇报"
        r"|文案|讲解|介绍|说明|润色|翻译|大纲|摘要")),
    ("configuration", re.compile(
        r"配置|安装|部署|环境|hook|settings|config|setup|install|deploy|发布|上线"
        r"|权限|账号|密钥|token|证书|依赖版本|升级.*版本")),
]


def classify_task_type(text):
    """Classify a prompt's task type by keyword matching."""
    for task_type, pattern in _TASK_TYPE_PATTERNS:
        if pattern.search(text):
            return task_type
    return "other"


_COLLAB_STYLE_PATTERNS = [
    ("delegation", re.compile(r"帮我|去做|给我|直接做|你来|你去|帮忙|替我|help me|do it|just do")),
    ("collaborative", re.compile(r"我们|一起|想想|讨论|你觉得|商量|探讨|let'?s|what do you think|together|discuss")),
    ("review", re.compile(r"检查|review|看看|审[一查]|cr|code review|check|inspect|verify|验证")),
]


def classify_collab_style(text):
    """Classify collaboration style by keyword matching."""
    for style, pattern in _COLLAB_STYLE_PATTERNS:
        if pattern.search(text):
            return style
    return "directive"


def compute_classification_stats(prompts):
    """Compute task type and collaboration style distributions.

    Placeholder prompts (pasted text / images) carry no analyzable text, so they
    are excluded from the task-type denominator and reported separately rather
    than inflating an "other" bucket that looks like classification failure.
    """
    task_dist = Counter()
    style_dist = Counter()
    unclassifiable = 0
    for p in prompts:
        text = p["text"].strip()
        if not text or text.startswith("/") or text.startswith("<") or len(text) <= 2:
            continue
        if text.startswith("[Pasted") or text.startswith("[Image") or text.startswith("[图"):
            unclassifiable += 1
            continue
        task_dist[classify_task_type(text)] += 1
        style_dist[classify_collab_style(text)] += 1
    return {
        "task_type": dict(task_dist.most_common()),
        "collab_style": dict(style_dist.most_common()),
        "unclassifiable_pasted": unclassifiable,
    }


# ─── Session-level anti-pattern detection ────────────────────────

def detect_session_antipatterns(prompts):
    """Detect user-side anti-patterns at the session level."""
    sessions = defaultdict(list)
    for p in prompts:
        sid = p.get("session_id", "")
        if sid:
            sessions[sid].append(p)

    results = []
    type_counts = Counter()

    for sid, ps in sessions.items():
        real = [p for p in ps if not p["text"].startswith("/") and len(p["text"]) > 2
                and not p["text"].startswith("<")]
        if not real:
            continue

        project = real[0].get("project", "unknown")
        source = real[0].get("source", "unknown")
        detected = []

        # 1. Negation loop: ≥2 consecutive negation prompts
        consecutive_neg = 0
        max_consecutive = 0
        for p in real:
            if _NEGATION_KEYWORDS.search(p["text"]):
                consecutive_neg += 1
                max_consecutive = max(max_consecutive, consecutive_neg)
            else:
                consecutive_neg = 0
        if max_consecutive >= 2:
            detected.append("negation_loop")

        # 2. Short commands: ≥3 prompts < 10 chars (non-slash)
        short_count = sum(1 for p in real if len(p["text"].strip()) < 10)
        if short_count >= 3:
            detected.append("short_commands")

        # 3. Session bloat: > 50 turns
        if len(real) > 50:
            detected.append("session_bloat")

        # 4. Goal drift: task type switches ≥ 3
        if len(real) >= 4:
            types = [classify_task_type(p["text"]) for p in real]
            switches = sum(1 for i in range(1, len(types)) if types[i] != types[i - 1])
            if switches >= 3:
                detected.append("goal_drift")

        for d in detected:
            type_counts[d] += 1
            if len(results) < 20:
                results.append({"session_id": sid, "type": d, "project": project,
                                "source": source, "turns": len(real)})

    return {
        "total_detected": sum(type_counts.values()),
        "by_type": dict(type_counts),
        "affected_sessions": results[:10],
    }


def analyze(days=None, project=None, deep=True, sources=None):
    prompts = load_prompts(days=days, project=project, sources=sources)
    if not prompts:
        return {"error": "no_conversation_data_found", "data_sources": discover_sources()}

    # Layer 1
    signals, category_counts = scan_frustration_signals(prompts)

    # Layer 2 (optional)
    incidents = []
    if deep and signals:
        incidents = deep_dive_incidents(signals, max_incidents=6)

    # Anti-pattern library coverage across ALL frustration signals (not just the
    # deep-dived sample). Groups incidents by known root cause across sessions
    # and projects, and carries the curated fix_rule for each.
    antipattern_library = scan_antipattern_matches(signals)
    # Coarse recurring-theme view by category, covering signals that don't match
    # a known pattern — surfaces what keeps recurring across projects and time.
    recurring_categories = compute_recurring_categories(signals)

    # Positive signals
    positive_signals, positive_counts = scan_positive_signals(prompts)

    # Cognitive patterns
    cognitive_patterns = detect_cognitive_patterns(prompts)

    # Helper stats
    session_stats = compute_session_stats(prompts)
    model_stats = compute_model_stats(prompts, signals)
    high_freq = compute_high_frequency_phrases(prompts)
    prompt_quality = compute_prompt_quality_stats(prompts)
    efficiency = compute_efficiency_stats(prompts)
    classifications = compute_classification_stats(prompts)
    antipatterns = detect_session_antipatterns(prompts)

    # Deterministic, session-level health so the headline number is stable across
    # runs (not re-derived by the LLM each time). Health = share of sessions with
    # no correction. Session-level, not per-prompt, so long sessions don't dilute.
    frustrated_sessions = {(s.get("source_id"), s.get("session_id"))
                           for s in signals if s.get("session_id")}
    _total_sess = session_stats["total_sessions"]
    health_score = round(100 - len(frustrated_sessions) / max(_total_sess, 1) * 100)

    # Per-project stats: total prompts + frustration count + rate
    project_prompts = Counter(p["project"] for p in prompts)
    project_frustration = Counter()
    for s in signals:
        project_frustration[s["project"]] += 1
    project_stats = {}
    for proj, frust_count in project_frustration.most_common(10):
        total = project_prompts.get(proj, 0)
        project_stats[proj] = {
            "total_prompts": total,
            "frustration_count": frust_count,
            "frustration_rate": round(frust_count / max(total, 1) * 100, 1),
        }

    return {
        "period": {
            "start": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d") if days else prompts[0]["timestamp"][:10] if prompts and prompts[0].get("timestamp") else "unknown",
            "end": datetime.now().strftime("%Y-%m-%d"),
            "all_time": days is None,
        },
        "overview": {
            "total_prompts": len(prompts),
            "total_sessions": session_stats["total_sessions"],
            "health_score": health_score,
            "health_basis": {
                "zh": "健康度 = 无纠正的 session 占比（会话级，确定性）",
                "en": "Health = share of sessions with zero corrections (session-level, deterministic)",
            },
            "frustrated_session_count": len(frustrated_sessions),
            "data_sources": discover_sources(),
            "source_prompt_counts": dict(Counter(p.get("source", "unknown") for p in prompts)),
        },
        "category_labels": {k: v["label"] for k, v in FRUSTRATION_CATEGORIES.items()},
        "layer1_frustration": {
            "total_signals": len(signals),
            "category_counts": category_counts,
            "frustration_rate": round(len(signals) / max(len(prompts), 1) * 100, 1),
            "top_projects": project_stats,
            "signals_sample": [
                {"category": s["category"], "prompt": s["full_prompt"][:150],
                 "source": s.get("source"), "project": s["project"], "timestamp": s["timestamp"]}
                for s in signals[:20]
            ],
        },
        "model_stats": model_stats,
        "layer2_incidents": [
            {
                "category": inc["category"],
                "prompt": inc["full_prompt"][:200],
                "source": inc.get("source"),
                "project": inc["project"],
                "turn": inc.get("turn_in_session"),
                "total_turns": inc.get("total_turns_in_session"),
                "context": inc.get("context"),
                "matched_antipatterns": inc.get("matched_antipatterns", []),
            }
            for inc in incidents
        ],
        "antipattern_library": antipattern_library,
        "recurring_categories": recurring_categories,
        "session_stats": session_stats,
        "high_frequency_phrases": high_freq,
        "prompt_quality": prompt_quality,
        "efficiency": efficiency,
        "task_type_distribution": classifications.get("task_type", {}),
        "collab_style_distribution": classifications.get("collab_style", {}),
        "unclassifiable_pasted": classifications.get("unclassifiable_pasted", 0),
        "session_antipatterns": antipatterns,
        "positive_signals": {
            "total": len(positive_signals),
            "category_counts": positive_counts,
            "category_labels": {k: v["label"] for k, v in POSITIVE_CATEGORIES.items()},
            "signals_sample": [
                {"category": s["category"], "prompt": s["full_prompt"][:150],
                 "source": s.get("source"), "project": s["project"]}
                for s in positive_signals[:20]
            ],
        },
        "cognitive_patterns": cognitive_patterns,
    }


def scope_check():
    """Stage 0: Determine analysis scope."""
    sources = discover_sources()
    counts = {}
    for label, days in [("30d", 30), ("60d", 60), ("90d", 90)]:
        prompts = load_prompts(days=days)
        counts[label] = len(prompts)

    recommended = 60
    if counts["60d"] > 3000:
        recommended = 30
    elif counts["60d"] < 300:
        recommended = 180

    return {
        "data_sources": sources,
        "prompt_counts": counts,
        "source_counts_60d": dict(Counter(p.get("source", "unknown") for p in load_prompts(days=60))),
        "recommended_days": recommended,
        "reason": f"60d has {counts['60d']} prompts" + (
            ", too many — shrink to 30d" if recommended == 30 else
            ", too few — expand to 180d" if recommended == 180 else
            ", good volume"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="AI Interaction Analyzer v4")
    parser.add_argument("--mode", choices=["analyze", "setup", "signals", "scope", "context"], default="analyze")
    parser.add_argument("--days", type=int, default=None, help="analysis window in days (omit for all data)")
    parser.add_argument("--project", type=str, default=None)
    parser.add_argument("--source", type=str, default=None, help="comma-separated source ids, e.g. claude-code,codex")
    parser.add_argument("--session", type=str, default=None, help="session ID for context extraction")
    parser.add_argument("--prompt", type=str, default=None, help="target prompt text for context extraction")
    parser.add_argument("--radius", type=int, default=4, help="context radius (default ±4 turns)")
    parser.add_argument("--no-deep", action="store_true")
    args = parser.parse_args()

    if args.mode == "setup":
        print(json.dumps({"data_sources": discover_sources(), "python": sys.version,
                           "frustration_categories": list(FRUSTRATION_CATEGORIES.keys())},
                          ensure_ascii=False, indent=2))

    elif args.mode == "scope":
        result = scope_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.mode == "signals":
        prompts = load_prompts(days=args.days, project=args.project, sources=args.source)
        signals, counts = scan_frustration_signals(prompts)
        # Also find positive signals (successful sessions)
        sessions = defaultdict(list)
        neg_re = re.compile(r'不对|错了|瞎|重[来做]|撤销|恢复|胡编|别瞎')
        for p in prompts:
            if p["session_id"]:
                sessions[(p.get("source_id", "unknown"), p["session_id"])].append(p)
        quick_wins = []
        for (source_id, sid), ps in sessions.items():
            real = [p for p in ps if not p["text"].startswith("/") and len(p["text"]) > 10
                    and not p["text"].startswith("<")]
            if 1 <= len(real) <= 5 and not any(neg_re.search(p["text"]) for p in real):
                if real and len(real[0]["text"]) > 30:
                    quick_wins.append({
                        "session_id": sid,
                        "source_id": source_id,
                        "turns": len(real),
                        "first_prompt": real[0]["text"][:200],
                        "source": real[0].get("source"),
                        "project": real[0]["project"],
                    })

        pos_signals, pos_counts = scan_positive_signals(prompts)
        cog_patterns = detect_cognitive_patterns(prompts)

        pq = compute_prompt_quality_stats(prompts)
        eff = compute_efficiency_stats(prompts)
        cls = compute_classification_stats(prompts)
        ap = detect_session_antipatterns(prompts)

        print(json.dumps({
            "total_prompts": len(prompts),
            "frustration": {"total": len(signals), "categories": counts,
                "signals": [{"cat": s["category"], "text": s["full_prompt"][:200],
                             "source": s.get("source"), "project": s["project"],
                             "session_id": s["session_id"]}
                            for s in signals]},
            "positive": {"total": len(pos_signals), "categories": pos_counts,
                "category_labels": {k: v["label"] for k, v in POSITIVE_CATEGORIES.items()},
                "signals": [{"cat": s["category"], "text": s["full_prompt"][:200],
                             "source": s.get("source"), "project": s["project"],
                             "session_id": s["session_id"]}
                            for s in pos_signals[:20]]},
            "cognitive_patterns": cog_patterns,
            "success": {"total": len(quick_wins),
                "sessions": quick_wins[:10]},
            "prompt_quality_summary": {
                "metric_name": pq.get("metric_name"),
                "avg_score": pq.get("avg_score"),
                "distribution": pq.get("score_distribution"),
                "underspecified_rate": pq.get("underspecified_rate"),
            } if pq else None,
            "task_type_distribution": cls.get("task_type", {}),
            "collab_style_distribution": cls.get("collab_style", {}),
            "efficiency_summary": {
                "first_success_rate": eff.get("first_success_rate"),
                "negation_rate": eff.get("negation_rate"),
                "efficiency_score": eff.get("efficiency_score"),
            } if eff else None,
            "session_antipatterns_summary": {
                "total": ap.get("total_detected", 0),
                "by_type": ap.get("by_type", {}),
            } if ap else None,
        }, ensure_ascii=False, indent=2))

    elif args.mode == "context":
        if not args.session or not args.prompt:
            print(json.dumps({"error": "requires --session and --prompt arguments"}, ensure_ascii=False))
            sys.exit(1)
        result = extract_context(args.session, args.prompt, radius=args.radius, source=args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:  # analyze
        result = analyze(days=args.days, project=args.project, deep=not args.no_deep, sources=args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

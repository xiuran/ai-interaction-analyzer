#!/usr/bin/env bash
set -euo pipefail

# AI Interaction Analyzer — Environment check & auto-install
# Run once on a new machine to complete setup

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_NAME="ai-interaction-analyzer"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"

echo "═══════════════════════════════════════════════"
echo "  AI Interaction Analyzer — Setup"
echo "═══════════════════════════════════════════════"
echo ""

# ─── Step 1: Python check ───────────────────────────────────

check_python() {
    if command -v python3 &>/dev/null; then
        PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 8 ]]; then
            echo "✅ Python $PY_VER ($(which python3))"
            return 0
        else
            echo "⚠️  Python $PY_VER is too old, need 3.8+"
        fi
    else
        echo "❌ python3 not found"
    fi

    if command -v brew &>/dev/null; then
        echo "   → Installing Python via brew..."
        brew install python@3.12
        echo "✅ Python installed"
    elif command -v apt-get &>/dev/null; then
        echo "   → Installing Python via apt..."
        sudo apt-get update && sudo apt-get install -y python3
        echo "✅ Python installed"
    else
        echo "❌ Cannot auto-install Python. Please install Python 3.8+ manually."
        echo "   macOS: brew install python"
        echo "   Ubuntu: sudo apt install python3"
        exit 1
    fi
}

# ─── Step 2: Create symlink ─────────────────────────────────

setup_symlink() {
    mkdir -p "$CLAUDE_SKILLS_DIR"

    if [[ -L "$CLAUDE_SKILLS_DIR/$SKILL_NAME" ]]; then
        CURRENT_TARGET=$(readlink "$CLAUDE_SKILLS_DIR/$SKILL_NAME")
        if [[ "$CURRENT_TARGET" == "$SKILL_DIR" ]]; then
            echo "✅ Symlink already correct"
            return 0
        else
            echo "⚠️  Symlink points to $CURRENT_TARGET, updating to $SKILL_DIR"
            rm "$CLAUDE_SKILLS_DIR/$SKILL_NAME"
        fi
    elif [[ -e "$CLAUDE_SKILLS_DIR/$SKILL_NAME" ]]; then
        echo "⚠️  $CLAUDE_SKILLS_DIR/$SKILL_NAME exists but is not a symlink, skipping"
        return 0
    fi

    ln -sf "$SKILL_DIR" "$CLAUDE_SKILLS_DIR/$SKILL_NAME"
    echo "✅ Symlink created: $CLAUDE_SKILLS_DIR/$SKILL_NAME → $SKILL_DIR"
}

# ─── Step 3: Register SessionEnd Hook ────────────────────────

setup_hook() {
    local SETTINGS_FILE="$HOME/.claude/settings.json"
    local HOOK_CMD="python3 $SKILL_DIR/scripts/mini_analyzer.py"

    if [[ ! -f "$SETTINGS_FILE" ]]; then
        echo "⚠️  $SETTINGS_FILE not found, skipping hook registration"
        echo "   Manual setup: add to hooks.SessionEnd: command: '$HOOK_CMD'"
        return 0
    fi

    if grep -q "mini_analyzer.py" "$SETTINGS_FILE" 2>/dev/null; then
        echo "✅ SessionEnd hook already registered"
        return 0
    fi

    echo "ℹ️  SessionEnd hook not registered"
    echo "   Add this to ~/.claude/settings.json under hooks.SessionEnd:"
    echo ""
    echo "   {\"hooks\": [{\"type\": \"command\", \"command\": \"$HOOK_CMD\", \"timeout\": 3, \"async\": true}]}"
    echo ""
    echo "   (Auto-modifying settings.json is risky, manual setup recommended)"
}

# ─── Step 4: Data source detection ───────────────────────────

detect_sources() {
    echo ""
    echo "── Data Sources ────────────────────────────────"
    echo ""

    local found=0

    if [[ -f "$HOME/.claude/history.jsonl" ]]; then
        local count=$(wc -l < "$HOME/.claude/history.jsonl" | tr -d ' ')
        echo "✅ Claude Code     — $count prompts"
        found=$((found + 1))
    else
        echo "○  Claude Code     — not detected"
    fi

    if [[ -f "$HOME/.codex/history.jsonl" ]]; then
        local count=$(wc -l < "$HOME/.codex/history.jsonl" | tr -d ' ')
        echo "✅ Codex CLI       — $count prompts"
        found=$((found + 1))
    else
        echo "○  Codex CLI       — not detected"
    fi

    if [[ -d "$HOME/Library/Application Support/Cursor" ]]; then
        echo "✅ Cursor          — data directory found"
        found=$((found + 1))
    else
        echo "○  Cursor          — not detected"
    fi

    local cline_dir=$(find "$HOME/.vscode/extensions" -maxdepth 1 -name "saoudrizwan.claude-dev-*" 2>/dev/null | head -1)
    if [[ -n "$cline_dir" ]]; then
        echo "✅ Cline           — detected"
        found=$((found + 1))
    else
        echo "○  Cline           — not detected"
    fi

    if [[ -d "$HOME/.gemini" ]]; then
        echo "✅ Gemini CLI      — detected"
        found=$((found + 1))
    else
        echo "○  Gemini CLI      — not detected"
    fi

    if [[ -d "$HOME/.config/github-copilot" ]]; then
        echo "✅ GitHub Copilot  — detected"
        found=$((found + 1))
    else
        echo "○  GitHub Copilot  — not detected"
    fi

    echo ""
    if [[ $found -eq 0 ]]; then
        echo "⚠️  No data sources found. Use an AI coding tool first to build up conversation data."
    else
        echo "Found $found data source(s). Ready to analyze."
    fi
}

# ─── Step 5: Verify ─────────────────────────────────────────

verify_run() {
    echo ""
    echo "── Verification ────────────────────────────────"
    echo ""
    python3 "$SKILL_DIR/scripts/analyzer.py" --mode=setup 2>/dev/null && echo "" && echo "✅ Analysis engine running OK" || echo "❌ Run failed, check Python environment"
}

# ─── Main ────────────────────────────────────────────────────

main() {
    local mode="${1:---full}"

    case "$mode" in
        --check)
            detect_sources
            ;;
        --full|*)
            check_python
            echo ""
            setup_symlink
            echo ""
            setup_hook
            detect_sources
            verify_run
            echo ""
            echo "═══════════════════════════════════════════════"
            echo "  Setup complete! Usage:"
            echo "  - In Claude Code: type /ai-trace"
            echo "  - CLI: python3 $SKILL_DIR/scripts/analyzer.py --days=7"
            echo "═══════════════════════════════════════════════"
            ;;
    esac
}

main "$@"

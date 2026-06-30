<p align="center">
  <h1 align="center">AI Interaction Analyzer</h1>
  <p align="center">
    <strong>把你和 AI 的对话历史，变成可直接安装的协作规则。</strong>
  </p>
  <p align="center">
    <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square"></a>
    <img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8+-yellow?style=flat-square">
    <img alt="Dependencies" src="https://img.shields.io/badge/外部依赖-0-orange?style=flat-square">
    <br>
    <a href="README_EN.md">English</a>
  </p>
</p>

---

你每天都在和 AI 编码工具对话，这些对话日志躺在本地硬盘上，从来没人看过。

这个工具帮你看。它扫描你本地 **6 款 AI 工具** 的对话记录，找出 AI 反复犯错的模式和你一次就搞定的模式，然后产出 **可以直接复制到任何 AI 工具配置文件里的规则**。

不是统计报告，是可执行的规则。

## 产出物长这样

```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║                        AI Interaction Analyzer                           ║
║                        ── 协 作 质 量 诊 断 ──                            ║
║                                                                          ║
║    📅  2026-06-23 ~ 06-30 (7天)                                          ║
║    💬  300 prompts · 37 sessions                                         ║
║    🔧  Claude Code (主力)                                                ║
║                                                                          ║
║    ┌──────────────────────────────────────────────────────────┐          ║
║    │                                                          │          ║
║    │   健 康 度    ████████████████░░░░░░░░  62%               │          ║
║    │                                                          │          ║
║    │   🔴  37 次纠正       🟢  6 次一次成功                    │          ║
║    │   📊  12 个高密度 session（信号 ≥ 2）                     │          ║
║    │   📝  6 条通用规则 + 4 条定制发现                         │          ║
║    │                                                          │          ║
║    └──────────────────────────────────────────────────────────┘          ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

完整报告还包括：

```
┌───────────────────────────────────────────────────────────────────────────┐
│  ──── 问题类型 ────────────────────────────────────────────────────────── │
│   AI 不够认真    ███████████████████████████████████████████   20         │
│   AI 编造/瞎猜   ██████████████████████████░░░░░░░░░░░░░░░░   10         │
│   AI 做错了      ████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░    8         │
│   质疑/不信任    ██████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░    7         │
│   AI 重复犯错    ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    4         │
└───────────────────────────────────────────────────────────────────────────┘

模式 1 — 不读代码就下结论 / 瞎猜实现
┌───────────────────────────────────────────────────────────────────────────┐
│  涉及 8 个 incident · 覆盖 hedui / huiyuan / abtest                      │
│                                                                           │
│  👤 "当前代码肯定需要改...仔细分析bizCheck方法...不允许胡编乱造"           │
│  🤖 AI 没有真正追踪 bizCheck 的上下游调用链，凭推测给出修改建议           │
│  👤 "这不是有吗？别瞎猜"                                                  │
│                                                                           │
│  根因  AI 用推测代替验证——没有 grep/read 确认就直接给结论                  │
└───────────────────────────────────────────────────────────────────────────┘

通用规则（直接复制到配置文件）
┌───────────────────────────────────────────────────────────────────────────┐
│  1. 复杂代码分析必须 grep/read 验证后再下结论。                           │
│  2. 收到修改意见只改指出的问题，不动已确认的好内容。                      │
│  3. 不同业务域平级隔离组织，不默认合并。                                  │
│  4. 引入外部调研结果围绕用户核心诉求，不喧宾夺主。                        │
│  5. "深度思考"= 推测 → 验证 → 确认闭环，不是给出解释就停。              │
│  6. 线上代码 ≠ 本地未提交代码，分析前先 git diff 区分。                   │
└───────────────────────────────────────────────────────────────────────────┘
```

以上是真实运行产出（7 天数据）。完整报告约 300 行，包括模型对比、按项目拆解的问题分布、5 类根因模式的深度分析（每个模式附真实对话上下文）、成功 session 的可复用模式、以及可直接安装到任何 AI 工具的规则。

## 支持的工具

| 工具 | 支持程度 | 分析内容 |
|------|---------|---------|
| **Claude Code** | 完整支持 | prompt 历史 + 完整 session 上下文 |
| **Codex** | 完整支持 | 历史 + rollout 上下文 |
| **Cursor** | 尽力解析 | SQLite 中的对话数据 |
| **Cline / Roo Code** | 尽力解析 | JSON 对话历史 |
| **Gemini CLI** | 尽力解析 | JSON 历史文件 |
| **ChatGPT**（导出） | 尽力解析 | 导出的 `conversations.json` |

信号检测同时覆盖中文表达（`"错了"` `"瞎编"` `"又来了"`）和英文表达（`"wrong"` `"hallucinating"` `"again"`），不限制用户的语言习惯。

## 工作原理

```
  你的本地对话日志（不会上传到任何地方）
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  Layer 1：信号扫描               │  扫描所有 prompt，提取
  │  "错了" "瞎编" "are you sure"    │  挫败信号和成功信号
  └───────────────┬─────────────────┘
                  │ 发现问题事件
                  ▼
  ┌─────────────────────────────────┐
  │  Layer 2：上下文深钻             │  读取每个事件前后 4 轮
  │  AI 做了什么？为什么出错？       │  完整对话，分析根因
  └───────────────┬─────────────────┘
                  │ 循环，直到没有新模式
                  ▼
  ┌─────────────────────────────────┐
  │  综合输出                        │  健康度仪表盘 + 规则 +
  │  Prompt Rules + Best Practices  │  一键安装到任何工具
  └─────────────────────────────────┘
```

## 安装

### 最快的方式

```bash
git clone https://github.com/xiuran/ai-interaction-analyzer ~/.claude/skills/ai-interaction-analyzer
```

然后在 Claude Code 对话里输入 `/ai-trace`，AI 会自动跑完整分析。

### 作为 Claude Code Plugin 安装

```bash
# 在 Claude Code 里执行：
/plugin marketplace add xiuran/ai-interaction-analyzer
```

### 独立 CLI

```bash
git clone https://github.com/xiuran/ai-interaction-analyzer
cd ai-interaction-analyzer

python3 scripts/analyzer.py --mode=scope           # 看看有哪些数据源
python3 scripts/analyzer.py --mode=analyze --days=30  # 跑完整分析
python3 scripts/analyzer.py --mode=signals --days=15  # 只扫信号（更快）
```

直接跑 `python3 analyzer.py` 输出的是原始 JSON 数据。完整的格式化报告需要通过 AI 执行 — 在 Claude Code 里用 `/ai-trace` 触发，AI 会读 SKILL.md 里的指令，调用脚本采集数据，然后按模板格式化输出。

<details>
<summary><strong>可选：SessionEnd Hook</strong></summary>

每次 Claude Code session 结束后自动记录质量指标。在 `~/.claude/settings.json` 加入：

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

日志写入 `~/.ai-interaction-analyzer/session-log.jsonl`。

</details>

## 规则安装到哪

| 工具 | 配置文件 |
|------|---------|
| Claude Code | `CLAUDE.md` |
| Codex | `AGENTS.md` |
| Cursor | `.cursorrules` |
| Cline | `.clinerules` |
| Windsurf | `.windsurfrules` |
| 通用 | System Prompt |

规则分两层：**通用规则**（适用于任何人、任何项目）和 **个性化发现**（只对你有价值，标注可选）。

## 自定义配置

```bash
mkdir -p ~/.config/ai-interaction-analyzer
cp config/custom_patterns.example.json ~/.config/ai-interaction-analyzer/custom_patterns.json
```

可以配置额外的确认短语（减少误报）、自定义否定词模式、特定领域的任务类型关键词、不想分析的项目。

## 隐私

完全本地运行，数据不出你的电脑。只读你的对话日志，不修改任何文件，不联网，不追踪。纯 Python 标准库，零第三方依赖。

## 项目结构

```
ai-interaction-analyzer/
├── SKILL.md                          # AI 指令文件（skill 入口）
├── .claude-plugin/marketplace.json   # Claude Code Plugin 配置
├── scripts/
│   ├── analyzer.py                   # 分析引擎（~1200 行）
│   ├── mini_analyzer.py              # 轻量 session hook
│   └── setup.sh                      # 一键安装
├── config/
│   └── custom_patterns.example.json  # 自定义配置模板
├── references/                       # 评分模型 & 反模式库
├── README.md
├── README_EN.md
└── LICENSE
```

## License

MIT

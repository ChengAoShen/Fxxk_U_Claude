<div align="center">

# Fxxk_U_claude

**中文 | [English](README.en.md)**

**把 Claude Code 里的配置、技能、命令、记忆和可选对话历史，安全迁移到 Codex / OpenCode / Pi / 其他 coding agent。**

![type](https://img.shields.io/badge/type-CLI%20tool-blue)
![python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)
![deps](https://img.shields.io/badge/dependencies-none%20required-brightgreen)
![targets](https://img.shields.io/badge/targets-codex%20%7C%20opencode%20%7C%20pi%20%7C%20generic-orange)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

</div>

---

## 这是什么？

**Fxxk_U_claude** 是一个本地迁移工具。它读取你机器上的 Claude Code 配置，然后生成一个干净、可审阅、可交给其他 coding agent 使用的迁移包。

它可以迁移：

- `CLAUDE.md` 项目/用户指令
- Claude Code Skills
- Claude Code slash commands
- Claude Code memory notes，包括 `MEMORY.md`
- settings / hooks / permissions 的人工审阅副本
- 可选：conversation history。对话历史默认不扫描，必须显式开启

支持输出到：

- **Codex**：生成 `AGENTS.md`
- **OpenCode**：生成 `AGENTS.md`、`.opencode/skills/*/SKILL.md`、`.opencode/commands/*.md`
- **Pi**：生成 `AGENTS.md`、`.pi/skills/*/SKILL.md`、best-effort Pi session JSONL
- **Generic**：生成通用 `AGENT_CONTEXT.md`，任何 agent 都能读

这个工具不会修改你的 Claude Code 配置，也不会直接写入目标 agent 的真实配置目录。它只生成一个迁移包，让你先检查，再手动接入。

---

## 为什么需要它？

如果你想从 Claude Code 迁移到别的 agent，最麻烦的不是重新安装一个 CLI，而是这些长期积累的上下文：

- 项目约定写在 `CLAUDE.md` 里
- 自己写过的 skills 和 commands
- Claude Code 记住的项目背景和偏好
- 之前对话里做过的决策、计划和排查过程
- settings / hooks / permissions 里有一些不能自动转换但需要人工确认的行为

**Fxxk_U_claude** 可以把这些东西整理成一个可读、可审阅、可迁移的 bundle。

---

## 安全设计

这个工具默认偏保守：

- `scan.py` 只读扫描，不修改任何源文件
- `migrate.py` 默认 dry-run，只打印文件计划，不打印文件内容
- 只有加 `--write` 才会真正生成迁移包
- 输出目录如果非空，会拒绝写入，避免覆盖
- 对话历史默认不扫描；要迁移 history 必须显式加 `--include-history`
- dry-run 默认隐藏内容预览，避免 secret 进入终端日志；需要预览时加 `--preview`
- 跳过 symlink，避免恶意项目诱导读取本机敏感文件
- 输出路径会校验，防止写出 `--out` 目录
- 自动不了解的 settings / hooks / permissions 会进入 `MANUAL_REVIEW.md`，不会乱转换

---

## 给不同 Agent 使用

**推荐方式是把它当通用 CLI 使用**：任何 agent 只要能运行 shell 命令，都可以调用 `uvx --from . fxxk-u-claude-scan` 和 `uvx --from . fxxk-u-claude-migrate`。这比绑定某个 Claude-style skill 机制更通用，也更适合 Codex、OpenCode、Pi 等工具混用。

- **Codex**：让 Codex 阅读本仓库的 [`AGENTS.md`](AGENTS.md)，然后按 README 的 CLI 命令执行。
- **OpenCode / Pi / Claude Code**：可以直接运行 CLI；如果你希望它们在技能列表里发现这个工具，也可以把本仓库作为兼容性 skill 安装。
- **其他 agent**：读取 `README.md` 或 `AGENTS.md`，按 CLI 使用即可。

可选的 skill 兼容安装方式：

```bash
# Claude Code
mkdir -p ~/.claude/skills
ln -s /path/to/Fxxk_U_claude ~/.claude/skills/fxxk-u-claude

# OpenCode project-local
mkdir -p .opencode/skills
ln -s /path/to/Fxxk_U_claude .opencode/skills/fxxk-u-claude

# Pi project-local
mkdir -p .pi/skills
ln -s /path/to/Fxxk_U_claude .pi/skills/fxxk-u-claude
```

---

## 人工使用（命令行）

推荐用 **uvx** 运行。这样会自动带上 PyYAML，YAML frontmatter 解析更完整；同时仓库仍兼容直接 `python3 scripts/...` 运行，没装依赖也能用内置 fallback。

```bash
git clone <this-repo-url> Fxxk_U_claude
cd Fxxk_U_claude

# 1. 扫描 Claude Code 配置，默认不包含对话历史
uvx --from . fxxk-u-claude-scan \
  --scope project \
  --project-root /path/to/your/project \
  --out /tmp/fxxk-u-claude-ir.json

# 2. 预览迁移到 Codex 会生成哪些文件，不写入磁盘
uvx --from . fxxk-u-claude-migrate \
  --ir /tmp/fxxk-u-claude-ir.json \
  --target codex \
  --out ./migrated/codex

# 3. 确认文件计划没问题后，真正生成迁移包
uvx --from . fxxk-u-claude-migrate \
  --ir /tmp/fxxk-u-claude-ir.json \
  --target codex \
  --out ./migrated/codex \
  --write
```

兼容的纯 Python 用法：

```bash
python3 scripts/scan.py --scope project --project-root /path/to/your/project --out /tmp/fxxk-u-claude-ir.json
python3 scripts/migrate.py --ir /tmp/fxxk-u-claude-ir.json --target codex --out ./migrated/codex --write
```

如果你确实想迁移对话历史：

```bash
uvx --from . fxxk-u-claude-scan \
  --scope project \
  --project-root /path/to/your/project \
  --include-history \
  --out /tmp/fxxk-u-claude-ir.json
```

> 注意：history 可能包含密码、token、内部 URL、粘贴过的私密内容。迁移前请确认你真的需要它。

---

## 常用目标

### 迁移到 Codex

```bash
uvx --from . fxxk-u-claude-migrate --ir /tmp/fxxk-u-claude-ir.json --target codex --out ./migrated/codex --write
```

生成：

```text
migrated/codex/
├── AGENTS.md
├── MANIFEST.md
└── MANUAL_REVIEW.md       # 有人工复核项时才生成
```

Codex 目前没有 Claude-style skill loader，所以 skills / commands 会被压平进 `AGENTS.md`。

### 迁移到 OpenCode

```bash
uvx --from . fxxk-u-claude-migrate --ir /tmp/fxxk-u-claude-ir.json --target opencode --out ./migrated/opencode --write
```

生成：

```text
migrated/opencode/
├── AGENTS.md
├── .opencode/skills/<skill>/SKILL.md
├── .opencode/commands/<command>.md
├── MANIFEST.md
└── MANUAL_REVIEW.md       # 有人工复核项时才生成
```

### 迁移到 Pi

```bash
uvx --from . fxxk-u-claude-migrate --ir /tmp/fxxk-u-claude-ir.json --target pi --out ./migrated/pi --write
```

生成：

```text
migrated/pi/
├── AGENTS.md
├── .pi/skills/<skill>/SKILL.md
├── pi-sessions/*.jsonl    # 仅在扫描时使用 --include-history
├── MANIFEST.md
└── MANUAL_REVIEW.md       # 有人工复核项时才生成
```

Pi session JSONL 是 best-effort 输出：格式尽量贴近 Pi 文档，但建议先拿一个文件测试能否加载。

### 通用 Markdown 输出

```bash
uvx --from . fxxk-u-claude-migrate --ir /tmp/fxxk-u-claude-ir.json --target generic --out ./migrated/generic --write
```

生成 `AGENT_CONTEXT.md`，适合粘贴给任何 agent 或作为人工迁移参考。

---

## 扫描范围

```bash
--scope project      # 默认：当前项目 + 全局 Claude Code 配置
--scope global-all   # 扫描 ~/.claude/projects/* 下所有项目的 memory；谨慎使用
--include-history    # 显式扫描 conversation history；默认关闭
--no-history         # 兼容旧用法；现在 history 默认就是关闭
```

默认推荐使用：

```bash
uvx --from . fxxk-u-claude-scan --scope project --project-root /path/to/project --out /tmp/ir.json
```

只有当你明确要迁移所有 Claude Code 项目时，才使用 `--scope global-all`。

---

## 输出文件说明

| 文件 | 说明 |
|---|---|
| `AGENTS.md` / `AGENT_CONTEXT.md` | 迁移后的主上下文文件 |
| `.opencode/skills/*/SKILL.md` | OpenCode skill 输出 |
| `.opencode/commands/*.md` | OpenCode command 输出 |
| `.pi/skills/*/SKILL.md` | Pi skill 输出 |
| `history/*.md` | Markdown 对话历史，仅 `--include-history` 时生成 |
| `pi-sessions/*.jsonl` | Pi-shaped session JSONL，仅 `--target pi` 且 `--include-history` 时生成 |
| `MANIFEST.md` | 本次扫描到了什么、生成了什么 |
| `MANUAL_REVIEW.md` | 需要人工确认的 settings、hooks、权限、文件名冲突、扫描警告等 |

如果生成了 `MANUAL_REVIEW.md`，请务必先读它，再把迁移包接入目标工具。

---

## 许可证

MIT License. See [LICENSE](LICENSE).

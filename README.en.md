<div align="center">

**[中文](README.md) | English**

# Fxxk_U_claude

**Safely migrate your Claude Code instructions, skills, commands, memory, and optional conversation history to Codex / OpenCode / Pi / other coding agents.**

![type](https://img.shields.io/badge/type-CLI%20tool-blue)
![python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)
![deps](https://img.shields.io/badge/dependencies-none%20required-brightgreen)
![targets](https://img.shields.io/badge/targets-codex%20%7C%20opencode%20%7C%20pi%20%7C%20generic-orange)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

</div>

---

## What is this?

**Fxxk_U_claude** is a local migration tool. It reads your Claude Code setup from disk and generates a clean, reviewable bundle that another coding agent can consume.

It can migrate:

- `CLAUDE.md` user/project instructions
- Claude Code skills
- Claude Code slash commands
- Claude Code memory notes, including `MEMORY.md`
- settings / hooks / permissions as manual-review material
- optional conversation history; history is not scanned unless you explicitly opt in

Supported output targets:

- **Codex**: `AGENTS.md`
- **OpenCode**: `AGENTS.md`, `.opencode/skills/*/SKILL.md`, `.opencode/commands/*.md`
- **Pi**: `AGENTS.md`, `.pi/skills/*/SKILL.md`, best-effort Pi session JSONL
- **Generic**: portable `AGENT_CONTEXT.md`

The tool does not modify your Claude Code files and does not write directly into another agent's live config directory. It creates a migration bundle for you to inspect first.

---

## Quick start

**Recommended:** run it with `uvx`. This automatically installs PyYAML for better YAML frontmatter parsing. Direct `python3 scripts/...` commands remain supported and fall back to the built-in lightweight parser when PyYAML is unavailable.

```bash
git clone <this-repo-url> Fxxk_U_claude
cd Fxxk_U_claude

uvx --from . fxxk-u-claude-scan \
  --scope project \
  --project-root /path/to/your/project \
  --out /tmp/fxxk-u-claude-ir.json

uvx --from . fxxk-u-claude-migrate \
  --ir /tmp/fxxk-u-claude-ir.json \
  --target codex \
  --out ./migrated/codex

uvx --from . fxxk-u-claude-migrate \
  --ir /tmp/fxxk-u-claude-ir.json \
  --target codex \
  --out ./migrated/codex \
  --write
```

Compatible plain-Python usage:

```bash
python3 scripts/scan.py --scope project --project-root /path/to/your/project --out /tmp/fxxk-u-claude-ir.json
python3 scripts/migrate.py --ir /tmp/fxxk-u-claude-ir.json --target codex --out ./migrated/codex --write
```

To include conversation history:

```bash
uvx --from . fxxk-u-claude-scan \
  --scope project \
  --project-root /path/to/your/project \
  --include-history \
  --out /tmp/fxxk-u-claude-ir.json
```

History can contain credentials, tokens, internal URLs, and anything you pasted into a previous session. Review it before sharing the bundle.

---

## Safety defaults

- `scan.py` is read-only.
- `migrate.py` dry-runs by default and hides file contents.
- `--write` is required to create files.
- Non-empty output directories are refused.
- Conversation history is opt-in via `--include-history`.
- `--preview` is required to print generated content in dry-run mode.
- Symlinks are skipped to avoid leaking unrelated local files.
- Output paths are validated so profiles cannot write outside `--out`.
- Ambiguous settings / hooks / permissions go to `MANUAL_REVIEW.md` instead of being guessed.

---

## Using it from different agents

**Recommended:** treat this as a universal CLI tool. Any agent that can run shell commands can call `uvx --from . fxxk-u-claude-scan` and `uvx --from . fxxk-u-claude-migrate`. This is more portable than tying the project to a Claude-style skill loader.

- **Codex**: point Codex at this repository's [`AGENTS.md`](AGENTS.md), then run the CLI commands from this README.
- **OpenCode / Pi / Claude Code**: run the CLI directly. If you still want the tool to appear in a skills list, you can install it as a compatibility skill.
- **Other agents**: read `README.md` or `AGENTS.md` and run the CLI commands.

Optional compatibility skill install:

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

## Release checks

```bash
uvx ruff check .
python3 -m py_compile scripts/*.py src/fxxk_u_claude/*.py
uvx pytest -q
uv build --wheel
```

---

## License

MIT License. See [LICENSE](LICENSE).

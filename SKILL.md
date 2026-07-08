---
name: fxxk-u-claude
description: Migrates Claude Code configuration (CLAUDE.md, skills, slash commands, memory, settings, and optionally history) into a review-friendly bundle for another agent CLI — Codex, OpenCode, Pi, or a generic Markdown fallback for anything else. Use this whenever the user wants to move their Claude Code setup to another coding agent, asks "how do I bring my Claude Code stuff to Codex/OpenCode/Pi", wants a portable export of their instructions/skills/memory, or is switching their primary agent tool and doesn't want to hand-copy files one by one.
---

# Fxxk_U_claude

Scans Claude Code configuration and converts it into files a different agent
CLI can actually use. It is a plain Python tool (no Claude-specific runtime
dependency) — any agent that can run `python3` and read Markdown, including
Codex, can drive it directly. See `README.md` in this folder for full usage,
or `AGENTS.md` if you're Codex.

## When to reach for this

The user wants some or all of: their `CLAUDE.md` instructions, custom skills,
slash commands, accumulated memory notes, or explicitly requested conversation history to carry over to another tool.
Don't hand-roll a one-off copy/paste job for this — this tool already handles
the messy parts (finding the right memory directory, keeping frontmatter
around, flagging settings/hooks that don't have an equivalent elsewhere).

## How to run it

Two-step pipeline: `scan.py` reads Claude Code's config and writes a single
JSON snapshot (never modifies anything). `migrate.py` reads that JSON and a
target profile from `fxxk_u_claude/target_profiles.yaml` and produces the output
bundle — dry-run by default, add `--preview` to show content previews, add `--write` to actually create files.

```bash
cd Fxxk_U_claude

# 1. Scan (read-only). Default scope is just this project + global config —
#    NOT every project under ~/.claude, since that would pull in unrelated
#    projects' notes. Only pass --scope global-all if the user explicitly
#    wants everything. History is skipped by default; add --include-history only
#    after confirming the user wants transcripts included.
uvx --from . fxxk-u-claude-scan --scope project --project-root /path/to/project --out /tmp/ir.json

# 2. Preview the migration (no files written yet)
uvx --from . fxxk-u-claude-migrate --ir /tmp/ir.json --target codex --out ./migrated/codex

# 3. Once the preview looks right, write it for real
uvx --from . fxxk-u-claude-migrate --ir /tmp/ir.json --target codex --out ./migrated/codex --write
```

Available `--target` values live in `fxxk_u_claude/target_profiles.yaml`
(currently `codex`, `opencode`, `pi`, `generic`). If the user names a tool that
isn't in there, use `generic` — it produces one portable Markdown file that
works as a system prompt or pasted context anywhere — and consider adding a
proper profile to the YAML afterward (see below).

## Before trusting the output

`fxxk_u_claude/target_profiles.yaml` encodes assumptions about where Codex/
OpenCode expect their instructions file and whether they support per-file
skills/commands or need everything flattened. These conventions move fast and
may be stale by the time this runs. Before handing the generated bundle to the
user as final:

1. Skim the target tool's current docs for its actual config file layout.
2. If the shipped profile is wrong, fix the YAML entry (not the scripts) —
   the whole point of keeping profiles data-driven is that this should be a
   small edit, not a rewrite.
3. If `MANUAL_REVIEW.md` is generated, read it out loud to the
   user rather than silently trusting it was handled — it lists settings,
   hooks, and permissions that have no automatic equivalent, plus any memory
   cross-links (`[[name]]`) that got flattened and might read oddly out of
   context.

## Output bundle contents

- The consolidated instructions file (name depends on target — `AGENTS.md`
  for codex/opencode, `AGENT_CONTEXT.md` for generic).
- `skills/` or `commands/` subdirectories, only for targets whose profile
  says `skills_mode: directory` / `commands_mode: directory`.
- `MANUAL_REVIEW.md` — generated when needed; settings/hooks/permissions, output filename collisions, cross-link warnings and any scan warnings (e.g. could not confidently find the right memory directory).
- `MANIFEST.md` — what was found, what got written where.

## A note on memory

Claude Code's memory lives per-project under
`~/.claude/projects/<hash-of-project-path>/memory/`, where the hash directory
name isn't officially documented — `scan.py` reproduces the pattern observed
on disk (path separators and punctuation replaced with `-`) and falls back to
listing candidate directories if it can't get a confident match, rather than
guessing wrong silently. If `scan.py` reports it couldn't match a project,
tell the user and let them point at the right directory.

Memory has no equivalent concept in Codex/OpenCode/etc., so it's always
flattened into a "Background context" section of the instructions file,
grouped by type (about-the-user / feedback / project / reference) — treated
as background for the receiving agent to read, not as literal instructions.

## Extending to a new target

Add a new entry to `fxxk_u_claude/target_profiles.yaml` following the existing
ones. Use `skills_file_pattern` / `commands_file_pattern` when the target
expects paths such as `<name>/SKILL.md`. You don't need to touch `scan.py` or
`migrate.py` unless the new target needs something genuinely different from
flatten-or-directory (e.g. a totally different file format). See the comments
at the top of that YAML file for the field reference.

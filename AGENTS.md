# AGENTS.md — Fxxk_U_claude

You are working in a standalone tool folder, not a Claude Code skill package.
It has no dependency on Claude Code being installed — it's a Python CLI that
reads Claude Code's on-disk config format and writes plain Markdown/YAML.

Read `README.md` first for the full picture. This file is the short version
for driving the tool directly.

## What this does

1. `scripts/scan.py` — read-only. Walks a Claude Code install
   (`~/.claude/...` plus a project's `.claude/` and `CLAUDE.md`) and writes
   one JSON file describing everything found: instructions, skills, slash
   commands, memory notes, settings, and optionally conversation history when `--include-history` is passed.
2. `scripts/migrate.py` — reads that JSON plus a profile from
   `fxxk_u_claude/target_profiles.yaml`, and produces a target-specific output
   bundle. Dry-run unless `--write` is passed; dry-run hides content unless `--preview` is passed.

## Commands

```bash
uvx --from . fxxk-u-claude-scan --scope project --project-root <path> --out /tmp/ir.json
uvx --from . fxxk-u-claude-migrate --ir /tmp/ir.json --target codex --out ./migrated/codex          # dry run, prints plan
uvx --from . fxxk-u-claude-migrate --ir /tmp/ir.json --target codex --out ./migrated/codex --write   # writes files

# Plain Python remains supported when uvx is unavailable:
# python3 scripts/scan.py --scope project --project-root <path> --out /tmp/ir.json
# python3 scripts/migrate.py --ir /tmp/ir.json --target codex --out ./migrated/codex --write
```

`--scope global-all` instead of `project` scans every project's memory under
`~/.claude/projects/*`, not just the current one — only do this if the user
explicitly wants everything, since it touches unrelated projects' notes. Conversation history is skipped by default; pass `--include-history` only after the user explicitly accepts the privacy risk.

## If you (Codex) are the migration target

Since `codex` is one of the shipped target profiles, running this with
`--target codex` produces an `AGENTS.md` (plus `MANIFEST.md`, and `MANUAL_REVIEW.md` when review items exist) meant to become *your own* instructions file for the project
being migrated. Practical flow:

1. Run the scan against the source project the user names.
2. Dry-run the migration, show the user the plan.
3. On confirmation, `--write` it, then read `MANUAL_REVIEW.md` back to the
   user yourself if it was generated — it holds permissions/hooks/settings that have no
   equivalent in your own config format, plus anything ambiguous.
4. Before treating `fxxk_u_claude/target_profiles.yaml`'s `codex` entry as
   correct, sanity-check against whatever you currently know about your own
   config conventions (instructions file location, whether you support
   directory-based custom commands yet). If it's wrong, correct the YAML
   entry — don't hand-patch just the one output file, since that fix should
   persist for the next run too.

## Don't

- Don't scan `--scope global-all` by default — it pulls in every project's
  memory notes, most of which are irrelevant to whatever the user is actually
  migrating right now.
- Don't overwrite an existing `--out` directory that already has files in it
  — `migrate.py` already refuses this; don't work around it with `-f` or by
  deleting the directory first without asking.
- Don't treat `MANUAL_REVIEW.md` contents as already handled if that file is
  produced — it exists specifically because those items need a human decision.

#!/usr/bin/env python3
"""
Scan Claude Code configuration (CLAUDE.md, skills, commands, memory, settings)
and emit a single JSON "intermediate representation" (IR) describing everything
found and where it came from. Read-only — never writes or deletes anything.

Usage:
  python3 scan.py --scope project [--project-root DIR] [--home DIR] [--out FILE] [--include-history]
  python3 scan.py --scope global-all [--home DIR] [--out FILE] [--include-history]

Scopes:
  project     (default) project-root CLAUDE.md/.claude/*, plus the *global*
              CLAUDE.md/skills/commands/settings (global config applies to
              every project so it's always included), plus only the memory
              directory matching project-root (not other projects' memory).
  global-all  everything in --home/.claude, including every project's memory
              directory under projects/*. Touches data across ALL of the
              user's projects, not just the current one -- only use this
              when the user has explicitly asked to migrate everything.
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml  # optional, only used to surface frontmatter nicely
except ImportError:
    yaml = None


def read_text(p: Path):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"<<could not read {p}: {e}>>"


def is_safe_regular_file(p: Path, warnings=None, label="file") -> bool:
    """Avoid following symlinks during migration scans. A malicious project can
    otherwise point .claude/commands/foo.md at ~/.ssh/id_rsa and cause the tool
    to copy unrelated local secrets into the IR/output bundle."""
    try:
        if p.is_symlink():
            if warnings is not None:
                warnings.append(f"Skipped symlinked {label}: {p}")
            return False
        return p.is_file()
    except OSError as e:
        if warnings is not None:
            warnings.append(f"Could not stat {label} {p}: {e}")
        return False


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def split_frontmatter(text: str):
    """Return (frontmatter_dict_or_none, body_str, raw_frontmatter_or_none).
    Never raises. The raw frontmatter is kept so migration output can preserve
    the user's original metadata for review instead of only a parsed/re-dumped
    approximation."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text, None
    raw, body = m.group(1), m.group(2)
    if yaml is not None:
        try:
            fm = yaml.safe_load(raw) or {}
            return fm, body, raw
        except Exception:
            pass
    # Small fallback parser: top-level key: value plus one-level nested maps.
    # This is enough for common Claude memory frontmatter such as
    # metadata:\n  type: user, without requiring PyYAML.
    fm = {}
    current_map = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        if line.startswith((" ", "\t")) and current_map and ":" in stripped:
            k, _, v = stripped.partition(":")
            fm.setdefault(current_map, {})[k.strip()] = v.strip().strip("'\"")
            continue
        current_map = None
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            key = k.strip()
            val = v.strip().strip("'\"")
            if val == "":
                fm[key] = {}
                current_map = key
            else:
                fm[key] = val
    return fm, body, raw


def find_claude_md(paths, warnings=None):
    out = []
    for p in paths:
        if is_safe_regular_file(p, warnings, "CLAUDE.md"):
            out.append({"path": str(p), "content": read_text(p)})
    return out


def find_md_dir(dir_path: Path, kind: str, warnings=None):
    """Generic scanner for a directory of *.md files with optional frontmatter
    (used for skills and commands). Skills are one level deeper: dir/name/SKILL.md."""
    out = []
    if not dir_path.is_dir():
        return out
    if kind == "skill":
        for child in sorted(dir_path.iterdir()):
            if child.is_symlink():
                if warnings is not None:
                    warnings.append(f"Skipped symlinked skill directory: {child}")
                continue
            skill_md = child / "SKILL.md"
            if is_safe_regular_file(skill_md, warnings, "skill"):
                text = read_text(skill_md)
                fm, body, raw_fm = split_frontmatter(text)
                out.append({
                    "path": str(skill_md),
                    "dir": str(child),
                    "frontmatter": fm or {},
                    "raw_frontmatter": raw_fm,
                    "body": body,
                    "has_scripts": (child / "scripts").is_dir(),
                    "has_references": (child / "references").is_dir(),
                    "has_assets": (child / "assets").is_dir(),
                })
    else:  # command
        for f in sorted(dir_path.rglob("*.md")):
            if not is_safe_regular_file(f, warnings, "command"):
                continue
            text = read_text(f)
            fm, body, raw_fm = split_frontmatter(text)
            out.append({
                "path": str(f),
                "name": f.stem,
                "frontmatter": fm or {},
                "raw_frontmatter": raw_fm,
                "body": body,
            })
    return out


def find_plugin_skills(home: Path):
    """Third-party skills installed via the plugin marketplace, living under
    plugins/cache/<marketplace>/<plugin>/*/skills/*/SKILL.md. These are NOT
    the user's own authored content -- they were installed from elsewhere, so
    migrating the files verbatim doesn't make sense (the equivalent action on
    another tool is installing/finding an equivalent plugin there, not copying
    files). Reported separately, excluded from the main migration bundle."""
    out = []
    cache_dir = home / ".claude" / "plugins" / "cache"
    if not cache_dir.is_dir():
        return out
    for skill_md in cache_dir.glob("*/*/*/skills/*/SKILL.md"):
        if not is_safe_regular_file(skill_md, None, "plugin skill"):
            continue
        text = read_text(skill_md)
        fm, _, _ = split_frontmatter(text)
        out.append({
            "path": str(skill_md),
            "name": (fm or {}).get("name", skill_md.parent.name),
            "description": (fm or {}).get("description", ""),
        })
    return out


def project_hash_dirname(project_root: Path) -> str:
    """Best-effort reproduction of Claude Code's project->directory-name mapping.
    Observed convention: the absolute path with '/' collapsed and most
    non-alphanumeric separators (including '_' and '.') replaced with '-'.
    This is inferred from on-disk evidence, not documented -- if it stops
    matching, find_memory_dir() falls back to listing all project dirs so nothing
    is silently missed."""
    abs_path = str(project_root.resolve())
    return re.sub(r"[^A-Za-z0-9]+", "-", abs_path)


def find_project_dir(home: Path, project_root: Path):
    """Find the ~/.claude/projects/<hash> directory for this project -- it
    holds both memory/ and the raw session *.jsonl transcripts as siblings.
    Returns (project_dir_or_None, sibling_candidates_if_no_confident_match)."""
    projects_dir = home / ".claude" / "projects"
    if not projects_dir.is_dir():
        return None, []
    candidate = projects_dir / project_hash_dirname(project_root)
    if candidate.is_dir():
        return candidate, []
    # fallback: list all project dirs with *something* in them so the caller
    # (or the agent driving this script) can pick the right one manually
    siblings = [str(d) for d in sorted(projects_dir.iterdir()) if d.is_dir()]
    return None, siblings


def scan_memory(memory_dir: Path, warnings=None):
    entries = []
    index = None
    if memory_dir is None:
        return {"index": None, "entries": [], "dir": None}
    index_path = memory_dir / "MEMORY.md"
    if is_safe_regular_file(index_path, warnings, "memory index"):
        index = read_text(index_path)
    for f in sorted(memory_dir.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        if not is_safe_regular_file(f, warnings, "memory entry"):
            continue
        text = read_text(f)
        fm, body, raw_fm = split_frontmatter(text)
        entries.append({
            "path": str(f),
            "frontmatter": fm or {},
            "raw_frontmatter": raw_fm,
            "body": body,
        })
    return {"index": index, "entries": entries, "dir": str(memory_dir)}


def extract_text(content, depth=0) -> str:
    """Claude Code message content is either a plain string or a list of
    content blocks (text / tool_use / tool_result / thinking / image), same
    shape as the Anthropic Messages API. Render it into flat readable text --
    this is a summary for another agent to read as background, not a
    byte-exact transcript, so lossy simplification here (e.g. collapsing
    tool_result sub-content) is fine."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "thinking":
                continue  # internal reasoning, not useful as migrated context
            elif btype == "tool_use":
                args = json.dumps(block.get("input", {}), ensure_ascii=False)
                parts.append(f"[called tool `{block.get('name','?')}` with args {args}]")
            elif btype == "tool_result":
                inner = extract_text(block.get("content"), depth + 1)
                if len(inner) > 2000:
                    inner = inner[:2000] + " …[truncated]"
                tag = "error" if block.get("is_error") else "result"
                parts.append(f"[tool {tag}: {inner}]")
            elif btype == "image":
                parts.append("[image content omitted]")
            else:
                parts.append(f"[{btype or 'unknown'} block omitted]")
        return "\n".join(p for p in parts if p)
    return str(content)


TRANSCRIPT_MESSAGE_TYPES = {"user", "assistant"}


def scan_conversation_file(path: Path, warnings=None, max_chars_per_turn=6000):
    """Parse one Claude Code session JSONL file into a flat list of turns.
    These files interleave real conversation turns (type: user/assistant)
    with session bookkeeping (mode changes, permission-mode changes, file
    snapshots, queued-message bookkeeping, auto-generated titles) -- only the
    former becomes migrated content; the latter is Claude-Code-runtime
    plumbing with no equivalent anywhere else."""
    turns = []
    session_id = None
    title = None
    started_at = None
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception as e:
                if warnings is not None:
                    warnings.append(f"Skipped invalid JSONL line in conversation {path}: {e}")
                continue
            rtype = rec.get("type")
            if rtype == "ai-title":
                title = rec.get("title") or title
                continue
            if rtype not in TRANSCRIPT_MESSAGE_TYPES:
                continue
            msg = rec.get("message") or {}
            role = msg.get("role", rtype)
            text = extract_text(msg.get("content"))
            if not text.strip():
                continue
            if len(text) > max_chars_per_turn:
                if warnings is not None:
                    warnings.append(
                        f"Truncated a {role} turn in {path} to {max_chars_per_turn} characters."
                    )
                text = text[:max_chars_per_turn] + " …[truncated]"
            ts = rec.get("timestamp")
            if started_at is None:
                started_at = ts
            session_id = rec.get("sessionId", session_id)
            turns.append({"role": role, "text": text, "timestamp": ts, "uuid": rec.get("uuid")})
    return {
        "session_id": session_id or path.stem,
        "path": str(path),
        "title": title,
        "started_at": started_at,
        "turns": turns,
    }


def scan_conversations(project_memory_parent: Path, warnings=None):
    """project_memory_parent is the project's dir under ~/.claude/projects/
    (the same one that contains memory/) -- session transcripts sit as
    *.jsonl files directly inside it, siblings of memory/."""
    out = []
    if project_memory_parent is None or not project_memory_parent.is_dir():
        return out
    for f in sorted(project_memory_parent.glob("*.jsonl")):
        if not is_safe_regular_file(f, warnings, "conversation"):
            continue
        out.append(scan_conversation_file(f, warnings))
    return out


def scan_settings(paths, warnings=None):
    out = []
    for p in paths:
        if is_safe_regular_file(p, warnings, "settings file"):
            raw = read_text(p)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            out.append({"path": str(p), "raw": raw, "parsed": parsed})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scope", choices=["project", "global-all"], default="project")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--home", default=str(Path.home()))
    ap.add_argument("--out", default=None, help="write JSON here instead of stdout")
    ap.add_argument("--include-history", action="store_true",
                    help="include conversation transcripts. Off by default because history can "
                         "contain anything the user ever pasted or typed (credentials, internal "
                         "URLs, etc.).")
    ap.add_argument("--no-history", action="store_true",
                    help="deprecated compatibility flag; history is skipped by default unless "
                         "--include-history is passed")
    args = ap.parse_args()

    home = Path(args.home)
    project_root = Path(args.project_root).resolve()
    warnings = []

    ir = {
        "ir_version": 1,
        "scope": args.scope,
        "project_root": str(project_root),
        "home": str(home),
        "claude_md": [],
        "skills": {"global": [], "project": []},
        "commands": {"global": [], "project": []},
        "memory": {},
        "conversations": {},
        "settings": [],
        "plugin_skills_installed": [],
        "warnings": warnings,
    }

    include_history = args.include_history and not args.no_history

    # CLAUDE.md
    ir["claude_md"] = find_claude_md([
        home / ".claude" / "CLAUDE.md",
        project_root / "CLAUDE.md",
        project_root / ".claude" / "CLAUDE.md",
    ], warnings)

    # Skills (global always included; project skills only for project scope,
    # but global-all also naturally includes it since project_root still applies)
    ir["skills"]["global"] = find_md_dir(home / ".claude" / "skills", "skill", warnings)
    ir["skills"]["project"] = find_md_dir(project_root / ".claude" / "skills", "skill", warnings)

    # Commands
    ir["commands"]["global"] = find_md_dir(home / ".claude" / "commands", "command", warnings)
    ir["commands"]["project"] = find_md_dir(project_root / ".claude" / "commands", "command", warnings)

    # Plugin-installed skills (informational, not migrated by default)
    ir["plugin_skills_installed"] = find_plugin_skills(home)

    # Settings
    ir["settings"] = scan_settings([
        home / ".claude" / "settings.json",
        home / ".claude" / "settings.local.json",
        project_root / ".claude" / "settings.json",
        project_root / ".claude" / "settings.local.json",
    ], warnings)

    # Memory + conversation history share the same ~/.claude/projects/<hash>
    # directory, so they're located together.
    if args.scope == "project":
        proj_dir, siblings = find_project_dir(home, project_root)
        if proj_dir is None and siblings:
            warnings.append(
                "Could not confidently match this project to a directory under "
                f"~/.claude/projects/. Candidates found: {siblings}. "
                "Pass the right one explicitly if memory/history should be included."
            )
        mem_dir = (proj_dir / "memory") if proj_dir else None
        ir["memory"] = {"current_project": scan_memory(mem_dir, warnings)}
        if include_history:
            ir["conversations"] = {"current_project": scan_conversations(proj_dir, warnings)}
            if ir["conversations"]["current_project"]:
                warnings.append(
                    "Conversation history was included in this scan. These transcripts can "
                    "contain anything ever typed or pasted into a session (credentials, "
                    "internal URLs, etc.) -- review MANUAL_REVIEW.md and the rendered "
                    "transcripts before sharing the output bundle anywhere. Re-run with "
                    "--no-history to exclude conversation content entirely."
                )
    else:  # global-all
        projects_dir = home / ".claude" / "projects"
        all_mem = {}
        all_conv = {}
        if projects_dir.is_dir():
            for d in sorted(projects_dir.iterdir()):
                mem = d / "memory"
                if mem.is_dir():
                    all_mem[d.name] = scan_memory(mem, warnings)
                if include_history:
                    convs = scan_conversations(d, warnings)
                    if convs:
                        all_conv[d.name] = convs
        ir["memory"] = {"all_projects": all_mem}
        ir["conversations"] = {"all_projects": all_conv}
        if all_conv:
            warnings.append(
                "Conversation history from ALL projects was included in this scan (--scope "
                "global-all) -- this can be a lot of unrelated content and may contain "
                "sensitive material. Review before sharing the output bundle anywhere."
            )

    out_text = json.dumps(ir, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"Wrote IR to {args.out}", file=sys.stderr)
    else:
        print(out_text)


if __name__ == "__main__":
    main()

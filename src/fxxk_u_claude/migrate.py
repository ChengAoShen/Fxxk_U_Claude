#!/usr/bin/env python3
"""
Turn an IR JSON file (produced by scan.py) into a migration bundle for a
target agent tool, using the mapping rules in fxxk_u_claude/target_profiles.yaml.

Dry-run by default: prints the file plan without file contents, so secrets are
less likely to leak into terminal logs. Pass --preview to include first-line
previews. Pass --write to actually create the bundle
in --out (which must not already exist, so nothing gets silently overwritten).

Usage:
  python3 migrate.py --ir /path/to/ir.json --target codex --out ./migrated/codex
  python3 migrate.py --ir /path/to/ir.json --target codex --out ./migrated/codex --write
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from importlib import resources as importlib_resources
except ImportError:  # pragma: no cover - Python 3.8 fallback
    import importlib_resources  # type: ignore

try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

try:
    from . import _yamlite  # type: ignore
except ImportError:  # direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _yamlite  # type: ignore  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
PROFILES_PATH = SCRIPT_DIR / "target_profiles.yaml"


def find_profiles_path():
    candidates = [
        PROFILES_PATH,
        Path.cwd() / "fxxk_u_claude" / "target_profiles.yaml",
        Path.cwd() / "target_profiles.yaml",
        Path(sys.prefix) / "fxxk_u_claude" / "target_profiles.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Could not find fxxk_u_claude/target_profiles.yaml. Run from the repository root, "
        "or install the package with its data files."
    )


def load_profiles():
    try:
        text = importlib_resources.files("fxxk_u_claude").joinpath("target_profiles.yaml").read_text(
            encoding="utf-8"
        )
    except Exception:
        text = find_profiles_path().read_text(encoding="utf-8")
    if HAVE_YAML:
        return yaml.safe_load(text)
    return _yamlite.load_profiles(text)


def yaml_dump_flat(d: dict) -> str:
    if HAVE_YAML:
        return yaml.safe_dump(d, allow_unicode=True, sort_keys=False).strip()
    return _yamlite.dump_flat(d)


def escape_html_comment(text: str) -> str:
    return (text or "").replace("-->", "--&gt;")


def render_frontmatter(fields: dict) -> str:
    return "---\n" + yaml_dump_flat(fields) + "\n---"


def render_path_pattern(pattern: str, slug: str) -> str:
    return pattern.format(slug=slug, name=slug)


def unique_pattern_path(files: dict, pattern: str, slug: str):
    candidate_slug = slug
    i = 2
    while True:
        rel_path = render_path_pattern(pattern, candidate_slug)
        if rel_path not in files:
            return candidate_slug, rel_path
        candidate_slug = f"{slug}-{i}"
        i += 1


def split_rel_path(path: str):
    p = Path(path)
    return str(p.with_suffix("")), p.suffix


def add_file(files: dict, rel_path: str, content: str, manual_review: list, reason: str = ""):
    """Add a generated file without silently overwriting an existing one."""
    candidate = rel_path
    if candidate in files:
        stem, suffix = split_rel_path(rel_path)
        i = 2
        while f"{stem}-{i}{suffix}" in files:
            i += 1
        candidate = f"{stem}-{i}{suffix}"
        manual_review.append("## Output filename collision resolved")
        manual_review.append("")
        manual_review.append(
            f"Generated path `{rel_path}` was already used{f' for {reason}' if reason else ''}; "
            f"wrote this item to `{candidate}` instead so no content was lost."
        )
        manual_review.append("")
    files[candidate] = content
    return candidate


def validate_relative_output_path(rel_path: str):
    p = Path(rel_path)
    if p.is_absolute() or any(part == ".." for part in p.parts) or rel_path in ("", "."):
        raise ValueError(f"unsafe output path from target profile: {rel_path!r}")


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "item"


def skill_display_name(skill: dict) -> str:
    fm = skill.get("frontmatter") or {}
    return fm.get("name") or Path(skill["dir"]).name


def command_display_name(cmd: dict) -> str:
    fm = cmd.get("frontmatter") or {}
    return fm.get("name") or cmd.get("name") or Path(cmd["path"]).stem


def render_skill_section(skill: dict, source_label: str) -> str:
    fm = skill.get("frontmatter") or {}
    name = skill_display_name(skill)
    desc = fm.get("description", "")
    lines = [f"## Skill: {name}  _(from {source_label})_", ""]
    if desc:
        lines += [f"> {desc}", ""]
    lines += [skill.get("body", "").strip(), ""]
    return "\n".join(lines)


def render_command_section(cmd: dict, source_label: str) -> str:
    fm = cmd.get("frontmatter") or {}
    name = command_display_name(cmd)
    desc = fm.get("description", "")
    lines = [f"## Command: /{name}  _(from {source_label})_", ""]
    if desc:
        lines += [f"> {desc}", ""]
    lines += [cmd.get("body", "").strip(), ""]
    return "\n".join(lines)


def render_skill_file(skill: dict, profile_name: str, output_name=None) -> str:
    """Standalone file for directory-mode targets. Keeps the original
    frontmatter visible (as a comment) since we don't know the target's exact
    expected field names -- better to show both than silently guess wrong."""
    fm = skill.get("frontmatter") or {}
    orig_fm_yaml = skill.get("raw_frontmatter") or yaml_dump_flat(fm)
    name = output_name or slugify(skill_display_name(skill))
    desc = fm.get("description", "Migrated Claude Code skill")
    out = []
    out.append(render_frontmatter({"name": name, "description": desc}))
    out.append("")
    out.append("<!-- MIGRATION NOTE: original Claude Code frontmatter below.")
    out.append(f"     Field names may need adjusting for {profile_name}'s")
    out.append(f"     expected schema -- check {profile_name}'s current docs.")
    out.append(escape_html_comment(orig_fm_yaml))
    out.append("-->")
    out.append("")
    out.append(skill.get("body", "").strip())
    out.append("")
    return "\n".join(out)


def render_command_file(cmd: dict, profile_name: str) -> str:
    fm = cmd.get("frontmatter") or {}
    orig_fm_yaml = cmd.get("raw_frontmatter") or yaml_dump_flat(fm)
    desc = fm.get("description", "Migrated Claude Code command")
    out = []
    out.append(render_frontmatter({"description": desc}))
    out.append("")
    out.append("<!-- MIGRATION NOTE: original Claude Code frontmatter below.")
    out.append(f"     Field names may need adjusting for {profile_name}'s")
    out.append(f"     expected schema -- check {profile_name}'s current docs.")
    out.append(escape_html_comment(orig_fm_yaml))
    out.append("-->")
    out.append("")
    out.append(cmd.get("body", "").strip())
    out.append("")
    return "\n".join(out)


def render_memory(memory: dict) -> str:
    """Flatten memory into a labeled context section, grouped by type."""
    entries = []
    indexes = []
    if "current_project" in memory:
        cur = memory["current_project"]
        entries = cur.get("entries", [])
        if cur.get("index"):
            indexes.append((cur.get("dir"), cur.get("index")))
    elif "all_projects" in memory:
        for proj, m in memory["all_projects"].items():
            if m.get("index"):
                indexes.append((proj, m.get("index")))
            for e in m.get("entries", []):
                e = dict(e)
                e["_project"] = proj
                entries.append(e)

    if not entries and not indexes:
        return ""

    by_type = {}
    for e in entries:
        fm = e.get("frontmatter") or {}
        t = (fm.get("metadata") or {}).get("type", "unknown") if isinstance(fm.get("metadata"), dict) else "unknown"
        by_type.setdefault(t, []).append(e)

    out = ["## Background context (migrated from Claude Code memory)", "",
           "_The notes below were accumulated over past sessions. They are not "
           "instructions to follow blindly -- read them as background the way you "
           "would read notes left by a colleague._", ""]
    if indexes:
        out.append("### Memory index")
        out.append("")
        for source, index in indexes:
            if source:
                out.append(f"<!-- source: {source}/MEMORY.md -->")
            out.append(index.strip())
            out.append("")
    type_titles = {
        "user": "About the user",
        "feedback": "Working-style feedback / preferences",
        "project": "Project context",
        "reference": "Where to find things",
        "unknown": "Other notes",
    }
    ordered_types = ["user", "feedback", "project", "reference", "unknown"] + sorted(
        t for t in by_type if t not in {"user", "feedback", "project", "reference", "unknown"}
    )
    for t in ordered_types:
        if t not in by_type:
            continue
        out.append(f"### {type_titles.get(t, t)}")
        out.append("")
        for e in by_type[t]:
            fm = e.get("frontmatter") or {}
            title = fm.get("description") or fm.get("name") or Path(e["path"]).stem
            out.append(f"**{title}**")
            out.append("")
            out.append(e.get("body", "").strip())
            out.append("")
    return "\n".join(out)


def find_memory_links_needing_review(memory: dict):
    """[[name]] links between memory files reference other memory files by
    slug. Once flattened into one document those links no longer resolve to
    separate files, so flag them for a human to eyeball rather than silently
    leaving dead references."""
    entries = []
    if "current_project" in memory:
        entries = memory["current_project"].get("entries", [])
    elif "all_projects" in memory:
        for m in memory["all_projects"].values():
            entries.extend(m.get("entries", []))
    hits = []
    for e in entries:
        for m in re.finditer(r"\[\[([^\]]+)\]\]", e.get("body", "")):
            hits.append((Path(e["path"]).name, m.group(1)))
    return hits


def collect_conversations(conversations_ir: dict):
    """Flatten scan.py's {"current_project": [...]} or {"all_projects": {proj: [...]}}
    shape into one list, tagging each with its source project for global-all scans."""
    out = []
    if "current_project" in conversations_ir:
        for c in conversations_ir["current_project"]:
            out.append(dict(c, _project=None))
    elif "all_projects" in conversations_ir:
        for proj, convs in conversations_ir["all_projects"].items():
            for c in convs:
                out.append(dict(c, _project=proj))
    return out


def render_transcript_md(conv: dict) -> str:
    """Readable Markdown transcript -- background for a human or agent to
    read, not a format meant to resume a live session. Works for any target."""
    title = conv.get("title") or conv.get("session_id")
    lines = [f"# Session: {title}", "",
             f"- Source session id: `{conv.get('session_id')}`",
             f"- Started: {conv.get('started_at')}",
             f"- Original file: `{conv.get('path')}`", ""]
    for turn in conv.get("turns", []):
        role = turn.get("role", "?")
        label = {"user": "User", "assistant": "Assistant"}.get(role, role)
        lines.append(f"### {label}  _{turn.get('timestamp','')}_")
        lines.append("")
        lines.append(turn.get("text", "").strip())
        lines.append("")
    return "\n".join(lines)


def iso_to_unix_ms(ts: str) -> int:
    if not ts:
        return 0
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return 0


def pi_entry_id(seed: str, used: set) -> str:
    i = 0
    while True:
        digest = hashlib.sha1(f"{seed}:{i}".encode("utf-8")).hexdigest()[:8]
        if digest not in used:
            used.add(digest)
            return digest
        i += 1


def render_pi_session(conv: dict) -> str:
    """Best-effort reproduction of Pi's documented session JSONL schema
    (docs/session-format.md in earendil-works/pi-mono): a header 'session'
    line, then entries with id/parentId forming a linear chain, each wrapping
    an AgentMessage. This has only been checked against the published schema,
    not round-tripped through a real Pi install -- treat as a strong starting
    point, not guaranteed-correct input to `pi --session`."""
    lines = []
    session_id = conv.get("session_id", "unknown")
    header = {
        "type": "session",
        "version": 3,
        "id": session_id,
        "timestamp": conv.get("started_at") or "",
        "cwd": conv.get("_source_cwd") or conv.get("project_root") or "",
    }
    lines.append(json.dumps(header, ensure_ascii=False))
    parent_id = None
    used_ids = set()
    for i, turn in enumerate(conv.get("turns", [])):
        entry_id = pi_entry_id(turn.get("uuid") or f"{session_id}:{i}", used_ids)
        role = turn.get("role")
        ts = turn.get("timestamp") or ""
        msg_ts = iso_to_unix_ms(ts)
        if role == "user":
            message = {"role": "user", "content": turn.get("text", ""), "timestamp": msg_ts}
        else:
            message = {
                "role": "assistant",
                "content": [{"type": "text", "text": turn.get("text", "")}],
                "api": "unknown", "provider": "unknown", "model": "unknown",
                "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0,
                          "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0}},
                "stopReason": "stop", "timestamp": msg_ts,
            }
        entry = {
            "type": "message",
            "id": entry_id,
            "parentId": parent_id,
            "timestamp": ts,
            "message": message,
        }
        lines.append(json.dumps(entry, ensure_ascii=False))
        parent_id = entry_id
    return "\n".join(lines) + "\n"


def build_bundle(ir: dict, profile: dict, profile_name: str):
    """Returns {relative_path: content} plus a list of manual-review notes."""
    files = {}
    manual_review = []

    # --- consolidated instructions file ---
    parts = ["# Migrated agent instructions",
             "",
             f"_Generated by agent-config-migrate from Claude Code config "
             f"(scope: {ir.get('scope')}). Target profile: {profile_name}. "
             f"Review before trusting -- some fields are best-effort guesses._",
             ""]

    if ir.get("claude_md"):
        parts.append("## Project / user instructions (from CLAUDE.md)")
        parts.append("")
        for c in ir["claude_md"]:
            parts.append(f"<!-- source: {c['path']} -->")
            parts.append(c["content"].strip())
            parts.append("")

    skills_flatten = profile.get("skills_mode", "flatten") == "flatten"
    commands_flatten = profile.get("commands_mode", "flatten") == "flatten"

    all_skills = [(s, "global skill") for s in ir.get("skills", {}).get("global", [])] + \
                 [(s, "project skill") for s in ir.get("skills", {}).get("project", [])]
    all_commands = [(c, "global command") for c in ir.get("commands", {}).get("global", [])] + \
                   [(c, "project command") for c in ir.get("commands", {}).get("project", [])]

    if skills_flatten and all_skills:
        parts.append("## Skills")
        parts.append("")
        for s, label in all_skills:
            parts.append(render_skill_section(s, label))
    elif not skills_flatten:
        skills_pattern = profile.get("skills_file_pattern") or f"{profile['skills_dir']}/{{slug}}.md"
        for s, label in all_skills:
            name = slugify(skill_display_name(s))
            output_name, rel_path = unique_pattern_path(files, skills_pattern, name)
            if output_name != name:
                manual_review.append("## Output filename collision resolved")
                manual_review.append("")
                manual_review.append(
                    f"Skill `{name}` conflicted with an existing output path; wrote it as `{output_name}` instead so no content was lost."
                )
                manual_review.append("")
            add_file(
                files,
                rel_path,
                render_skill_file(s, profile_name, output_name),
                manual_review,
                f"skill {name}",
            )

    if commands_flatten and all_commands:
        parts.append("## Commands")
        parts.append("")
        for c, label in all_commands:
            parts.append(render_command_section(c, label))
    elif not commands_flatten:
        commands_pattern = profile.get("commands_file_pattern") or f"{profile['commands_dir']}/{{slug}}.md"
        for c, label in all_commands:
            name = slugify(command_display_name(c))
            output_name, rel_path = unique_pattern_path(files, commands_pattern, name)
            if output_name != name:
                manual_review.append("## Output filename collision resolved")
                manual_review.append("")
                manual_review.append(
                    f"Command `{name}` conflicted with an existing output path; wrote it as `{output_name}` instead so no content was lost."
                )
                manual_review.append("")
            add_file(
                files,
                rel_path,
                render_command_file(c, profile_name),
                manual_review,
                f"command {name}",
            )

    memory_section = render_memory(ir.get("memory", {}))
    if memory_section:
        parts.append(memory_section)

    conversations = collect_conversations(ir.get("conversations", {}))
    if conversations:
        history_mode = profile.get("history_mode", "transcript")
        history_dir = profile.get("history_dir", "history")
        for conv in conversations:
            slug = slugify(conv.get("title") or conv.get("session_id") or "session")
            if history_mode == "native_pi":
                add_file(files, f"{history_dir}/{slug}.jsonl", render_pi_session(conv), manual_review, f"session {slug}")
            else:
                add_file(files, f"{history_dir}/{slug}.md", render_transcript_md(conv), manual_review, f"session {slug}")
        parts.append("## Conversation history")
        parts.append("")
        parts.append(
            f"{len(conversations)} past session(s) were migrated into `{history_dir}/` "
            f"({'Pi-native session JSONL' if history_mode == 'native_pi' else 'readable Markdown transcripts'}). "
            "Treat this as background on what was discussed and decided before, not as "
            "instructions to re-execute."
        )
        parts.append("")

    add_file(files, profile["instructions_file"], "\n".join(parts), manual_review, "instructions")

    # --- manual review ---
    if ir.get("settings"):
        review = ["# Manual review needed", "",
                   "Items below have no automatic equivalent in the target tool. "
                   "Read them and decide what (if anything) to recreate manually.",
                   "", "## Claude Code settings (permissions / hooks / env)", ""]
        for s in ir["settings"]:
            review.append(f"### {s['path']}")
            review.append("```json")
            review.append(s["raw"].strip() if s["raw"] else "{}")
            review.append("```")
            review.append("")
        manual_review.extend(review)

    link_hits = find_memory_links_needing_review(ir.get("memory", {}))
    if link_hits:
        manual_review.append("## Memory cross-links flattened")
        manual_review.append("")
        manual_review.append(
            "These memory files referenced each other with [[links]]. After "
            "flattening into one document the links are just plain text -- "
            "check that the referenced context still reads sensibly nearby:"
        )
        manual_review.append("")
        for src, target in link_hits:
            manual_review.append(f"- `{src}` links to `[[{target}]]`")
        manual_review.append("")

    if ir.get("plugin_skills_installed"):
        manual_review.append("## Installed third-party plugin skills (not migrated)")
        manual_review.append("")
        manual_review.append(
            "These are skills installed from a plugin marketplace, not authored "
            "by you -- copying the files over doesn't make sense since the "
            "equivalent action on the target tool is finding/installing an "
            "equivalent plugin there, if one exists. Listed for awareness only:"
        )
        manual_review.append("")
        for p in ir["plugin_skills_installed"]:
            manual_review.append(f"- **{p['name']}** — {p.get('description','')} (`{p['path']}`)")
        manual_review.append("")

    if conversations and profile.get("history_mode") == "native_pi":
        manual_review.append("## Conversation history written in Pi's native format")
        manual_review.append("")
        manual_review.append(
            f"The {len(conversations)} file(s) under `{profile.get('history_dir','history')}/` "
            "were generated to match Pi's *published* session JSONL schema, but this tool has "
            "not verified them by actually loading one into a real Pi install -- try "
            "`pi --session <file>` on one before trusting the rest, and don't be surprised if "
            "some fields (model/provider/usage, which weren't recoverable from the Claude Code "
            "transcript) show up as placeholder 'unknown'/0 values."
        )
        manual_review.append("")

    if ir.get("warnings"):
        manual_review.append("## Scan warnings")
        manual_review.append("")
        for w in ir["warnings"]:
            manual_review.append(f"- {w}")
        manual_review.append("")

    if manual_review:
        if not manual_review[0].startswith("# "):
            manual_review = [
                "# Manual review needed",
                "",
                "Items below need human attention before considering the migration complete.",
                "",
            ] + manual_review
        files["MANUAL_REVIEW.md"] = "\n".join(manual_review)

    return files


def build_manifest(ir, profile, profile_name, files):
    lines = ["# Migration manifest", "",
              f"- IR version: **{ir.get('ir_version', 'unknown')}**",
              f"- Source scope: **{ir.get('scope')}**",
              f"- Target: **{profile.get('display_name', profile_name)}**",
              ""]
    lines.append("## Notes about this target profile")
    lines.append("")
    lines.append(
        "These mapping rules are read from fxxk_u_claude/target_profiles.yaml, not "
        "hardcoded -- if the target tool's conventions have changed since this "
        "profile was last verified, edit that file rather than the scripts."
    )
    lines.append("")
    for n in profile.get("notes", []):
        lines.append(f"- {n}")
    lines.append("")
    lines.append("## Files this run produces")
    lines.append("")
    for path in sorted(files):
        lines.append(f"- `{path}`")
    lines.append("")
    n_skills = len(ir.get("skills", {}).get("global", [])) + len(ir.get("skills", {}).get("project", []))
    n_cmds = len(ir.get("commands", {}).get("global", [])) + len(ir.get("commands", {}).get("project", []))
    n_claude_md = len(ir.get("claude_md", []))
    mem = ir.get("memory", {})
    if "current_project" in mem:
        cur_mem = mem.get("current_project", {})
        n_mem = len(cur_mem.get("entries", [])) + (1 if cur_mem.get("index") else 0)
    else:
        n_mem = sum(len(m.get("entries", [])) + (1 if m.get("index") else 0)
                    for m in mem.get("all_projects", {}).values())
    n_conv = len(collect_conversations(ir.get("conversations", {})))
    n_turns = sum(len(c.get("turns", [])) for c in collect_conversations(ir.get("conversations", {})))
    lines.append("## What was found")
    lines.append("")
    lines.append(f"- CLAUDE.md files: {n_claude_md}")
    lines.append(f"- Skills: {n_skills}")
    lines.append(f"- Commands: {n_cmds}")
    lines.append(f"- Memory entries: {n_mem}")
    lines.append(f"- Conversation sessions: {n_conv} ({n_turns} total turns)")
    lines.append(f"- Settings files: {len(ir.get('settings', []))}")
    lines.append(f"- Installed plugin skills (not migrated): {len(ir.get('plugin_skills_installed', []))}")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ir", required=True, help="path to IR JSON from scan.py")
    ap.add_argument("--target", required=True, help="profile name in target_profiles.yaml (e.g. codex, opencode, generic)")
    ap.add_argument("--out", required=True, help="output bundle directory")
    ap.add_argument("--write", action="store_true", help="actually write files (default: dry-run plan only)")
    ap.add_argument("--preview", action="store_true", help="in dry-run mode, also print the first lines of each file (may reveal sensitive content)")
    args = ap.parse_args()

    ir = json.loads(Path(args.ir).read_text(encoding="utf-8"))
    profiles = load_profiles()

    profile_name = args.target
    if profile_name not in profiles:
        print(f"WARNING: unknown target '{profile_name}', falling back to 'generic'.", file=sys.stderr)
        profile_name = "generic"
    profile = profiles[profile_name]

    files = build_bundle(ir, profile, profile_name)
    manifest = build_manifest(ir, profile, profile_name, files)
    files["MANIFEST.md"] = manifest

    out_dir = Path(args.out)

    for rel_path in files:
        validate_relative_output_path(rel_path)

    if not args.write:
        print(f"DRY RUN -- would write to {out_dir}/ :\n")
        for path in sorted(files):
            content = files[path]
            print(f"--- {path} ({len(content)} chars) ---")
            if args.preview:
                preview = "\n".join(content.splitlines()[:8])
                print(preview)
                if len(content.splitlines()) > 8:
                    print("...")
            else:
                print("(content preview hidden; pass --preview to show it)")
            print()
        print("Re-run with --write to create these files.")
        return

    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"ERROR: {out_dir} already exists and is not empty -- refusing to overwrite. "
              f"Choose a new/empty --out directory.", file=sys.stderr)
        sys.exit(1)

    out_root = out_dir.resolve()
    for rel_path, content in files.items():
        full = (out_dir / rel_path).resolve()
        if full != out_root and out_root not in full.parents:
            print(f"ERROR: unsafe output path escapes --out: {rel_path}", file=sys.stderr)
            sys.exit(1)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    print(f"Wrote {len(files)} files to {out_dir}/")


if __name__ == "__main__":
    main()

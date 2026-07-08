"""
Tiny dependency-free YAML reader/writer covering exactly the two shapes this
tool needs: target_profiles.yaml (two-level: profile -> {scalar fields, one
list field}) and flat skill/command frontmatter (string -> string). Real
PyYAML is used instead when available (see the try/except at each call site)
-- this module exists so the tool doesn't hard-require `pip install pyyaml`
just to run, since the whole point is to work in unfamiliar environments
(e.g. a bare Codex sandbox) without a setup step.

This is intentionally not a general YAML parser -- it will mishandle
multi-line scalars, nested maps-in-lists, anchors, etc. If target_profiles.yaml
needs anything fancier than "profile: {scalar: value, notes: [one-line, ...]}",
either install PyYAML or extend this file.
"""
def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def load_profiles(text: str) -> dict:
    profiles = {}
    cur_profile = None
    cur_list_key = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            cur_profile = stripped.rstrip(":")
            profiles[cur_profile] = {}
            cur_list_key = None
            continue
        if stripped.startswith("- "):
            if cur_profile is None or cur_list_key is None:
                continue
            profiles[cur_profile].setdefault(cur_list_key, []).append(_unquote(stripped[2:]))
            continue
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if cur_profile is None:
                continue
            if v == "":
                cur_list_key = k
                profiles[cur_profile][k] = []
            else:
                profiles[cur_profile][k] = _unquote(v)
                cur_list_key = None
    return profiles


def load_flat_frontmatter(text: str) -> dict:
    """Best-effort: key: value per line, ignores anything nested/listy rather
    than raising, since this is only used as a fallback for reporting/display."""
    out = {}
    for line in text.splitlines():
        if ":" in line and not line.strip().startswith("#") and not line.startswith((" ", "\t", "-")):
            k, _, v = line.partition(":")
            out[k.strip()] = _unquote(v.strip())
    return out


def _quote_scalar(v) -> str:
    if v is None:
        return "''"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # Single-quote scalars so newlines, colons, comments, and document markers
    # cannot break the generated frontmatter. YAML escapes a single quote by
    # doubling it inside single-quoted strings.
    return "'" + s.replace("'", "''").replace("\n", "\\n") + "'"


def dump_flat(d: dict) -> str:
    lines = []
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            lines.append(f"{k}:")
            for ck, cv in v.items():
                lines.append(f"  {ck}: {_quote_scalar(cv)}")
        elif isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {_quote_scalar(item)}")
        else:
            lines.append(f"{k}: {_quote_scalar(v)}")
    return "\n".join(lines)

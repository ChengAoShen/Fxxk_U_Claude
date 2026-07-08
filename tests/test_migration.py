import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migrate = load_module("migrate", ROOT / "src" / "fxxk_u_claude" / "migrate.py")
scan = load_module("scan", ROOT / "src" / "fxxk_u_claude" / "scan.py")


def sample_ir():
    return {
        "ir_version": 1,
        "scope": "project",
        "claude_md": [],
        "skills": {
            "global": [
                {
                    "path": "/tmp/a/SKILL.md",
                    "dir": "/tmp/a",
                    "frontmatter": {"name": "demo", "description": "Demo skill"},
                    "raw_frontmatter": "name: demo\ndescription: Demo skill",
                    "body": "Do demo work.",
                }
            ],
            "project": [
                {
                    "path": "/tmp/b/SKILL.md",
                    "dir": "/tmp/b",
                    "frontmatter": {"name": "demo", "description": "Project demo"},
                    "raw_frontmatter": "name: demo\ndescription: Project demo",
                    "body": "Project demo work.",
                }
            ],
        },
        "commands": {"global": [], "project": []},
        "memory": {
            "current_project": {
                "dir": "/tmp/memory",
                "index": "# Memory index\nImportant index note.",
                "entries": [],
            }
        },
        "conversations": {},
        "settings": [],
        "plugin_skills_installed": [],
        "warnings": [],
    }


class MigrationTests(unittest.TestCase):
    def test_pi_skill_paths_and_collision_are_safe(self):
        profiles = migrate.load_profiles()
        files = migrate.build_bundle(sample_ir(), profiles["pi"], "pi")
        self.assertIn(".pi/skills/demo/SKILL.md", files)
        self.assertIn(".pi/skills/demo-2/SKILL.md", files)
        self.assertIn("MANUAL_REVIEW.md", files)
        self.assertIn("collision", files["MANUAL_REVIEW.md"].lower())

    def test_opencode_current_paths(self):
        profiles = migrate.load_profiles()
        files = migrate.build_bundle(sample_ir(), profiles["opencode"], "opencode")
        self.assertIn(".opencode/skills/demo/SKILL.md", files)
        self.assertIn(".opencode/skills/demo-2/SKILL.md", files)

    def test_memory_index_is_rendered(self):
        profiles = migrate.load_profiles()
        files = migrate.build_bundle(sample_ir(), profiles["generic"], "generic")
        self.assertIn("Important index note", files["AGENT_CONTEXT.md"])

    def test_output_path_validation_rejects_escape(self):
        for bad in ["../x.md", "/tmp/x.md", ""]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    migrate.validate_relative_output_path(bad)

    def test_scan_skips_symlinked_commands(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            commands = root / ".claude" / "commands"
            commands.mkdir(parents=True)
            target = root / "secret.md"
            target.write_text("secret", encoding="utf-8")
            link = commands / "leak.md"
            link.symlink_to(target)
            warnings = []
            found = scan.find_md_dir(commands, "command", warnings)
            self.assertEqual(found, [])
            self.assertTrue(any("symlink" in w.lower() for w in warnings))

    def test_scan_conversations_available_but_history_is_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            home = base / "home"
            project = base / "project"
            project.mkdir(parents=True)
            proj_dir = home / ".claude" / "projects" / scan.project_hash_dirname(project)
            proj_dir.mkdir(parents=True)
            (proj_dir / "s.jsonl").write_text(
                json.dumps({
                    "type": "user",
                    "sessionId": "s",
                    "timestamp": "2026-01-01T00:00:00.000Z",
                    "message": {"role": "user", "content": "hello"},
                }) + "\n",
                encoding="utf-8",
            )
            self.assertTrue(scan.scan_conversations(proj_dir, []))


if __name__ == "__main__":
    unittest.main()

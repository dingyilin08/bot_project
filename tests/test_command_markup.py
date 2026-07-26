from pathlib import Path
import unittest

from Game_main.g6_dungeon import format_monster_list_markdown


class CommandMarkupTests(unittest.TestCase):
    def test_runtime_source_does_not_emit_enter_commands(self):
        root = Path(__file__).resolve().parents[1]
        source_roots = (root / "Game_main", root / "Tool", root / "func")
        remaining = []
        for source_root in source_roots:
            for path in source_root.rglob("*.py"):
                if "<qqbot-cmd-enter" in path.read_text(encoding="utf-8"):
                    remaining.append(path.relative_to(root).as_posix())
        self.assertEqual(remaining, [])

    def test_monster_button_uses_name_as_display_text(self):
        content = format_monster_list_markdown(
            "试炼秘境",
            {
                "defeated_count": 0,
                "wave": 1,
                "kill_streak": 0,
                "monsters": [{"index": 1, "name": "青木妖狼", "defeated": False, "type": "normal"}],
            },
            {},
        )
        self.assertIn("text='挑战怪物 1' show='青木妖狼'", content)


if __name__ == "__main__":
    unittest.main()

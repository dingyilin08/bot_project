import unittest

from Game_main.g15_expedition import (
    MAX_NODES,
    causal_mark_effects,
    node_options,
    normalize_vote,
    outcome,
    resolve_choice,
)


class ExpeditionTests(unittest.TestCase):
    def test_nodes_are_six_and_have_two_choices(self):
        self.assertEqual(MAX_NODES, 6)
        self.assertEqual(node_options(1), ("战斗", ("破阵", "守势")))
        self.assertEqual(len(node_options(99)[1]), 2)

    def test_vote_accepts_only_current_node_options(self):
        self.assertEqual(normalize_vote("救援", 2), "救援")
        self.assertIsNone(normalize_vote("夺宝", 2))

    def test_choice_is_deterministic_and_majority_wins(self):
        self.assertEqual(resolve_choice(["破阵", "破阵", "守势"], 1), "破阵")
        self.assertEqual(resolve_choice(["救援", "交易"], 2), resolve_choice(["交易", "救援"], 2))

    def test_outcome_is_replayable_and_marks_causal_choices(self):
        self.assertEqual(outcome(2, "救援", "session-a"), outcome(2, "救援", "session-a"))
        self.assertEqual(outcome(2, "救援", "session-a")[1], "丹师善缘")
        self.assertEqual(outcome(4, "夺宝", "session-a")[1], "遗宝因果")

    def test_causal_marks_have_presence_only_pve_effects(self):
        effects = causal_mark_effects((("丹师善缘", 9), ("遗宝因果", 3)))
        self.assertEqual(effects["attack_bp"], 300)
        self.assertEqual(effects["defense_bp"], 300)
        self.assertEqual(effects["stacks"]["丹师善缘"], 9)

    def test_unknown_and_duplicate_marks_cannot_inflate_stats(self):
        effects = causal_mark_effects(("遗宝因果", "遗宝因果", "未知印记"))
        self.assertEqual(effects["attack_bp"], 300)
        self.assertEqual(effects["defense_bp"], 0)

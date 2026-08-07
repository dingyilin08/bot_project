import unittest
from copy import deepcopy

import output_main
from Game_main import g5_skill
from Game_main.g5_skill import parse_fusion_skill_ids, parse_skill_info_id, parse_skill_rename_param


class SkillRenameParserTests(unittest.TestCase):
    def test_parse_valid_name(self):
        self.assertEqual(parse_skill_rename_param(" 10001-烈焰斩 "), (10001, "烈焰斩", None))

    def test_parse_rejects_invalid_id_empty_placeholder_and_long_name(self):
        for value in (
            "烈焰斩",
            "0-烈焰斩",
            "1-",
            "1-未命名",
            "1-" + "道" * 31,
            "1-烈焰斩\n<qqbot-cmd-input>",
        ):
            with self.subTest(value=value):
                skill_id, name, error = parse_skill_rename_param(value)
                self.assertIsNone(skill_id)
                self.assertIsNone(name)
                self.assertTrue(error)

    def test_parse_fusion_skill_ids_requires_two_distinct_positive_ids(self):
        self.assertEqual(parse_fusion_skill_ids("31-33"), (31, 33))
        for value in ("31", "31-", "31-31", "0-33", "abc-33", "31-33-35"):
            with self.subTest(value=value):
                self.assertEqual(parse_fusion_skill_ids(value), (None, None))

    def test_parse_skill_info_id_requires_a_positive_skill_bag_id(self):
        self.assertEqual(parse_skill_info_id(" 34 "), 34)
        for value in ("", "0", "-1", "雨之剑意", "31-33"):
            with self.subTest(value=value):
                self.assertIsNone(parse_skill_info_id(value))


class _FusionCursor:
    def __init__(self, skills):
        self.skills = skills
        self._row = None

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        if statement.startswith("SELECT skill_name, skill_type"):
            skill = self.skills.get(int(params[0]))
            self._row = skill["row"] if skill and skill["uid"] == params[1] else None
        elif statement.startswith("SELECT COALESCE(MAX(id), 0) + 1"):
            self._row = (max(self.skills, default=0) + 1,)
        elif statement.startswith("INSERT INTO user_skill"):
            skill_id, uid, name, skill_type, value, is_percent, source_1, source_2, is_data_skill, is_zb, cooldown = params
            self.skills[skill_id] = {
                "uid": uid,
                "row": (name, skill_type, value, is_percent, is_data_skill, is_zb, source_1, cooldown),
                "sources": (source_1, source_2),
            }
        elif statement.startswith("DELETE FROM user_skill"):
            for skill_id in params[:2]:
                self.skills.pop(int(skill_id), None)
        elif statement.startswith("SELECT buff_name, buff_desc FROM data_skill"):
            self._row = ("雨界意境", "无视敌方40%防御，持续2回合")
        else:
            raise AssertionError(f"未预期的融合 SQL：{statement}")

    async def fetchone(self):
        return self._row


class _FusionCursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, *_args):
        return False


class _FusionConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.commit_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def cursor(self):
        return _FusionCursorContext(self.cursor_value)

    async def commit(self):
        self.commit_count += 1


class SkillFusionSimulationTests(unittest.IsolatedAsyncioTestCase):
    async def test_player_31_33_fusion_returns_response_and_restores_snapshot(self):
        uid = 70001
        skills = {
            31: {"uid": uid, "row": ("雨之剑意", 1, "340", 0, 1, 0, 63, 2)},
            33: {"uid": uid, "row": ("本源真身", 1, "40", 0, 1, 0, 65, 1)},
        }
        original_skills = deepcopy(skills)
        cursor = _FusionCursor(skills)
        conn = _FusionConnection(cursor)
        original_connect = g5_skill.connect_mysql
        original_uid_to_name = g5_skill.uid_to_name
        original_randint = g5_skill.random.randint

        async def fake_uid_to_name(_uid):
            return "模拟玩家"

        g5_skill.connect_mysql = lambda: conn
        g5_skill.uid_to_name = fake_uid_to_name
        g5_skill.random.randint = lambda low, _high: low
        try:
            result = await g5_skill.fuse_skills.__wrapped__(uid, "", "31-33")
        finally:
            g5_skill.connect_mysql = original_connect
            g5_skill.uid_to_name = original_uid_to_name
            g5_skill.random.randint = original_randint

        self.assertIn("成功将[雨之剑意]和[本源真身]融合", result["content"])
        self.assertIn("技能数值：60", result["content"])
        self.assertIn("继承BUFF：雨界意境", result["content"])
        self.assertIn("技能信息 34", result["content"])
        self.assertEqual(conn.commit_count, 1)
        self.assertEqual(set(skills), {34})
        skills.clear()
        skills.update(deepcopy(original_skills))
        self.assertEqual(skills, original_skills)


class _SkillInfoCursor:
    def __init__(self):
        self._row = None
        self._rows = []

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        if statement.startswith("SELECT id, skill_name, skill_type"):
            self._row = (34, "未命名", 1, "60", 0, None, 63, 65, 0, 2)
        elif statement.startswith("SELECT id, skill_name, buff_name, buff_desc FROM data_skill"):
            self._rows = [
                (63, "雨之剑意", "雨界意境", "无视敌方40%防御，持续2回合"),
                (65, "本源真身", "本尊", "全属性提升15%，持续1回合"),
            ]
        else:
            raise AssertionError(f"未预期的技能信息 SQL：{statement}")

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return self._rows


class SkillInfoTests(unittest.IsolatedAsyncioTestCase):
    async def test_fused_skill_details_are_loaded_by_skill_bag_id(self):
        cursor = _SkillInfoCursor()
        conn = _FusionConnection(cursor)
        original_connect = g5_skill.connect_mysql
        g5_skill.connect_mysql = lambda: conn
        try:
            result = await g5_skill.skill_info.__wrapped__(70001, "", "34")
        finally:
            g5_skill.connect_mysql = original_connect

        content = result["content"]
        self.assertIn("融合技能【未命名】信息", content)
        self.assertIn("技能编号：34", content)
        self.assertIn("可装备角色：任意角色", content)
        self.assertIn("融合素材：雨之剑意 + 本源真身", content)
        self.assertIn("继承BUFF：雨界意境", content)
        self.assertIn("BUFF描述：无视敌方40%防御，持续2回合", content)

    async def test_base_skill_name_returns_catalog_details(self):
        cursor = _BaseSkillInfoCursor(found=True)
        conn = _FusionConnection(cursor)
        original_connect = g5_skill.connect_mysql
        g5_skill.connect_mysql = lambda: conn
        try:
            result = await g5_skill.skill_info.__wrapped__(70001, "", "吸掌")
        finally:
            g5_skill.connect_mysql = original_connect

        content = result["content"]
        self.assertIn("基础技能【吸掌】信息", content)
        self.assertIn("可装备角色：萧炎", content)
        self.assertIn("技能BUFF：破甲", content)

    async def test_unknown_skill_name_guides_player_to_skill_bag_id(self):
        cursor = _BaseSkillInfoCursor(found=False)
        conn = _FusionConnection(cursor)
        original_connect = g5_skill.connect_mysql
        g5_skill.connect_mysql = lambda: conn
        try:
            result = await g5_skill.skill_info.__wrapped__(70001, "", "我的融合技")
        finally:
            g5_skill.connect_mysql = original_connect

        self.assertIn("技能信息 技能编号", result["content"])
        self.assertIn("技能信息 31", result["content"])


class _BaseSkillInfoCursor:
    def __init__(self, found):
        self.found = found
        self._row = None

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        if statement.startswith("SELECT role_name, skill_type, `value`"):
            self._row = ("萧炎", 4, "30", 1, 2, "破甲", "破防提升30%，持续2回合") if self.found else None
        else:
            raise AssertionError(f"未预期的基础技能信息 SQL：{statement}")

    async def fetchone(self):
        return self._row


class _SkillBagCursor:
    def __init__(self):
        self._row = None
        self._rows = []

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        if statement.startswith("SELECT COUNT(*) FROM user_skill"):
            self._row = (1,)
        elif statement.startswith("SELECT id, is_data_skill, skill_name, skill_type FROM user_skill"):
            self._rows = [(34, 0, "万象斩", 1)]
        elif statement.startswith("SELECT lingshi, xianyu FROM user_zt"):
            self._row = (1000, 100)
        else:
            raise AssertionError(f"未预期的技能背包 SQL：{statement}")

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return self._rows


class SkillBagDisplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_skill_bag_button_shows_name_and_submits_skill_id(self):
        cursor = _SkillBagCursor()
        conn = _FusionConnection(cursor)
        original_connect = g5_skill.connect_mysql
        g5_skill.connect_mysql = lambda: conn
        try:
            result = await g5_skill.skill_bag.__wrapped__(70001, "", 1)
        finally:
            g5_skill.connect_mysql = original_connect

        content = result["content"]
        self.assertIn("text='技能信息 34' show='万象斩'", content)
        self.assertIn("〔34〕", content)


class SkillRenameRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_parser_preserves_name_separator(self):
        self.assertEqual(
            await output_main.jiance("技能命名 10001-烈焰斩"),
            ("技能命名", "10001-烈焰斩"),
        )
        self.assertEqual(await output_main.jiance("技能信息 34"), ("技能信息", "34"))

    async def test_content_routes_to_rename_handler(self):
        original_uid = output_main.openid_to_uid
        original_rename = output_main.rename_skill
        calls = []

        async def fake_uid(_openid):
            return 7001

        async def fake_rename(uid, param):
            calls.append((uid, param))
            return {"type": "markdown", "content": "命名完成"}

        output_main.openid_to_uid = fake_uid
        output_main.rename_skill = fake_rename
        try:
            result = await output_main.content("技能命名", "10001-烈焰斩", "openid")
        finally:
            output_main.openid_to_uid = original_uid
            output_main.rename_skill = original_rename

        self.assertEqual(result["content"], "命名完成")
        self.assertEqual(calls, [(7001, "10001-烈焰斩")])


if __name__ == "__main__":
    unittest.main()

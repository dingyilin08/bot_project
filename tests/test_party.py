import asyncio
import unittest
from unittest.mock import patch

from Game_main import g13_party
from Game_main.g13_party import FORMATIONS, parse_formation


class _Cursor:
    def __init__(self, party_state="LOBBY"):
        self.party_state = party_state
        self.queries = []
        self._last_query = ""

    async def execute(self, query, params=()):
        self._last_query = " ".join(query.split())
        self.queries.append((self._last_query, params))

    async def fetchone(self):
        if "SELECT p.id, p.party_code" in self._last_query:
            return (9, "ABCDEFGH", "group", 1, "锋矢", self.party_state)
        return None

    async def fetchall(self):
        if "SELECT p.party_code" in self._last_query:
            return [
                ("ABCDEFGH", 1, "玄武", self.party_state, 1, 0, "前列"),
                ("ABCDEFGH", 1, "玄武", self.party_state, 2, 0, "后列"),
            ]
        return []


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self):
        return self

    async def __aenter__(self):
        return self._cursor if self._cursor else self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.commits += 1


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class PartyTests(unittest.TestCase):
    def test_parse_formation_accepts_supported_layout(self):
        self.assertEqual(parse_formation("玄武-前列"), ("玄武", "前列"))
        self.assertIn("流云", FORMATIONS)

    def test_parse_formation_rejects_invalid_values(self):
        self.assertIsNone(parse_formation("未知-前列"))
        self.assertIsNone(parse_formation("玄武"))

    def test_party_identity_reader_keeps_battle_state_visible(self):
        cursor = _Cursor("BATTLE")
        party = asyncio.run(g13_party._party_for_member(1, cursor))
        self.assertEqual(party["state"], "BATTLE")
        self.assertIn("p.state IN ('LOBBY', 'BATTLE')", cursor.queries[0][0])

    def test_changing_formation_clears_every_active_member_ready(self):
        cursor = _Cursor("LOBBY")
        connection = _Connection(cursor)
        with patch.object(g13_party, "connect_mysql", return_value=_ConnectionContext(connection)):
            result = asyncio.run(
                g13_party.party_formation.__wrapped__(1, "", "group", "玄武-前列")
            )
        queries = [query for query, _ in cursor.queries]
        self.assertTrue(any(
            "UPDATE party_member SET ready = 0 WHERE party_id = %s AND member_state = 'ACTIVE'" in query
            for query in queries
        ))
        self.assertIn("全员准备已清空", result["content"])

    def test_battle_state_rejects_formation_without_writes(self):
        cursor = _Cursor("BATTLE")
        connection = _Connection(cursor)
        with patch.object(g13_party, "connect_mysql", return_value=_ConnectionContext(connection)):
            result = asyncio.run(
                g13_party.party_formation.__wrapped__(1, "", "group", "玄武-前列")
            )
        self.assertIn("战斗中", result["content"])
        self.assertFalse(any(query.startswith("UPDATE party ") for query, _ in cursor.queries))

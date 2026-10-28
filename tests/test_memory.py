from __future__ import annotations

import tempfile
import time
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from echomora.engine import EchoMora
from echomora.settings import Settings


class EchoMoraTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "demo.db"
        settings = Settings(
            db_path=self.db_path,
            random_forget_rate=1.0,
            half_life_days=30.0,
        )
        self.engine = EchoMora(settings)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_explicit_memory_round_trip(self) -> None:
        self.engine.chat(
            "g1", "u1", "小岚", "请记住：我不吃甜食，最近在减脂。", use_llm=False
        )
        result = self.engine.chat(
            "g1", "u1", "小岚", "你还记得我为什么不吃甜食吗？", use_llm=False
        )
        self.assertTrue(result["recalled"])
        self.assertIn("不吃", result["recalled"][0]["text"])
        self.assertGreaterEqual(result["affect"]["score"], 0)

    def test_private_memory_does_not_leak_to_other_user(self) -> None:
        self.engine.chat(
            "g1", "u1", "小岚", "请记住：我对花生过敏。", use_llm=False
        )
        result = self.engine.chat(
            "g1", "u2", "小北", "花生过敏这件事你知道吗？", use_llm=False
        )
        self.assertFalse(
            any("花生" in hit["text"] for hit in result["recalled"]),
            result["recalled"],
        )
        self.assertEqual(self.engine.snapshot("g1", "u2")["graph"]["nodes"], [])

    def test_pinned_memory_survives_sleep(self) -> None:
        self.engine.chat(
            "g1", "u1", "小岚", "一定要记住：我的生日是 11 月 3 日。", use_llm=False
        )
        before = self.engine.snapshot("g1", "u1")["memories"]
        self.engine.sleep("g1")
        after = self.engine.snapshot("g1", "u1")["memories"]
        self.assertTrue(any(item["pinned"] for item in before))
        self.assertTrue(
            all(
                item["status"] == "active"
                for item in after
                if item["pinned"]
            )
        )

    def test_soft_forgetting_keeps_the_record(self) -> None:
        result = self.engine.chat(
            "g1", "u1", "小岚", "我喜欢喝茉莉花茶。", use_llm=False
        )
        memory_id = result["created_memories"][0]["id"]
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "UPDATE memories SET created_at=? WHERE id=?",
                (time.time() - 86400 * 365, memory_id),
            )
        summary = self.engine.sleep("g1")
        memories = self.engine.snapshot("g1", "u1")["memories"]
        row = next(item for item in memories if item["id"] == memory_id)
        self.assertGreaterEqual(summary["soft_forgotten"], 1)
        self.assertEqual(row["status"], "suppressed")


if __name__ == "__main__":
    unittest.main()


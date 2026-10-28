from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from .core import Fact, affect_label, embed, new_id, now_ts


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  user_name TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_group_time
  ON messages(group_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  owner_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'personal',
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  embedding TEXT NOT NULL,
  importance REAL NOT NULL,
  valence REAL NOT NULL DEFAULT 0,
  intensity REAL NOT NULL DEFAULT 0,
  pinned INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0.8,
  status TEXT NOT NULL DEFAULT 'active',
  source_message_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  last_accessed_at REAL,
  access_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_memories_scope
  ON memories(group_id, owner_id, visibility, status);

CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  name TEXT NOT NULL,
  node_type TEXT NOT NULL,
  importance REAL NOT NULL DEFAULT 0.5,
  last_seen_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_group_name ON nodes(group_id, name);

CREATE TABLE IF NOT EXISTS memory_entities (
  memory_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  PRIMARY KEY(memory_id, node_id),
  FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE,
  FOREIGN KEY(node_id) REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  source_node TEXT NOT NULL,
  relation TEXT NOT NULL,
  target_node TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 0.8,
  valid_from REAL NOT NULL,
  valid_to REAL,
  last_seen_at REAL NOT NULL,
  source_memory_id TEXT NOT NULL,
  FOREIGN KEY(source_node) REFERENCES nodes(id),
  FOREIGN KEY(target_node) REFERENCES nodes(id)
);
CREATE INDEX IF NOT EXISTS idx_edges_group_active
  ON edges(group_id, source_node, relation, valid_to);

CREATE TABLE IF NOT EXISTS affect (
  group_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  positive_count INTEGER NOT NULL DEFAULT 0,
  negative_count INTEGER NOT NULL DEFAULT 0,
  last_interaction_at REAL NOT NULL,
  last_reason TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS recall_log (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  payload TEXT NOT NULL
);
"""


class SQLiteStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def add_message(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        item = {
            "id": new_id("msg"),
            "group_id": group_id,
            "user_id": user_id,
            "user_name": user_name,
            "role": role,
            "content": content,
            "created_at": now_ts(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO messages
                   (id, group_id, user_id, user_name, role, content, created_at)
                   VALUES (:id, :group_id, :user_id, :user_name, :role, :content, :created_at)""",
                item,
            )
        return item

    def recent_messages(self, group_id: str, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM messages WHERE group_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (group_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def _upsert_node(
        self,
        conn: sqlite3.Connection,
        group_id: str,
        name: str,
        node_type: str,
        importance: float,
        at: float,
    ) -> str:
        digest = hashlib.blake2b(
            f"{group_id}|{node_type}|{name}".encode("utf-8"), digest_size=10
        ).hexdigest()
        node_id = f"node_{digest}"
        conn.execute(
            """INSERT INTO nodes(id, group_id, name, node_type, importance, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 importance=MAX(importance, excluded.importance),
                 last_seen_at=excluded.last_seen_at""",
            (node_id, group_id, name, node_type, importance, at),
        )
        return node_id

    def add_memory(
        self,
        group_id: str,
        source_message_id: str,
        fact: Fact,
        created_at: float | None = None,
    ) -> dict[str, Any]:
        at = created_at or now_ts()
        memory_id = new_id("mem")
        visibility = "shared" if fact.visibility == "shared" else "personal"
        owner_id = None if visibility == "shared" else fact.owner_id
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memories
                   (id, group_id, owner_id, visibility, kind, text, embedding,
                    importance, valence, intensity, pinned, confidence, status,
                    source_message_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                (
                    memory_id,
                    group_id,
                    owner_id,
                    visibility,
                    fact.kind,
                    fact.text,
                    json.dumps(embed(fact.text), separators=(",", ":")),
                    fact.importance,
                    fact.valence,
                    fact.intensity,
                    int(fact.pinned),
                    fact.confidence,
                    source_message_id,
                    at,
                ),
            )
            subject_id = self._upsert_node(
                conn, group_id, fact.subject, "person", max(0.6, fact.importance / 10), at
            )
            object_id = self._upsert_node(
                conn, group_id, fact.object, "topic", max(0.4, fact.importance / 10), at
            )
            conn.execute(
                "INSERT OR IGNORE INTO memory_entities(memory_id, node_id) VALUES (?, ?)",
                (memory_id, subject_id),
            )
            conn.execute(
                "INSERT OR IGNORE INTO memory_entities(memory_id, node_id) VALUES (?, ?)",
                (memory_id, object_id),
            )
            conn.execute(
                """UPDATE edges SET valid_to=?, last_seen_at=?
                   WHERE group_id=? AND source_node=? AND relation=?
                     AND target_node<>? AND valid_to IS NULL""",
                (at, at, group_id, subject_id, fact.predicate, object_id),
            )
            current = conn.execute(
                """SELECT id FROM edges WHERE group_id=? AND source_node=?
                   AND relation=? AND target_node=? AND valid_to IS NULL""",
                (group_id, subject_id, fact.predicate, object_id),
            ).fetchone()
            if current:
                conn.execute(
                    "UPDATE edges SET weight=MAX(weight, ?), last_seen_at=? WHERE id=?",
                    (fact.confidence, at, current["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO edges
                       (id, group_id, source_node, relation, target_node, weight,
                        valid_from, last_seen_at, source_memory_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        new_id("edge"),
                        group_id,
                        subject_id,
                        fact.predicate,
                        object_id,
                        fact.confidence,
                        at,
                        at,
                        memory_id,
                    ),
                )
        return {
            "id": memory_id,
            "text": fact.text,
            "kind": fact.kind,
            "owner_id": owner_id,
            "visibility": visibility,
            "importance": fact.importance,
            "pinned": fact.pinned,
            "created_at": at,
        }

    def update_affect(
        self,
        group_id: str,
        user_id: str,
        delta: float,
        reason: str,
    ) -> dict[str, Any]:
        at = now_ts()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT score, positive_count, negative_count FROM affect WHERE group_id=? AND user_id=?",
                (group_id, user_id),
            ).fetchone()
            score = float(row["score"]) if row else 0.0
            positive = int(row["positive_count"]) if row else 0
            negative = int(row["negative_count"]) if row else 0
            score = max(-50.0, min(50.0, score + delta))
            positive += int(delta > 0)
            negative += int(delta < 0)
            conn.execute(
                """INSERT INTO affect
                   (group_id, user_id, score, positive_count, negative_count,
                    last_interaction_at, last_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(group_id, user_id) DO UPDATE SET
                     score=excluded.score,
                     positive_count=excluded.positive_count,
                     negative_count=excluded.negative_count,
                     last_interaction_at=excluded.last_interaction_at,
                     last_reason=excluded.last_reason""",
                (group_id, user_id, score, positive, negative, at, reason),
            )
        return {"score": score, "label": affect_label(score)}

    def get_affect(self, group_id: str, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM affect WHERE group_id=? AND user_id=?",
                (group_id, user_id),
            ).fetchone()
        if not row:
            return {
                "score": 0.0,
                "label": "普通",
                "positive_count": 0,
                "negative_count": 0,
                "last_reason": "",
            }
        data = dict(row)
        data["label"] = affect_label(float(data["score"]))
        return data

    def _graph_memory_ids(self, group_id: str, query: str, max_hops: int = 2) -> set[str]:
        with self._connect() as conn:
            nodes = conn.execute(
                "SELECT id, name FROM nodes WHERE group_id=?", (group_id,)
            ).fetchall()
            seeds = {
                row["id"]
                for row in nodes
                if row["name"] and row["name"].lower() in query.lower()
            }
            if not seeds:
                return set()
            reached = set(seeds)
            frontier = set(seeds)
            for _ in range(max_hops):
                placeholders = ",".join("?" for _ in frontier)
                rows = conn.execute(
                    f"""SELECT source_node, target_node FROM edges
                        WHERE group_id=? AND valid_to IS NULL
                          AND (source_node IN ({placeholders})
                               OR target_node IN ({placeholders}))""",
                    (group_id, *frontier, *frontier),
                ).fetchall()
                next_frontier = {
                    node
                    for row in rows
                    for node in (row["source_node"], row["target_node"])
                } - reached
                reached.update(next_frontier)
                frontier = next_frontier
                if not frontier:
                    break
            if not reached:
                return set()
            placeholders = ",".join("?" for _ in reached)
            rows = conn.execute(
                f"""SELECT DISTINCT memory_id FROM memory_entities
                    WHERE node_id IN ({placeholders})""",
                tuple(reached),
            ).fetchall()
        return {row["memory_id"] for row in rows}

    def candidates(
        self,
        group_id: str,
        user_id: str,
        query: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], set[str]]:
        graph_ids = self._graph_memory_ids(group_id, query)
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM memories
                   WHERE group_id=?
                     AND ((owner_id=? AND visibility='personal') OR visibility='shared')
                     AND status IN ('active', 'suppressed')
                   ORDER BY pinned DESC, importance DESC, created_at DESC
                   LIMIT ?""",
                (group_id, user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows], graph_ids

    def touch_memories(self, memory_ids: Iterable[str]) -> None:
        ids = list(memory_ids)
        if not ids:
            return
        at = now_ts()
        with self._connect() as conn:
            conn.executemany(
                """UPDATE memories
                   SET last_accessed_at=?, access_count=access_count+1
                   WHERE id=?""",
                [(at, memory_id) for memory_id in ids],
            )

    def log_recall(
        self,
        group_id: str,
        user_id: str,
        message_id: str,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO recall_log
                   (id, group_id, user_id, message_id, created_at, payload)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    new_id("recall"),
                    group_id,
                    user_id,
                    message_id,
                    now_ts(),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def latest_recall(self, group_id: str, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT payload FROM recall_log
                   WHERE group_id=? AND user_id=?
                   ORDER BY created_at DESC LIMIT 1""",
                (group_id, user_id),
            ).fetchone()
        if not row:
            return {"recalled": [], "mode": "none", "extraction": None, "affect": None}
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return {"recalled": [], "mode": "none", "extraction": None, "affect": None}

    def summarize_memories(self, group_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, owner_id, visibility, kind, text, importance, status,
                          pinned, created_at, last_accessed_at, access_count
                   FROM memories WHERE group_id=?
                   ORDER BY created_at DESC""",
                (group_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def graph(
        self,
        group_id: str,
        visible_memory_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            nodes = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM nodes WHERE group_id=? ORDER BY importance DESC",
                    (group_id,),
                ).fetchall()
            ]
            edges = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM edges WHERE group_id=? ORDER BY last_seen_at DESC",
                    (group_id,),
                ).fetchall()
            ]
            if visible_memory_ids is not None:
                if visible_memory_ids:
                    placeholders = ",".join("?" for _ in visible_memory_ids)
                    visible_nodes = {
                        row["node_id"]
                        for row in conn.execute(
                            f"""SELECT DISTINCT node_id FROM memory_entities
                                WHERE memory_id IN ({placeholders})""",
                            tuple(visible_memory_ids),
                        ).fetchall()
                    }
                else:
                    visible_nodes = set()
                nodes = [node for node in nodes if node["id"] in visible_nodes]
                node_ids = {node["id"] for node in nodes}
                edges = [
                    edge
                    for edge in edges
                    if edge["source_node"] in node_ids and edge["target_node"] in node_ids
                ]
        return {"nodes": nodes, "edges": edges}

    def apply_sleep(self, group_id: str, half_life_days: float, random_rate: float) -> dict[str, int]:
        at = now_ts()
        forgot = 0
        restored = 0
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, created_at, importance, pinned, status
                   FROM memories WHERE group_id=?""",
                (group_id,),
            ).fetchall()
            for row in rows:
                age_days = max(0.0, (at - row["created_at"]) / 86400.0)
                retrievability = pow(0.5, age_days / max(0.1, half_life_days))
                if row["pinned"]:
                    continue
                digest = hashlib.blake2b(
                    f"{row['id']}|{int(at // 86400)}".encode("utf-8"), digest_size=4
                ).digest()
                draw = int.from_bytes(digest, "big") / 2**32
                should_forget = (
                    retrievability < 0.4
                    and row["importance"] < 8
                    and draw < random_rate + (0.4 - retrievability) * 0.5
                )
                if should_forget and row["status"] != "suppressed":
                    conn.execute(
                        "UPDATE memories SET status='suppressed' WHERE id=?",
                        (row["id"],),
                    )
                    forgot += 1
                elif not should_forget and row["status"] == "suppressed":
                    conn.execute(
                        "UPDATE memories SET status='active' WHERE id=?",
                        (row["id"],),
                    )
                    restored += 1
            conn.execute(
                "UPDATE affect SET score=score*0.98 WHERE group_id=?", (group_id,)
            )
        return {"soft_forgotten": forgot, "restored": restored}

    def snapshot(self, group_id: str, user_id: str) -> dict[str, Any]:
        memories = [
            row
            for row in self.summarize_memories(group_id)
            if row["visibility"] == "shared" or row["owner_id"] == user_id
        ]
        visible_ids = {memory["id"] for memory in memories}
        return {
            "messages": self.recent_messages(group_id, 60),
            "memories": memories,
            "graph": self.graph(group_id, visible_ids),
            "affect": self.get_affect(group_id, user_id),
            "last_recall": self.latest_recall(group_id, user_id),
        }

    def reset_demo(self, group_id: str) -> None:
        with self._connect() as conn:
            for table in (
                "memory_entities",
                "edges",
                "nodes",
                "memories",
                "recall_log",
                "messages",
                "affect",
            ):
                conn.execute(f"DELETE FROM {table} WHERE group_id=?" if table != "memory_entities" else
                             "DELETE FROM memory_entities WHERE memory_id IN (SELECT id FROM memories WHERE group_id=?)",
                             (group_id,))


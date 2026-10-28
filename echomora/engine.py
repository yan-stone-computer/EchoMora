from __future__ import annotations

from typing import Any

from .core import Fact, affect_label, now_ts
from .llm import DeepSeekClient
from .memory import (
    RecallController,
    affect_delta,
    extract_memory,
    offline_reply,
    render_prompt,
)
from .settings import Settings
from .store import SQLiteStore


class EchoMora:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = SQLiteStore(settings.db_path)
        self.deepseek = DeepSeekClient(
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.chat_model,
            settings.extract_model,
        )
        self.recall = RecallController(
            settings.recall_top_n,
            settings.candidate_limit,
            settings.half_life_days,
        )

    def chat(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        content: str,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        content = content.strip()[:4000]
        if not content:
            raise ValueError("消息不能为空")
        source = self.store.add_message(
            group_id, user_id, user_name, "user", content
        )
        history = self.store.recent_messages(group_id, self.settings.short_term_turns)
        context = "\n".join(
            f"{item['user_name']}：{item['content'][:240]}" for item in history[-12:]
        )
        extraction = extract_memory(self.deepseek, user_name, content, context)

        created: list[dict[str, Any]] = []
        for extracted_fact in extraction.facts:
            fact: Fact = extracted_fact
            fact.owner_id = user_id
            fact.visibility = "personal"
            created.append(
                self.store.add_memory(
                    group_id,
                    source["id"],
                    fact,
                    now_ts(),
                )
            )

        delta = affect_delta(extraction)
        if delta:
            affection = self.store.update_affect(
                group_id, user_id, delta, extraction.emotion
            )
        else:
            affection = self.store.get_affect(group_id, user_id)
        affection["label"] = affect_label(float(affection["score"]))

        candidates, graph_ids = self.store.candidates(
            group_id,
            user_id,
            content,
            self.settings.candidate_limit,
        )
        recalled = self.recall.rank(
            content, candidates, graph_ids, float(affection["score"])
        )
        self.store.touch_memories(hit.memory_id for hit in recalled)
        system_prompt = render_prompt(
            user_name,
            affection,
            extraction,
            history,
            recalled,
            self.settings.token_budget,
        )

        mode = "offline"
        llm_error = ""
        if use_llm and self.deepseek.enabled:
            try:
                reply = self.deepseek.reply(system_prompt, content)
                mode = "deepseek"
            except Exception as exc:
                llm_error = str(exc)
                reply = offline_reply(user_name, content, affection, recalled)
                mode = "offline-fallback"
        else:
            reply = offline_reply(user_name, content, affection, recalled)

        assistant = self.store.add_message(
            group_id, "assistant", "EchoMora", "assistant", reply
        )
        payload = {
            "message_id": source["id"],
            "mode": mode,
            "llm_error": llm_error,
            "affect": affection,
            "extraction": extraction.to_dict(),
            "created_memories": created,
            "recalled": [hit.to_dict() for hit in recalled],
        }
        self.store.log_recall(group_id, user_id, source["id"], payload)
        return {
            **payload,
            "reply": reply,
            "user_message": source,
            "assistant_message": assistant,
            "short_term_count": len(history),
            "system_prompt_preview": system_prompt[:1200],
        }

    def snapshot(self, group_id: str, user_id: str) -> dict[str, Any]:
        return self.store.snapshot(group_id, user_id)

    def sleep(self, group_id: str) -> dict[str, Any]:
        result = self.store.apply_sleep(
            group_id,
            self.settings.half_life_days,
            self.settings.random_forget_rate,
        )
        return {
            **result,
            "policy": {
                "half_life_days": self.settings.half_life_days,
                "random_forget_rate": self.settings.random_forget_rate,
                "pinned_protected": True,
            },
        }

    def reset(self, group_id: str) -> None:
        self.store.reset_demo(group_id)

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "version": "0.1.0",
            "llm": "deepseek" if self.deepseek.enabled else "offline",
            "db": str(self.settings.db_path),
        }


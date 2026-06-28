import threading
import unittest
from datetime import datetime

from jarvis_os.core.context.context_builder import ContextBuilder
from jarvis_os.core.context.models import ContextSection, ContextPriority
from jarvis_os.core.context.token_budget import ContextBudget
from jarvis_os.core.domain.entities import LLMMessage


class TestContextBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.system_prompt = "You are Jarvis."
        self.budget = ContextBudget(max_prompt_tokens=10)

        # Deterministic token estimator: token count == number of words
        self.estimator = lambda s: len((s or "").split())
        self.builder = ContextBuilder(
            system_prompt=self.system_prompt,
            budget=self.budget,
            token_estimator=self.estimator,
        )

    def test_empty_context_handling(self) -> None:
        res = self.builder.build(user_request="hi", conversation_history=())
        self.assertTrue(any(p[1] == "hi" for p in res.prompt_messages))

    def test_context_ordering_by_priority(self) -> None:
        memories = [ContextSection(name="m1", priority=ContextPriority.MEMORY, content="alpha")]
        docs = [ContextSection(name="d1", priority=ContextPriority.DOCUMENT, content="beta")]

        res = self.builder.build(
            user_request="q",
            retrieved_memories=memories,
            retrieved_documents=docs,
        )

        # System + included sections + user request. Ensure memory appears before document.
        joined = "\n".join(p[1] for p in res.prompt_messages)
        self.assertIn("[m1]", joined)
        self.assertIn("[d1]", joined)
        self.assertLess(joined.index("[m1]"), joined.index("[d1]"))

    def test_token_budget_enforcement_trims(self) -> None:
        # system_prompt tokens=3 (You are Jarvis.)
        # remaining=7. Add large section.
        sec = ContextSection(name="big", priority=ContextPriority.MEMORY, content="one two three four five six seven eight")
        res = self.builder.build(user_request="q", retrieved_memories=[sec])

        # Ensure trimmed content is not longer than budget.
        included_contents = [s.content for s in res.included_sections if s.name == "big"]
        self.assertEqual(len(included_contents), 1)
        # Budget estimator uses words. remaining was 7 -> big content should have <=7 words
        self.assertLessEqual(len(included_contents[0].split()), 7)

    def test_metadata_preservation(self) -> None:
        sec = ContextSection(name="m", priority=ContextPriority.MEMORY, content="alpha", metadata={"source": "unit"})
        res = self.builder.build(user_request="q", retrieved_memories=[sec])
        included = [s for s in res.included_sections if s.name == "m"][0]
        self.assertEqual(included.metadata["source"], "unit")

    def test_thread_safety_deterministic(self) -> None:
        sec = ContextSection(name="m", priority=ContextPriority.MEMORY, content="alpha beta")
        results = []
        errors = []

        def worker() -> None:
            try:
                for _ in range(20):
                    results.append(self.builder.build(user_request="q", retrieved_memories=[sec]))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertTrue(all(r == results[0] for r in results))


if __name__ == "__main__":
    unittest.main()


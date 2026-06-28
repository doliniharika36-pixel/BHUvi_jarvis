import threading
import unittest

from jarvis_os.core.decision.decision_engine import DecisionEngine
from jarvis_os.core.decision.decision_policy import DefaultDecisionPolicy
from jarvis_os.core.decision.models import DecisionContext, DecisionType


class TestDecisionEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DecisionEngine(policy=DefaultDecisionPolicy())

    def test_direct_response_routing(self) -> None:
        ctx = DecisionContext(request_text="hello", requires_memory=False, requires_documents=False, requires_tools=False, requires_clarification=False)
        res = self.engine.decide(ctx)
        self.assertEqual(res.decision_type, DecisionType.DIRECT_LLM_RESPONSE)

    def test_clarification_routing(self) -> None:
        ctx = DecisionContext(request_text="?", requires_clarification=True)
        res = self.engine.decide(ctx)
        self.assertEqual(res.decision_type, DecisionType.CLARIFICATION)

    def test_memory_needed_routing(self) -> None:
        ctx = DecisionContext(request_text="remember this", requires_memory=True)
        res = self.engine.decide(ctx)
        self.assertEqual(res.decision_type, DecisionType.MEMORY_RETRIEVAL)

    def test_retrieval_needed_routing_documents(self) -> None:
        ctx = DecisionContext(request_text="search docs", requires_documents=True)
        res = self.engine.decide(ctx)
        self.assertEqual(res.decision_type, DecisionType.DOCUMENT_RETRIEVAL)

    def test_tool_execution_plan_routing(self) -> None:
        ctx = DecisionContext(
            request_text="run something",
            requires_tools=True,
            tool_candidates=("open_chrome", "screenshot"),
        )
        res = self.engine.decide(ctx)
        self.assertEqual(res.decision_type, DecisionType.TOOL_EXECUTION_PLAN)
        self.assertEqual(res.tool_plan, ("open_chrome", "screenshot"))

    def test_priority_order_deterministic(self) -> None:
        # Clarification should win over tools.
        ctx = DecisionContext(
            request_text="x",
            requires_clarification=True,
            requires_tools=True,
            tool_candidates=("t1",),
        )
        res = self.engine.decide(ctx)
        self.assertEqual(res.decision_type, DecisionType.CLARIFICATION)

    def test_dependency_isolation_and_determinism(self) -> None:
        # Engine does not touch infra. Calling twice yields same result.
        ctx = DecisionContext(request_text="hello", requires_memory=True)
        a = self.engine.decide(ctx)
        b = self.engine.decide(ctx)
        self.assertEqual(a, b)

    def test_thread_safety(self) -> None:
        ctx = DecisionContext(request_text="hi")
        results = []
        errors = []

        def worker() -> None:
            try:
                for _ in range(50):
                    results.append(self.engine.decide(ctx))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertTrue(all(r.decision_type == DecisionType.DIRECT_LLM_RESPONSE for r in results))


if __name__ == "__main__":
    unittest.main()


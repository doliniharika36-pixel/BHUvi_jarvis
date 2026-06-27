"""
Contract Test for LLMPort.
"""
import unittest
from typing import Any, Dict, List, Optional
from jarvis_os.core.ports.llm import LLMPort
from jarvis_os.core.domain.entities import LLMMessage, LLMResponse
from jarvis_os.core.domain.exceptions import LLMException

class TestLLMPortContract(unittest.TestCase):
    """Verifies that the LLMPort interface conforms to design specifications."""

    def test_interface_is_abstract(self):
        """Asserts that the LLMPort cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            LLMPort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompleteLLM(LLMPort):
            pass

        with self.assertRaises(TypeError):
            IncompleteLLM()  # type: ignore

    def test_valid_implementation_signatures(self):
        """Asserts that a fully-conforming mock subclass can be instantiated."""
        class MockLLM(LLMPort):
            def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
                if prompt == "fail":
                    raise LLMException("Failed LLM operation")
                return f"Response to: {prompt}"

            def chat(self, messages: List[LLMMessage], options: Optional[Dict[str, Any]] = None) -> LLMResponse:
                return LLMResponse(content="Hello", model_name="qwen2.5:1.5b")

            def embed(self, text: str) -> List[float]:
                return [0.1, 0.2, 0.3]

        llm = MockLLM()
        self.assertIsInstance(llm, LLMPort)
        
        # Test generate contract
        res = llm.generate("test prompt")
        self.assertEqual(res, "Response to: test prompt")
        
        # Test generate failure propagation contract
        with self.assertRaises(LLMException):
            llm.generate("fail")
            
        # Test chat contract
        chat_res = llm.chat([LLMMessage(role="user", content="Hi")])
        self.assertIsInstance(chat_res, LLMResponse)
        self.assertEqual(chat_res.content, "Hello")
        
        # Test embed contract
        emb = llm.embed("text")
        self.assertEqual(emb, [0.1, 0.2, 0.3])

if __name__ == "__main__":
    unittest.main()

"""
Contract Test for RuntimePort.
"""
import unittest
from jarvis_os.core.ports.runtime import RuntimePort
from jarvis_os.core.domain.exceptions import JarvisException

class TestRuntimePortContract(unittest.TestCase):
    """Verifies that the RuntimePort interface conforms to design specifications."""

    def test_interface_is_abstract(self):
        """Asserts that the RuntimePort cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            RuntimePort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompleteRuntime(RuntimePort):
            pass

        with self.assertRaises(TypeError):
            IncompleteRuntime()  # type: ignore

    def test_valid_implementation_signatures(self):
        """Asserts that a fully-conforming mock subclass can be instantiated."""
        class MockRuntime(RuntimePort):
            def __init__(self):
                self._running = False
                self.bootstrapped = False

            def bootstrap(self) -> None:
                if self.bootstrapped:
                    raise JarvisException("Already bootstrapped")
                self._running = True
                self.bootstrapped = True

            def shutdown(self) -> None:
                self._running = False

            def is_running(self) -> bool:
                return self._running

        runtime = MockRuntime()
        self.assertIsInstance(runtime, RuntimePort)
        self.assertFalse(runtime.is_running())
        
        # Test bootstrap
        runtime.bootstrap()
        self.assertTrue(runtime.is_running())
        
        # Test error propagation on multiple bootstrap
        with self.assertRaises(JarvisException):
            runtime.bootstrap()
            
        # Test shutdown
        runtime.shutdown()
        self.assertFalse(runtime.is_running())

if __name__ == "__main__":
    unittest.main()

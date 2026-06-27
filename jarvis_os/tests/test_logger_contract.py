"""
Contract Test for LoggerPort.
"""
import unittest
from typing import Any, Optional
from jarvis_os.core.ports.logger import LoggerPort

class TestLoggerPortContract(unittest.TestCase):
    """Verifies that the LoggerPort interface conforms to design specifications."""

    def test_interface_is_abstract(self):
        """Asserts that the LoggerPort cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            LoggerPort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompleteLogger(LoggerPort):
            pass

        with self.assertRaises(TypeError):
            IncompleteLogger()  # type: ignore

    def test_valid_implementation_signatures(self):
        """Asserts that a fully-conforming mock subclass can be instantiated."""
        class MockLogger(LoggerPort):
            def __init__(self):
                self.logs = []
                self.level = "INFO"

            def debug(self, message: str, **kwargs: Any) -> None:
                self.logs.append(("DEBUG", message, kwargs))

            def info(self, message: str, **kwargs: Any) -> None:
                self.logs.append(("INFO", message, kwargs))

            def warning(self, message: str, **kwargs: Any) -> None:
                self.logs.append(("WARNING", message, kwargs))

            def error(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
                self.logs.append(("ERROR", message, error, kwargs))

            def critical(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
                self.logs.append(("CRITICAL", message, error, kwargs))

            def set_level(self, level: str) -> None:
                self.level = level

        logger = MockLogger()
        self.assertIsInstance(logger, LoggerPort)
        
        # Test basic contract calls
        logger.debug("Debug message", user="test_user")
        logger.info("Info message")
        logger.warning("Warning message")
        
        ex = ValueError("test error")
        logger.error("Error occurred", error=ex)
        logger.critical("Critical failure", error=ex)
        
        self.assertEqual(len(logger.logs), 5)
        self.assertEqual(logger.logs[0][0], "DEBUG")
        self.assertEqual(logger.logs[0][1], "Debug message")
        self.assertEqual(logger.logs[0][2], {"user": "test_user"})
        
        self.assertEqual(logger.logs[3][0], "ERROR")
        self.assertEqual(logger.logs[3][2], ex)

        logger.set_level("DEBUG")
        self.assertEqual(logger.level, "DEBUG")

if __name__ == "__main__":
    unittest.main()

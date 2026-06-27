"""
Unit tests for StructuredLogger concrete implementation of LoggerPort.
"""
import json
import unittest
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict
from jarvis_os.infrastructure.logger.structured_logger import (
    StructuredLogger,
    set_correlation_id,
    clear_correlation_id,
    correlation_context,
)
from jarvis_os.core.ports.config import ConfigurationPort

class MockLoggerConfig(ConfigurationPort):
    """Minimal mock config to satisfy StructuredLogger dependencies during testing."""
    def __init__(self, log_file: str, log_level: str = "DEBUG"):
        self.data = {
            "log.level": log_level,
            "log.file_path": log_file
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def get_boolean(self, key: str, default: bool = False) -> bool:
        return bool(self.get(key, default))

    def get_int(self, key: str, default: int = 0) -> int:
        return int(self.get(key, default))

    def get_string(self, key: str, default: str = "") -> str:
        return str(self.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def load(self) -> None:
        pass

    def validate(self) -> bool:
        return True

    def get_all(self) -> Dict[str, Any]:
        return self.data.copy()


class TestStructuredLogger(unittest.TestCase):
    """Verifies that the StructuredLogger concrete adapter behaves correctly."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "test_jarvis.log"
        self.config = MockLoggerConfig(log_file=str(self.log_file))
        self.logger = StructuredLogger(self.config)

    def tearDown(self):
        # Explicitly remove handlers to close file handles before deleting directory
        for handler in self.logger._logger.handlers:
            handler.close()
        self.temp_dir.cleanup()
        clear_correlation_id()

    def _read_log_lines(self) -> list:
        """Reads log file contents and parses each line as a JSON object."""
        lines = []
        if self.log_file.exists():
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(json.loads(line))
        return lines

    def test_structured_log_levels(self):
        """Asserts that logs write correct levels, formats, and messages in JSON."""
        self.logger.debug("debug msg", context="test")
        self.logger.info("info msg")
        self.logger.warning("warn msg")

        lines = self._read_log_lines()
        self.assertEqual(len(lines), 3)

        self.assertEqual(lines[0]["level"], "DEBUG")
        self.assertEqual(lines[0]["message"], "debug msg")
        self.assertEqual(lines[0]["metadata"], {"context": "test"})
        self.assertTrue("timestamp" in lines[0])

        self.assertEqual(lines[1]["level"], "INFO")
        self.assertEqual(lines[1]["message"], "info msg")
        self.assertEqual(lines[1]["metadata"], {})

        self.assertEqual(lines[2]["level"], "WARNING")
        self.assertEqual(lines[2]["message"], "warn msg")

    def test_log_level_threshold(self):
        """Asserts that messages below the configured log level are filtered out."""
        # Re-initialize logger with INFO level config
        info_config = MockLoggerConfig(log_file=str(self.log_file), log_level="INFO")
        logger = StructuredLogger(info_config)

        logger.debug("should not appear")
        logger.info("should appear")

        # Close handler before reading
        for h in logger._logger.handlers:
            h.close()

        lines = self._read_log_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["level"], "INFO")
        self.assertEqual(lines[0]["message"], "should appear")

    def test_correlation_id_context(self):
        """Asserts that the correlation ID propagates through logs and clears correctly."""
        # 1. Log without correlation ID
        self.logger.info("no cid")
        
        # 2. Log within correlation ID context
        with correlation_context("REQ-12345"):
            self.logger.warning("in context")

        # 3. Log after context exits
        self.logger.info("after context")

        lines = self._read_log_lines()
        self.assertEqual(len(lines), 3)

        self.assertFalse("correlation_id" in lines[0])
        
        self.assertEqual(lines[1]["correlation_id"], "REQ-12345")
        self.assertEqual(lines[1]["message"], "in context")
        
        self.assertFalse("correlation_id" in lines[2])

    def test_correlation_id_thread_isolation(self):
        """Asserts that correlation IDs are isolated to separate threads."""
        results = {}

        def thread_target(tid, cid):
            with correlation_context(cid):
                self.logger.info(f"msg from {tid}")
                lines = self._read_log_lines()
                # Find current log message in the file to check its CID
                for line in reversed(lines):
                    if line["message"] == f"msg from {tid}":
                        results[tid] = line.get("correlation_id")
                        break

        # Setup thread 1 with CID
        t1 = threading.Thread(target=thread_target, args=("T1", "CID-T1"))
        t2 = threading.Thread(target=thread_target, args=("T2", "CID-T2"))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results.get("T1"), "CID-T1")
        self.assertEqual(results.get("T2"), "CID-T2")

    def test_exception_serialization(self):
        """Asserts that error and critical levels serialize tracebacks to log output."""
        err = ValueError("Invalid operation")
        try:
            raise err
        except ValueError as ex:
            self.logger.error("action failed", error=ex, component="calculator")

        lines = self._read_log_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["level"], "ERROR")
        self.assertEqual(lines[0]["message"], "action failed")
        self.assertEqual(lines[0]["metadata"], {"component": "calculator"})
        self.assertTrue("exception" in lines[0])
        self.assertTrue("ValueError: Invalid operation" in lines[0]["exception"])

    def test_dynamic_set_level(self):
        """Asserts that set_level updates log filtering dynamically at runtime."""
        self.logger.set_level("WARNING")
        
        self.logger.info("ignored")
        self.logger.warning("written")

        lines = self._read_log_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["level"], "WARNING")
        self.assertEqual(lines[0]["message"], "written")

        # Test setting invalid level
        with self.assertRaises(ValueError):
            self.logger.set_level("NOT_A_LEVEL")

if __name__ == "__main__":
    unittest.main()

"""
Contract Test for ConfigurationPort.
"""
import unittest
from abc import ABC
from typing import Any, Dict
from jarvis_os.core.ports.config import ConfigurationPort
from jarvis_os.core.domain.exceptions import ConfigurationError

class TestConfigurationPortContract(unittest.TestCase):
    """Verifies that the ConfigurationPort interface conforms to design specifications."""

    def test_interface_is_abstract(self):
        """Asserts that the ConfigurationPort cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            ConfigurationPort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompleteConfig(ConfigurationPort):
            pass

        with self.assertRaises(TypeError):
            IncompleteConfig()  # type: ignore

    def test_valid_implementation_signatures(self):
        """Asserts that a fully-conforming mock subclass can be instantiated."""
        class MockConfig(ConfigurationPort):
            def __init__(self):
                self._data = {}

            def get(self, key: str, default: Any = None) -> Any:
                return self._data.get(key, default)

            def get_boolean(self, key: str, default: bool = False) -> bool:
                val = self.get(key, default)
                return bool(val)

            def get_int(self, key: str, default: int = 0) -> int:
                val = self.get(key, default)
                return int(val)

            def get_string(self, key: str, default: str = "") -> str:
                val = self.get(key, default)
                return str(val)

            def set(self, key: str, value: Any) -> None:
                self._data[key] = value

            def load(self) -> None:
                pass

            def validate(self) -> bool:
                if self.get("invalid_key"):
                    raise ConfigurationError("Invalid key exists")
                return True

            def get_all(self) -> Dict[str, Any]:
                return self._data.copy()

        config = MockConfig()
        self.assertIsInstance(config, ConfigurationPort)
        
        # Test basic contract operations
        config.set("test.int_key", 42)
        config.set("test.bool_key", True)
        config.set("test.str_key", "hello")

        self.assertEqual(config.get_int("test.int_key"), 42)
        self.assertTrue(config.get_boolean("test.bool_key"))
        self.assertEqual(config.get_string("test.str_key"), "hello")
        self.assertEqual(config.get("test.missing", "default"), "default")
        
        # Test error propagation contract
        config.set("invalid_key", True)
        with self.assertRaises(ConfigurationError):
            config.validate()

if __name__ == "__main__":
    unittest.main()

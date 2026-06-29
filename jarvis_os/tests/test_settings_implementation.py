"""
Unit tests for EnvSettings concrete implementation of ConfigurationPort.
"""
import os
import unittest
import tempfile
from pathlib import Path
from jarvis_os.infrastructure.config.settings import EnvSettings
from jarvis_os.core.domain.exceptions import ConfigurationError

class TestEnvSettings(unittest.TestCase):
    """Verifies that the EnvSettings concrete adapter functions correctly."""

    def test_default_values(self):
        """Asserts that defaults are applied if no env file exists."""
        settings = EnvSettings(env_file_path="nonexistent_file.env")
        settings.load()
        
        self.assertEqual(settings.get("llm.model"), "qwen2.5:1.5b")
        self.assertEqual(settings.get_string("llm.url"), "http://localhost:11434")
        self.assertEqual(settings.get_int("nonexistent", 100), 100)
        self.assertTrue(settings.get_boolean("security.sandbox_enabled"))
        self.assertEqual(settings.get("security.allowed_roots"), [])
        
        # Defaults validation should pass out-of-the-box
        self.assertTrue(settings.validate())

    def test_type_conversion_boolean(self):
        """Asserts that boolean type conversion behaves correctly for strings and raw bools."""
        settings = EnvSettings()
        settings.set("key.bool_raw", True)
        settings.set("key.bool_str_true", "true")
        settings.set("key.bool_str_1", "1")
        settings.set("key.bool_str_yes", "yes")
        settings.set("key.bool_str_on", "on")
        settings.set("key.bool_str_false", "false")
        settings.set("key.bool_str_other", "something_else")

        self.assertTrue(settings.get_boolean("key.bool_raw"))
        self.assertTrue(settings.get_boolean("key.bool_str_true"))
        self.assertTrue(settings.get_boolean("key.bool_str_1"))
        self.assertTrue(settings.get_boolean("key.bool_str_yes"))
        self.assertTrue(settings.get_boolean("key.bool_str_on"))
        self.assertFalse(settings.get_boolean("key.bool_str_false"))
        self.assertFalse(settings.get_boolean("key.bool_str_other"))

    def test_type_conversion_int(self):
        """Asserts that integer conversion converts correctly or falls back to default."""
        settings = EnvSettings()
        settings.set("key.int_raw", 42)
        settings.set("key.int_str", "100")
        settings.set("key.int_invalid", "abc")

        self.assertEqual(settings.get_int("key.int_raw"), 42)
        self.assertEqual(settings.get_int("key.int_str"), 100)
        self.assertEqual(settings.get_int("key.int_invalid", 999), 999)

    def test_load_from_dotenv_file(self):
        """Asserts that config parameters are read correctly from a physical .env file."""
        # Create a temporary .env file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as temp_env:
            temp_env.write("# This is a comment\n")
            temp_env.write("llm.model = qwen2.5:3b\n")
            temp_env.write("JARVIS_LLM_URL = http://127.0.0.1:11434\n")
            temp_env.write("JARVIS_SECURITY_SANDBOX_ENABLED = false\n")
            temp_env.write("JARVIS_SECURITY_ALLOWED_ROOTS = C:\\workspace, D:\\media\n")
            temp_env_path = temp_env.name

        try:
            settings = EnvSettings(env_file_path=temp_env_path)
            settings.load()

            self.assertEqual(settings.get("llm.model"), "qwen2.5:3b")
            self.assertEqual(settings.get("llm.url"), "http://127.0.0.1:11434")
            self.assertFalse(settings.get_boolean("security.sandbox_enabled"))
            self.assertEqual(settings.get("security.allowed_roots"), ["C:\\workspace", "D:\\media"])
        finally:
            # Clean up the file
            Path(temp_env_path).unlink(missing_ok=True)

    def test_os_environment_overrides(self):
        """Asserts that OS environment variables override .env file settings."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as temp_env:
            temp_env.write("JARVIS_LLM_MODEL = model-from-dotenv\n")
            temp_env_path = temp_env.name

        try:
            settings = EnvSettings(env_file_path=temp_env_path)

            # Override using OS environment variable
            os.environ["JARVIS_LLM_MODEL"] = "model-from-os-env"
            settings.load()

            self.assertEqual(settings.get("llm.model"), "model-from-os-env")
        finally:
            # Clean up
            Path(temp_env_path).unlink(missing_ok=True)
            if "JARVIS_LLM_MODEL" in os.environ:
                del os.environ["JARVIS_LLM_MODEL"]

    def test_validation_rules(self):
        """Asserts that validation checks raise ConfigurationError for invalid settings."""
        settings = EnvSettings()
        settings.load()

        # Valid states should validate successfully
        self.assertTrue(settings.validate())

        # Test invalid llm.url
        settings.set("llm.url", "invalid-url-format")
        with self.assertRaises(ConfigurationError):
            settings.validate()

        # Test empty llm.url
        settings.set("llm.url", "")
        with self.assertRaises(ConfigurationError):
            settings.validate()

        # Restore URL
        settings.set("llm.url", "http://localhost:11434")

        # Test invalid log.level
        settings.set("log.level", "SUPER_CRITICAL")
        with self.assertRaises(ConfigurationError):
            settings.validate()

        # Restore level
        settings.set("log.level", "info")
        self.assertTrue(settings.validate())

        # Test empty db.path
        settings.set("db.path", "")
        with self.assertRaises(ConfigurationError):
            settings.validate()

        # Restore db.path
        settings.set("db.path", "jarvis.db")

        # Test empty llm.model
        settings.set("llm.model", "")
        with self.assertRaises(ConfigurationError):
            settings.validate()

if __name__ == "__main__":
    unittest.main()

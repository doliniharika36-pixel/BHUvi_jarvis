"""
Concrete implementation of ConfigurationPort using .env files and environment variables.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from jarvis_os.core.ports.config import ConfigurationPort
from jarvis_os.core.domain.exceptions import ConfigurationError

DEFAULT_CONFIG: Dict[str, Any] = {
    "llm.model": "qwen2.5:1.5b",
    "llm.url": "http://localhost:11434",
    "db.path": "jarvis.db",
    "log.level": "INFO",
    "log.file_path": "jarvis.log",
    "security.sandbox_enabled": True,
    "security.allowed_roots": [],
    "voice.stt_engine": "vosk",
    "voice.tts_engine": "sapi5",
    "voice.wake_word": "jarvis",
}

ENV_MAP: Dict[str, str] = {
    "JARVIS_LLM_MODEL": "llm.model",
    "JARVIS_LLM_URL": "llm.url",
    "JARVIS_DB_PATH": "db.path",
    "JARVIS_LOG_LEVEL": "log.level",
    "JARVIS_LOG_FILE_PATH": "log.file_path",
    "JARVIS_SECURITY_SANDBOX_ENABLED": "security.sandbox_enabled",
    "JARVIS_SECURITY_ALLOWED_ROOTS": "security.allowed_roots",
    "JARVIS_VOICE_STT_ENGINE": "voice.stt_engine",
    "JARVIS_VOICE_TTS_ENGINE": "voice.tts_engine",
    "JARVIS_VOICE_WAKE_WORD": "voice.wake_word",
}

class EnvSettings(ConfigurationPort):
    """Configuration provider that loads values from a .env file and OS environment variables."""

    def __init__(self, env_file_path: Optional[str] = None):
        self._env_file_path = Path(env_file_path) if env_file_path else Path(".env")
        self._config: Dict[str, Any] = DEFAULT_CONFIG.copy()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_boolean(self, key: str, default: bool = False) -> bool:
        val = self.get(key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes", "on", "t", "y")
        return bool(val)

    def get_int(self, key: str, default: int = 0) -> int:
        val = self.get(key, default)
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_string(self, key: str, default: str = "") -> str:
        val = self.get(key, default)
        if val is None:
            return default
        return str(val)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value

    def load(self) -> None:
        """Loads configuration from `.env` file followed by OS environment overrides."""
        # 1. Start with defaults
        self._config = DEFAULT_CONFIG.copy()

        # 2. Parse dotenv file if it exists
        if self._env_file_path.is_file():
            try:
                with open(self._env_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        # Ignore comments and empty lines
                        if not line or line.startswith("#"):
                            continue
                        # Split by first '='
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip()
                            # Strip outer quotes if any
                            if len(v) >= 2 and ((v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'"))):
                                v = v[1:-1]
                            
                            # Store in configuration
                            self._apply_parsed_key(k, v)
            except Exception as e:
                raise ConfigurationError(f"Failed to read config file {self._env_file_path}: {e}") from e

        # 3. Apply active system environment overrides
        for env_k, config_k in ENV_MAP.items():
            if env_k in os.environ:
                self._apply_parsed_key(env_k, os.environ[env_k])

    def _apply_parsed_key(self, k: str, v: str) -> None:
        """Helper to map and cast raw key-value string pairs into internal configuration."""
        # Map environment variable keys (e.g. JARVIS_LLM_MODEL) to dot notation (e.g. llm.model)
        mapped_key = ENV_MAP.get(k, k)

        # Handle lists/comma-separated strings (like security.allowed_roots)
        if mapped_key == "security.allowed_roots":
            if v:
                self._config[mapped_key] = [path.strip() for path in v.split(",") if path.strip()]
            else:
                self._config[mapped_key] = []
        else:
            self._config[mapped_key] = v

    def validate(self) -> bool:
        """Validates that loaded configuration settings satisfy system constraints."""
        # Check llm.url format
        url = self.get_string("llm.url")
        if not url:
            raise ConfigurationError("Configuration 'llm.url' is required and cannot be empty.")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ConfigurationError(f"Configuration 'llm.url' must start with http:// or https://, got: {url}")

        # Check log.level constraints
        level = self.get_string("log.level").upper()
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed_levels:
            raise ConfigurationError(f"Configuration 'log.level' must be one of {allowed_levels}, got: {level}")

        # Check db.path
        db_path = self.get_string("db.path")
        if not db_path:
            raise ConfigurationError("Configuration 'db.path' is required.")

        # Check llm.model
        model = self.get_string("llm.model")
        if not model:
            raise ConfigurationError("Configuration 'llm.model' is required.")

        return True

    def get_all(self) -> Dict[str, Any]:
        return self._config.copy()

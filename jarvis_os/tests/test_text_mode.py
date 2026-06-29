import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from jarvis_os.core.conversation.models import ConversationMessage, ConversationResponse


class TestTextMode(unittest.TestCase):
    def test_text_conversation_loop_invokes_conversation_manager(self):
        manager = Mock()
        manager.create_session.return_value = SimpleNamespace(session_id="session-1")
        manager.handle_request.return_value = ConversationResponse(
            session_id="session-1",
            message=ConversationMessage(role="assistant", content="Hello! How can I help you today?"),
        )
        inputs = iter(["Hello", "exit"])
        outputs = []

        main.run_text_mode(
            manager,
            input_func=lambda prompt="": next(inputs),
            output_func=outputs.append,
            clear_func=Mock(),
        )

        manager.create_session.assert_called_once()
        manager.handle_request.assert_called_once()
        request = manager.handle_request.call_args.args[0]
        self.assertEqual(request.session_id, "session-1")
        self.assertEqual(request.message.role, "user")
        self.assertEqual(request.message.content, "Hello")
        self.assertTrue(any("BHUvi > Hello! How can I help you today?" in item for item in outputs))

    def test_exit_commands_return_to_menu_without_conversation_request(self):
        for command in ("exit", "quit", "back"):
            with self.subTest(command=command):
                manager = Mock()
                manager.create_session.return_value = SimpleNamespace(session_id="session-1")
                outputs = []

                main.run_text_mode(
                    manager,
                    input_func=lambda prompt="", command=command: command,
                    output_func=outputs.append,
                    clear_func=Mock(),
                )

                manager.handle_request.assert_not_called()
                self.assertIn("Returning to main menu...", outputs)

    def test_clear_command_clears_terminal_without_erasing_conversation(self):
        manager = Mock()
        manager.create_session.return_value = SimpleNamespace(session_id="session-1")
        clear_func = Mock()
        inputs = iter(["clear", "back"])

        main.run_text_mode(
            manager,
            input_func=lambda prompt="": next(inputs),
            output_func=Mock(),
            clear_func=clear_func,
        )

        clear_func.assert_called_once()
        manager.handle_request.assert_not_called()

    def test_text_mode_with_bootstrap_conversation_manager_uses_typed_requests(self):
        manager = main.build_conversation_manager(main.MockLLMProvider())
        inputs = iter(["Hello", "back"])
        outputs = []

        main.run_text_mode(
            manager,
            input_func=lambda prompt="": next(inputs),
            output_func=outputs.append,
            clear_func=Mock(),
        )

        self.assertTrue(any("BHUvi >" in item for item in outputs))
        self.assertFalse(any("request_text" in item for item in outputs))

    def test_menu_selection_routes_to_text_mode(self):
        provider = object()
        manager = Mock()
        inputs = iter(["2", "3"])

        with patch("sys.argv", ["main.py"]), \
            patch("builtins.input", lambda prompt="": next(inputs)), \
            patch.object(main, "resolve_llm_provider", return_value=provider) as resolve_provider, \
            patch.object(main, "build_conversation_manager", return_value=manager) as build_manager, \
            patch.object(main, "run_text_mode") as run_text_mode:
            main.main()

        resolve_provider.assert_called_once()
        build_manager.assert_called_once_with(provider)
        run_text_mode.assert_called_once_with(manager)

    def test_ollama_failure_returns_to_menu_gracefully(self):
        inputs = iter(["2", "3"])
        output = io.StringIO()

        with patch("sys.argv", ["main.py"]), \
            patch("builtins.input", lambda prompt="": next(inputs)), \
            patch.object(main, "check_ollama_status", return_value=False), \
            patch.object(main, "build_conversation_manager") as build_manager, \
            redirect_stdout(output):
            main.main()

        self.assertIn("[ERROR] Ollama server is unavailable.", output.getvalue())
        build_manager.assert_not_called()


if __name__ == "__main__":
    unittest.main()

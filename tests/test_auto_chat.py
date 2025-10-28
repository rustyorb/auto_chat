import unittest
from unittest.mock import MagicMock, patch, call
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock tkinter before importing auto_chat
sys.modules['tkinter'] = MagicMock()
sys.modules['tkinter.ttk'] = MagicMock()
mock_ttkbootstrap = MagicMock()
mock_ttkbootstrap.Window = type('MockWindow', (object,), {})
mock_constants = MagicMock()
mock_constants.NORMAL = 'normal'
mock_constants.DISABLED = 'disabled'
sys.modules['ttkbootstrap'] = mock_ttkbootstrap
sys.modules['ttkbootstrap.constants'] = mock_constants

from auto_chat import ChatApp

class TestChatAppBugFixes(unittest.TestCase):

    def setUp(self):
        """Set up a mock ChatApp instance before each test."""
        # Create an instance without calling __init__ to avoid GUI setup
        self.app = ChatApp.__new__(ChatApp)

        # Manually mock the attributes needed for the tests
        self.app.persona1_var = MagicMock()
        self.app.persona2_var = MagicMock()
        self.app.chat_manager = MagicMock()
        self.app.update_persona_details = MagicMock()
        self.app.persona1_combo = MagicMock()
        self.app.persona2_combo = MagicMock()
        self.app.api_key_var = MagicMock()
        self.app.app_config = {}
        self.app.chat_manager.api_clients = {
            "openrouter": MagicMock()
        }
        self.app.pause_button = MagicMock()
        self.app.narrator_button = MagicMock()
        self.app.update_status = MagicMock()
        self.app.after_idle = MagicMock()
        self.app.winfo_exists = MagicMock(return_value=True)

    def test_update_persona_combos_clears_stale_selection(self):
        """
        Bug 1 Fix: Test that update_persona_combos clears a stale persona selection.
        """
        # Arrange
        self.app.persona1_var.get.return_value = "Deleted Persona"
        self.app.persona2_var.get.return_value = "Existing Persona"
        self.app.chat_manager.personas = [MagicMock(name="Existing Persona")]

        # Act
        self.app.update_persona_combos()

        # Assert
        self.app.persona1_var.set.assert_called_with("")

    def test_save_current_api_key_clears_client_key(self):
        """
        Bug 2 Fix: Test that save_current_api_key clears the API key on the client.
        """
        # Arrange
        self.app.current_api_key_provider = "openrouter"
        self.app.api_key_var.get.return_value = ""
        self.app.app_config["openrouter_api_key"] = "some-old-key"

        # Act
        self.app.save_current_api_key()

        # Assert
        client = self.app.chat_manager.api_clients["openrouter"]
        self.assertEqual(client.api_key, "")
        client.update_headers.assert_called_once()

    def test_toggle_pause_avoids_race_condition(self):
        """
        Bug 3 Fix: Test that toggle_pause uses the correct state in the UI update.
        """
        # Arrange
        self.app.chat_manager.is_running = True
        self.app.chat_manager.is_paused = False

        # Act
        self.app.toggle_pause()

        # Assert
        self.app.after_idle.assert_called_once()

        # Capture the function passed to after_idle
        callback = self.app.after_idle.call_args[0][0]

        # Create a mock to represent the `update_ui` inner function
        mock_update_ui = MagicMock()

        # Since `update_ui` is a closure, we can't patch it directly.
        # Instead, we execute the callback and verify the calls to the UI elements.
        callback()

        self.app.pause_button.config.assert_called_with(text="Resume", bootstyle="success")
        self.app.narrator_button.config.assert_called_with(state='normal')
        self.app.update_status.assert_called_with("Conversation paused")

if __name__ == '__main__':
    unittest.main()

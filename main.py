"""
main.py

Entry point for the Groq Chat desktop application.

Run with:
    python main.py

Requires a .env file (copy .env.example to .env) with at least XAI_API_KEY
set, though the API key can also be entered later via the in-app Settings
dialog.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Groq Chat")
    app.setOrganizationName("GroqChatApp")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

"""
ui/main_window.py

The top-level QMainWindow. Owns:
    * The Sidebar (thread list + language switcher).
    * The ChatWidget (message viewport + input bar).
    * The Settings dialog (API key, base URL, model, theme).
    * Chat thread state (in-memory + persisted to disk via config.save_history).
    * The GroqStreamWorker lifecycle for sending/streaming/cancelling messages.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from api.file_handler import build_message_content, build_prompt_with_attachments
from api.groq_client import GroqStreamWorker
from api.openrouter_client import OpenRouterImageWorker
from config import (
    AVAILABLE_MODELS,
    IMAGES_DIR,
    Translator,
    load_history,
    load_settings,
    save_history,
    save_settings,
)
from ui.chat_widget import ChatWidget
from ui.sidebar import Sidebar
from ui.styles import get_stylesheet


class SettingsDialog(QDialog):
    """Modal dialog for editing the API key, base URL, model, and theme."""

    def __init__(self, translator: Translator, settings: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.translator = translator
        self.setWindowTitle(translator.t("settings"))
        self.setMinimumWidth(420)
        self._settings = dict(settings)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.api_key_input = QLineEdit(self._settings.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("gsk_...")
        form.addRow(self.translator.t("api_key"), self.api_key_input)

        self.openrouter_key_input = QLineEdit(self._settings.get("openrouter_api_key", ""))
        self.openrouter_key_input.setEchoMode(QLineEdit.Password)
        self.openrouter_key_input.setPlaceholderText("sk-or-v1-...")
        form.addRow("OpenRouter API Key", self.openrouter_key_input)

        self.base_url_input = QLineEdit(self._settings.get("base_url", ""))
        form.addRow("Base URL", self.base_url_input)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(AVAILABLE_MODELS)
        current_model = self._settings.get("model", AVAILABLE_MODELS[0])
        if current_model not in AVAILABLE_MODELS:
            self.model_combo.addItem(current_model)
        self.model_combo.setCurrentText(current_model)
        form.addRow(self.translator.t("model"), self.model_combo)

        self.openrouter_model_input = QLineEdit(
            self._settings.get("openrouter_model", "openai/gpt-4o-mini")
        )
        form.addRow("OpenRouter model", self.openrouter_model_input)

        self.fallback_provider_combo = QComboBox()
        self.fallback_provider_combo.addItem("OpenRouter", userData="openrouter")
        self.fallback_provider_combo.addItem("Groq", userData="groq")
        fallback_index = self.fallback_provider_combo.findData(
            self._settings.get("fallback_provider", "openrouter")
        )
        if fallback_index >= 0:
            self.fallback_provider_combo.setCurrentIndex(fallback_index)
        form.addRow("Fallback provider", self.fallback_provider_combo)

        self.fallback_model_input = QLineEdit(
            self._settings.get("fallback_model", "openai/gpt-4o-mini")
        )
        form.addRow("Fallback model", self.fallback_model_input)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self.translator.t("dark_theme"), userData="dark")
        self.theme_combo.addItem(self.translator.t("light_theme"), userData="light")
        theme_index = self.theme_combo.findData(self._settings.get("theme", "dark"))
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
        form.addRow(self.translator.t("theme"), self.theme_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox()
        save_btn = buttons.addButton(self.translator.t("save"), QDialogButtonBox.AcceptRole)
        cancel_btn = buttons.addButton(self.translator.t("cancel"), QDialogButtonBox.RejectRole)
        save_btn.setObjectName("PrimaryButton")
        cancel_btn.setObjectName("SecondaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_settings(self) -> dict:
        updated = dict(self._settings)
        updated["api_key"] = self.api_key_input.text().strip()
        updated["openrouter_api_key"] = self.openrouter_key_input.text().strip()
        updated["base_url"] = self.base_url_input.text().strip() or "https://api.groq.com/openai/v1"
        updated["model"] = self.model_combo.currentText().strip() or AVAILABLE_MODELS[0]
        updated["openrouter_model"] = self.openrouter_model_input.text().strip()
        updated["fallback_provider"] = self.fallback_provider_combo.currentData()
        updated["fallback_model"] = self.fallback_model_input.text().strip()
        updated["theme"] = self.theme_combo.currentData()
        return updated


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.translator = Translator(self.settings.get("language", "en"))

        self.threads: List[Dict] = load_history()
        if not self.threads:
            self.threads = [self._make_new_thread()]
        self.active_thread_id: str = self.threads[0]["id"]

        self.worker: Optional[GroqStreamWorker] = None
        self.image_worker: Optional[OpenRouterImageWorker] = None

        self.setWindowTitle(self.translator.t("app_title"))
        self.resize(self.settings.get("window_width", 1200), self.settings.get("window_height", 800))

        self._build_ui()
        self._apply_theme()
        self._apply_layout_direction()
        self._refresh_sidebar()
        self._load_active_thread_into_view()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar(self.translator, self.translator.language)
        self.sidebar.new_chat_requested.connect(self._on_new_chat)
        self.sidebar.thread_selected.connect(self._on_thread_selected)
        self.sidebar.thread_deleted.connect(self._on_thread_deleted)
        self.sidebar.thread_renamed.connect(self._on_thread_renamed)
        self.sidebar.language_changed.connect(self._on_language_changed)
        self.sidebar.settings_requested.connect(self._on_settings_requested)
        root_layout.addWidget(self.sidebar)

        self.chat_widget = ChatWidget(self.translator)
        self.chat_widget.message_submitted.connect(self._on_message_submitted)
        self.chat_widget.image_generation_requested.connect(self._on_image_generation_requested)
        self.chat_widget.message_edited.connect(self._on_message_edited)
        self.chat_widget.regenerate_requested.connect(self._on_regenerate)
        root_layout.addWidget(self.chat_widget, 1)

        self.setCentralWidget(central)

    def _apply_theme(self) -> None:
        app = QGuiApplication.instance()
        app.setStyleSheet(get_stylesheet(self.settings.get("theme", "dark")))

    def _apply_layout_direction(self) -> None:
        app = QGuiApplication.instance()
        app.setLayoutDirection(Qt.RightToLeft if self.translator.is_rtl() else Qt.LeftToRight)

    # ------------------------------------------------------------------ #
    # Thread helpers
    # ------------------------------------------------------------------ #
    def _make_new_thread(self) -> Dict:
        return {
            "id": str(uuid.uuid4()),
            "title": self.translator.t("untitled_chat") if hasattr(self, "translator") else "New conversation",
            "messages": [],
            "created_at": datetime.utcnow().isoformat(),
        }

    def _get_thread(self, thread_id: str) -> Optional[Dict]:
        for thread in self.threads:
            if thread["id"] == thread_id:
                return thread
        return None

    def _refresh_sidebar(self) -> None:
        display = [{"id": t["id"], "title": t["title"]} for t in self.threads]
        self.sidebar.set_threads(display, active_id=self.active_thread_id)

    def _persist(self) -> None:
        save_history(self.threads)
        save_settings(self.settings)

    def _load_active_thread_into_view(self) -> None:
        thread = self._get_thread(self.active_thread_id)
        self.chat_widget.clear_messages()
        if not thread:
            return
        if thread["messages"]:
            self.chat_widget.welcome_widget.setVisible(False)
        for message in thread["messages"]:
            self.chat_widget.add_message(message["role"], message["content"])

    # ------------------------------------------------------------------ #
    # Sidebar event handlers
    # ------------------------------------------------------------------ #
    def _on_new_chat(self) -> None:
        thread = self._make_new_thread()
        self.threads.insert(0, thread)
        self.active_thread_id = thread["id"]
        self._refresh_sidebar()
        self._load_active_thread_into_view()
        self._persist()

    def _on_thread_selected(self, thread_id: str) -> None:
        if thread_id == self.active_thread_id:
            return
        self._stop_generation_if_running()
        self.active_thread_id = thread_id
        self._load_active_thread_into_view()

    def _on_thread_deleted(self, thread_id: str) -> None:
        self.threads = [t for t in self.threads if t["id"] != thread_id]
        if not self.threads:
            self.threads = [self._make_new_thread()]
        if thread_id == self.active_thread_id:
            self.active_thread_id = self.threads[0]["id"]
            self._load_active_thread_into_view()
        self._refresh_sidebar()
        self._persist()

    def _on_thread_renamed(self, thread_id: str, new_title: str) -> None:
        thread = self._get_thread(thread_id)
        if thread:
            thread["title"] = new_title
            self._persist()

    def _on_language_changed(self, code: str) -> None:
        self.translator.set_language(code)
        self.settings["language"] = code
        self._apply_layout_direction()
        self.setWindowTitle(self.translator.t("app_title"))
        self.sidebar.retranslate()
        self.chat_widget.retranslate()
        self._refresh_sidebar()
        self._persist()

    def _on_settings_requested(self) -> None:
        dialog = SettingsDialog(self.translator, self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            updated = dialog.result_settings()
            theme_changed = updated.get("theme") != self.settings.get("theme")
            self.settings.update(updated)
            if theme_changed:
                self._apply_theme()
            self._persist()

    # ------------------------------------------------------------------ #
    # Chat / Groq API integration
    # ------------------------------------------------------------------ #
    def _on_image_generation_requested(self, prompt: str) -> None:
        api_key = self.settings.get("openrouter_api_key", "").strip()
        if not api_key:
            QMessageBox.warning(
                self,
                "OpenRouter API key missing",
                "Add an OpenRouter API key in Settings to generate images.",
            )
            self._on_settings_requested()
            return
        if self.image_worker is not None and self.image_worker.isRunning():
            return

        thread = self._get_thread(self.active_thread_id)
        if thread is None:
            return
        user_content = f"Generate image: {prompt}"
        thread["messages"].append({"role": "user", "content": user_content})
        self.chat_widget.add_message("user", user_content)
        self.chat_widget.begin_assistant_message()
        self._persist()

        self.image_worker = OpenRouterImageWorker(
            api_key=api_key,
            model=self.settings.get(
                "openrouter_image_model", "inclusionai/ming-image-0.1-design-layer"
            ),
            prompt=prompt,
            save_dir=str(IMAGES_DIR),
        )
        self.image_worker.image_ready.connect(self._on_image_ready)
        self.image_worker.error.connect(self._on_image_error)
        self.image_worker.finished.connect(self._clear_image_worker)
        self.image_worker.start()

    def _on_image_ready(self, path: str) -> None:
        image_url = QUrl.fromLocalFile(str(Path(path).resolve())).toString()
        content = f"![Generated image]({image_url})\n\n[Open image]({image_url})"
        self.chat_widget.end_assistant_message(content)
        thread = self._get_thread(self.active_thread_id)
        if thread is not None:
            thread["messages"].append({"role": "assistant", "content": content})
            self._persist()

    def _on_image_error(self, message: str) -> None:
        self.chat_widget.show_error_message(message)

    def _clear_image_worker(self) -> None:
        self.image_worker = None

    def _on_message_submitted(self, text: str, attachments: list) -> None:
        if not self._check_api_key():
            return

        thread = self._get_thread(self.active_thread_id)
        if thread is None:
            return

        full_prompt = build_prompt_with_attachments(text, attachments)
        request_content = build_message_content(text, attachments)
        thread["messages"].append({"role": "user", "content": text or full_prompt})

        if thread["title"] in (self.translator.t("untitled_chat"), "New conversation") and text:
            thread["title"] = text[:40] + ("..." if len(text) > 40 else "")
            self._refresh_sidebar()

        self._persist()
        has_image = any(attachment.is_valid and attachment.is_image for attachment in attachments)
        self._start_worker(
            thread,
            override_last_content=request_content,
            vision_request=has_image,
        )

    def _on_message_edited(self, index: int, new_text: str) -> None:
        """A user edited an earlier message: drop everything after it and
        regenerate the assistant's reply from that point."""
        if not self._check_api_key():
            return

        self._stop_generation_if_running()
        thread = self._get_thread(self.active_thread_id)
        if thread is None:
            return

        thread["messages"] = thread["messages"][:index]
        thread["messages"].append({"role": "user", "content": new_text})
        self._persist()
        self._start_worker(thread, override_last_content=new_text)

    def _on_regenerate(self, index: int) -> None:
        """Re-run the model for the assistant message at `index`, discarding
        it (and anything after it) first."""
        if index <= 0 or not self._check_api_key():
            return

        self._stop_generation_if_running()
        thread = self._get_thread(self.active_thread_id)
        if thread is None:
            return

        thread["messages"] = thread["messages"][:index]
        self._persist()
        self._start_worker(thread, override_last_content=None)

    def _check_api_key(self) -> bool:
        api_key = self.settings.get("api_key", "").strip()
        openrouter_key = self.settings.get("openrouter_api_key", "").strip()
        if not api_key and not openrouter_key:
            QMessageBox.warning(
                self,
                self.translator.t("no_api_key_title"),
                self.translator.t("no_api_key_body"),
            )
            self._on_settings_requested()
            return False
        return True

    def _start_worker(
        self,
        thread: Dict,
        override_last_content: Optional[Any],
        vision_request: bool = False,
    ) -> None:
        """Builds the API message list from `thread` and kicks off a
        streaming completion. If `override_last_content` is given, it
        replaces the stored content of the final (user) message — used to
        send file-attachment text that shouldn't be persisted verbatim.
        """
        messages = thread["messages"]
        api_messages = [{"role": "system", "content": self.translator.t("system_prompt_label")}]
        last_index = len(messages) - 1
        for i, message in enumerate(messages):
            content = message["content"]
            if override_last_content is not None and i == last_index and message["role"] == "user":
                content = override_last_content
            api_messages.append({"role": message["role"], "content": content})

        fallback_provider = self.settings.get("fallback_provider", "openrouter")
        fallback_base_url = "https://openrouter.ai/api/v1" if fallback_provider == "openrouter" else self.settings.get("base_url", "https://api.groq.com/openai/v1")
        fallback_key = self.settings.get("openrouter_api_key", "") if fallback_provider == "openrouter" else self.settings.get("api_key", "")
        fallback_model = self.settings.get("fallback_model", "openai/gpt-4o-mini")
        if fallback_provider == "openrouter":
            fallback_model = self.settings.get("fallback_model") or self.settings.get("openrouter_model", "openai/gpt-4o-mini")

        api_key = self.settings.get("api_key", "").strip()
        base_url = self.settings.get("base_url", "https://api.groq.com/openai/v1")
        model = self.settings.get("model", "llama-3.3-70b-versatile")
        primary_label = "Groq"
        if vision_request:
            openrouter_key = self.settings.get("openrouter_api_key", "").strip()
            if not openrouter_key:
                self.chat_widget.show_error_message(
                    "Image questions require a valid OpenRouter API key. "
                    "Add it in Settings under OpenRouter API Key."
                )
                return
            api_key = openrouter_key
            base_url = "https://openrouter.ai/api/v1"
            model = "openai/gpt-4o-mini"
            fallback_key = ""
            fallback_model = ""
            primary_label = "OpenRouter"

        self.chat_widget.begin_assistant_message()
        self.worker = GroqStreamWorker(
            api_key=api_key,
            base_url=base_url,
            model=model,
            messages=api_messages,
            fallback_api_key=fallback_key.strip(),
            fallback_base_url=fallback_base_url,
            fallback_model=fallback_model,
            fallback_label=fallback_provider,
            primary_label=primary_label,
        )
        self.worker.chunk_received.connect(self.chat_widget.append_assistant_delta)
        self.worker.finished.connect(self._on_generation_finished)
        self.worker.error.connect(self._on_generation_error)
        self.worker.start()

    def _on_generation_finished(self, full_text: str) -> None:
        self.chat_widget.end_assistant_message(full_text)
        thread = self._get_thread(self.active_thread_id)
        if thread is not None:
            thread["messages"].append({"role": "assistant", "content": full_text})
            self._persist()
        self.worker = None

    def _on_generation_error(self, message: str) -> None:
        self.chat_widget.show_error_message(message)
        self.worker = None

    def _stop_generation_if_running(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
            self.worker = None
        if self.image_worker is not None and self.image_worker.isRunning():
            self.image_worker.wait(2000)
            self.image_worker = None

    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._stop_generation_if_running()
        self.settings["window_width"] = self.width()
        self.settings["window_height"] = self.height()
        self._persist()
        super().closeEvent(event)

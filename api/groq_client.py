"""
api/groq_client.py

Wraps Groq's OpenAI-compatible API (https://api.groq.com/openai/v1) and exposes
it to the PySide6 GUI as a QThread worker, so streaming responses arrive via Qt
signals and never block the UI thread.

Usage:
    worker = GroqStreamWorker(api_key, base_url, model, messages)
    worker.chunk_received.connect(...)
    worker.finished.connect(...)
    worker.error.connect(...)
    worker.start()

    # To cancel a running generation:
    worker.stop()
"""

from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import QThread, Signal

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - surfaced via error signal at runtime
    OpenAI = None


class GroqClient:
    """Thin synchronous wrapper around the OpenAI-compatible Groq client."""

    def __init__(self, api_key: str, base_url: str) -> None:
        if OpenAI is None:
            raise RuntimeError(
                "The 'openai' package is not installed. Run: pip install openai"
            )
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def stream_chat(self, model: str, messages: List[Dict]):
        """Yields text deltas from a streaming chat completion."""
        stream = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content

    def list_models(self) -> List[str]:
        """Best-effort model listing; falls back to an empty list on failure."""
        try:
            response = self._client.models.list()
            return [m.id for m in response.data]
        except Exception:
            return []


class GroqStreamWorker(QThread):
    """
    Runs a streaming chat completion on a background thread.

    Signals:
        chunk_received(str): emitted for every text delta received from the API.
        finished(str): emitted once with the full accumulated response text.
        error(str): emitted if something goes wrong, with a human-readable message.
    """

    chunk_received = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        messages: List[Dict],
        fallback_api_key: str = "",
        fallback_base_url: str = "",
        fallback_model: str = "",
        fallback_label: str = "fallback provider",
        parent=None,
        primary_label: str = "Groq",
    ) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._messages = messages
        self._fallback = (fallback_api_key, fallback_base_url, fallback_model, fallback_label)
        self._primary_label = primary_label
        self._stop_requested = False

    def stop(self) -> None:
        """Request early termination. The thread checks this between chunks."""
        self._stop_requested = True

    def run(self) -> None:  # noqa: D401 - Qt override
        try:
            accumulated = self._stream_from(self._api_key, self._base_url, self._model)
        except Exception as primary_exc:  # noqa: BLE001
            fallback_key, fallback_url, fallback_model, fallback_label = self._fallback
            if (
                not fallback_key
                or not fallback_model
                or (self._api_key and not _should_use_fallback(primary_exc))
            ):
                self.error.emit(_friendly_error(primary_exc, self._primary_label))
                return
            try:
                accumulated = self._stream_from(fallback_key, fallback_url, fallback_model)
            except Exception as fallback_exc:  # noqa: BLE001
                self.error.emit(
                    f"Primary model failed: {_friendly_error(primary_exc)} "
                    f"Fallback ({fallback_label}) also failed: "
                    f"{_friendly_error(fallback_exc, fallback_label)}"
                )
                return
        self.finished.emit(accumulated)

    def _stream_from(self, api_key: str, base_url: str, model: str) -> str:
        accumulated = ""
        client = GroqClient(api_key, base_url)
        for delta in client.stream_chat(model, self._messages):
            if self._stop_requested:
                break
            accumulated += delta
            self.chunk_received.emit(delta)
        return accumulated


def _should_use_fallback(exc: Exception) -> bool:
    """Recognize Groq quota and rate-limit failures that should fail over."""
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "429",
            "rate limit",
            "ratelimit",
            "quota",
            "too many requests",
            "tokens per minute",
            "daily limit",
            "limit reached",
            "image_url",
            "image input",
            "image content",
            "vision",
            "multimodal",
            "llama-4-scout",
        )
    )


def _friendly_error(exc: Exception, provider: str = "Groq") -> str:
    """Translate common exception shapes into a readable message."""
    message = str(exc)
    lowered = message.lower()
    provider_name = {"groq": "Groq", "openrouter": "OpenRouter"}.get(
        provider.lower(), provider
    )
    if "unauthorized" in lowered or "401" in lowered or "invalid api key" in lowered:
        return f"Authentication failed. Please check your {provider_name} API key in Settings."
    if "connection" in lowered or "timed out" in lowered or "timeout" in lowered:
        return "Could not connect to the Groq API. Please check your internet connection."
    if "rate limit" in lowered or "429" in lowered:
        return "Rate limit exceeded. Please wait a moment and try again."
    if "model" in lowered and ("not found" in lowered or "404" in lowered or "decommissioned" in lowered):
        return "The selected model is not available. Please choose a different model in Settings."
    return f"An error occurred: {message}"

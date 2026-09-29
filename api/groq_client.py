"""
api/groq_client.py

Wraps Groq's OpenAI-compatible API (https://api.groq.com/openai/v1) and exposes
it to the PySide6 GUI as a QThread worker, so streaming responses arrive via Qt
signals and never block the UI thread.

Usage:
    worker = GroqStreamWorker(api_key, base_url, model, messages)
    worker.chunk_received.connect(...)
    worker.response_finished.connect(...)
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

MAX_CONTEXT_CHARS = 16000


def _content_char_count(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(part.get("text", "")) for part in content if isinstance(part, dict))
    return 0


def _trim_messages(messages: List[Dict], max_chars: int = MAX_CONTEXT_CHARS) -> List[Dict]:
    """Keep the latest prompt and as much recent history as fits a safe budget."""
    if len(messages) <= 1:
        return messages

    system_message = messages[0] if messages[0].get("role") == "system" else None
    latest_message = dict(messages[-1])
    system_size = _content_char_count(system_message.get("content", "")) if system_message else 0
    latest_content = latest_message.get("content", "")
    latest_size = _content_char_count(latest_content)
    available = max(0, max_chars - system_size)

    if isinstance(latest_content, str) and latest_size > available:
        marker = "\n[Earlier content omitted to fit the model context limit.]"
        latest_message["content"] = latest_content[:max(0, available - len(marker))] + marker
        latest_size = _content_char_count(latest_message["content"])

    remaining = max(0, available - latest_size)
    recent_messages = []
    earlier_messages = messages[1:-1] if system_message else messages[:-1]
    for message in reversed(earlier_messages):
        message_size = _content_char_count(message.get("content", ""))
        if message_size > remaining:
            break
        recent_messages.append(message)
        remaining -= message_size

    trimmed = ([system_message] if system_message else [])
    trimmed.extend(reversed(recent_messages))
    trimmed.append(latest_message)
    return trimmed


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
        response_finished(str): emitted once with the full accumulated response text.
        error(str): emitted if something goes wrong, with a human-readable message.
    """

    chunk_received = Signal(str)
    response_finished = Signal(str)
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
        self._messages = _trim_messages(messages)
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
            if _is_context_size_error(primary_exc):
                for budget in (8000, 4000, 2000):
                    self._messages = _trim_messages(self._messages, budget)
                    try:
                        accumulated = self._stream_from(
                            self._api_key, self._base_url, self._model
                        )
                        self.response_finished.emit(accumulated)
                        return
                    except Exception as retry_exc:  # noqa: BLE001
                        primary_exc = retry_exc

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
        self.response_finished.emit(accumulated)

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
            "401",
            "unauthorized",
            "invalid api key",
            "429",
            "413",
            "request too large",
            "rate limit",
            "ratelimit",
            "quota",
            "too many requests",
            "tokens per minute",
            "daily limit",
            "limit reached",
            "model not found",
            "decommissioned",
            "invalid model",
            "model does not exist",
            "404",
            "image_url",
            "image input",
            "image content",
            "vision",
            "multimodal",
            "llama-4-scout",
        )
    )


def _is_context_size_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("tokens per minute", "request too large", "413")
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
    if "402" in lowered or "insufficient_quota" in lowered or "insufficient credits" in lowered:
        return f"Your {provider_name} account has insufficient credits or has reached its spending limit."
    if "403" in lowered or "permission" in lowered or "forbidden" in lowered:
        return f"Access denied by {provider_name}. Check the API key permissions and account limits."
    if "connection" in lowered or "timed out" in lowered or "timeout" in lowered:
        return f"Could not connect to {provider_name}. Please check your internet connection."
    if "rate limit" in lowered or "429" in lowered:
        return f"{provider_name} rate limit exceeded. Please wait a moment and try again."
    if "model" in lowered and ("not found" in lowered or "404" in lowered or "decommissioned" in lowered):
        return "The selected model is not available. Please choose a different model in Settings."
    return f"An error occurred: {message}"


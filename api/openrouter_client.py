"""
api/openrouter_client.py

Wraps OpenRouter's Image Generation API and exposes it to the PySide6 GUI as
a QThread worker, so image generation never blocks the UI thread.

Usage:
    worker = OpenRouterImageWorker(api_key, model, prompt, save_dir)
    worker.image_ready.connect(...)   # receives the saved file path
    worker.error.connect(...)
    worker.start()
"""

from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path
from typing import Optional

import requests
from PySide6.QtCore import QThread, Signal

OPENROUTER_IMAGE_ENDPOINT = "https://openrouter.ai/api/v1/images"
DEFAULT_IMAGE_MODEL = "inclusionai/ming-image-0.1-design-layer"


class OpenRouterImageClient:
    """Thin synchronous wrapper around OpenRouter's Image API."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise RuntimeError("OpenRouter API key is missing. Set it in Settings.")
        self._api_key = api_key

    def generate_image(
        self,
        model: str,
        prompt: str,
        output_format: str = "png",
        n: int = 1,
        input_references: Optional[list] = None,
        timeout: int = 120,
    ) -> dict:
        """
        Calls the OpenRouter Image API and returns the parsed JSON response.
        Raises requests.HTTPError on non-2xx responses.
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "output_format": output_format,
            "n": n,
        }
        if input_references:
            payload["input_references"] = input_references

        response = requests.post(
            OPENROUTER_IMAGE_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        if response.status_code != 200:
            # Surface OpenRouter's own error message when available.
            try:
                err = response.json().get("error", {}).get("message", response.text)
            except Exception:
                err = response.text
            raise requests.HTTPError(f"{response.status_code}: {err}", response=response)

        return response.json()


class OpenRouterImageWorker(QThread):
    """
    Runs image generation on a background thread.

    Signals:
        image_ready(str): emitted with the local file path of the saved image.
        error(str): emitted if something goes wrong, with a human-readable message.
    """

    image_ready = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        api_key: str,
        model: str,
        prompt: str,
        save_dir: str,
        output_format: str = "png",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._model = model
        self._prompt = prompt
        self._save_dir = Path(save_dir)
        self._output_format = output_format

    def run(self) -> None:  # noqa: D401 - Qt override
        try:
            client = OpenRouterImageClient(self._api_key)
            result = client.generate_image(
                model=self._model,
                prompt=self._prompt,
                output_format=self._output_format,
                n=1,
            )
            data = result.get("data", [])
            if not data:
                self.error.emit("No image was returned by the API.")
                return

            b64_json = data[0].get("b64_json")
            media_type = data[0].get("media_type", f"image/{self._output_format}")
            if not b64_json:
                self.error.emit("The API response did not include image data.")
                return

            ext = media_type.split("/")[-1] if "/" in media_type else self._output_format
            self._save_dir.mkdir(parents=True, exist_ok=True)
            filename = f"img_{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = self._save_dir / filename

            image_bytes = base64.b64decode(b64_json)
            with open(filepath, "wb") as fh:
                fh.write(image_bytes)

            self.image_ready.emit(str(filepath))

        except requests.HTTPError as exc:
            self.error.emit(_friendly_error(str(exc)))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(_friendly_error(str(exc)))


def _friendly_error(message: str) -> str:
    lowered = message.lower()
    if "401" in lowered or "invalid" in lowered and "key" in lowered:
        return "Authentication failed. Please check your OpenRouter API key in Settings."
    if "402" in lowered:
        return "Insufficient OpenRouter credits."
    if "403" in lowered:
        return "Access blocked — check your OpenRouter key permissions or spend limit."
    if "404" in lowered:
        return "This image model isn't available right now."
    if "413" in lowered:
        return "The request was too large."
    if "429" in lowered:
        return "Rate limit exceeded. Please wait a moment and try again."
    if "timed out" in lowered or "timeout" in lowered or "connection" in lowered:
        return "Could not connect to OpenRouter. Please check your internet connection."
    return f"Image generation failed: {message}"
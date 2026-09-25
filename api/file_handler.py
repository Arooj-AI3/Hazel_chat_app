"""
api/file_handler.py

Extracts plain-text content from uploaded attachments so it can be folded into
the chat prompt payload. Supports .txt, .py, .json, .csv, .md, .log (read as
plain text) and .pdf (extracted page-by-page via PyPDF2).
"""

from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass
from typing import Optional

from config import MAX_ATTACHMENT_SIZE_BYTES, SUPPORTED_ATTACHMENT_EXTENSIONS

try:
    from PyPDF2 import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


@dataclass
class AttachedFile:
    """Represents a file attached to a chat message."""

    path: str
    name: str
    extension: str
    size_bytes: int
    content: str = ""
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.error is None

    @property
    def is_image(self) -> bool:
        return self.extension in {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def is_supported_extension(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext.lower() in SUPPORTED_ATTACHMENT_EXTENSIONS


def extract_file(path: str) -> AttachedFile:
    """
    Reads a file from disk and returns an AttachedFile with its extracted text
    content, or with `error` set describing why extraction failed.
    """
    name = os.path.basename(path)
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    try:
        size_bytes = os.path.getsize(path)
    except OSError as exc:
        return AttachedFile(path=path, name=name, extension=ext, size_bytes=0, error=str(exc))

    if size_bytes > MAX_ATTACHMENT_SIZE_BYTES:
        return AttachedFile(
            path=path,
            name=name,
            extension=ext,
            size_bytes=size_bytes,
            error="file_too_large",
        )

    if ext not in SUPPORTED_ATTACHMENT_EXTENSIONS:
        return AttachedFile(
            path=path,
            name=name,
            extension=ext,
            size_bytes=size_bytes,
            error="unsupported_file",
        )

    try:
        if ext == ".pdf":
            content = _extract_pdf_text(path)
        elif ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            content = ""
        else:
            content = _extract_plain_text(path)
    except Exception as exc:  # noqa: BLE001
        return AttachedFile(
            path=path, name=name, extension=ext, size_bytes=size_bytes, error=str(exc)
        )

    return AttachedFile(
        path=path, name=name, extension=ext, size_bytes=size_bytes, content=content
    )


def _extract_plain_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _extract_pdf_text(path: str) -> str:
    if PdfReader is None:
        raise RuntimeError("PyPDF2 is not installed. Run: pip install PyPDF2")
    reader = PdfReader(path)
    pages_text = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages_text.append(f"--- Page {index + 1} ---\n{text.strip()}")
    return "\n\n".join(pages_text).strip()


def build_prompt_with_attachments(user_text: str, attachments: list) -> str:
    """
    Combines the user's typed message with the extracted content of any valid
    attachments into a single prompt string sent to the model.
    """
    if not attachments:
        return user_text

    sections = []
    if user_text.strip():
        sections.append(user_text.strip())

    for attachment in attachments:
        if not attachment.is_valid:
            continue
        sections.append(
            f"\n\n[Attached file: {attachment.name}]\n"
            f"```\n{attachment.content}\n```"
        )

    return "".join(sections) if sections else user_text


def build_message_content(user_text: str, attachments: list) -> object:
    """Build text or multimodal OpenAI-compatible message content."""
    image_parts = []
    text_prompt = build_prompt_with_attachments(
        user_text,
        [attachment for attachment in attachments if not attachment.is_image],
    )
    if text_prompt:
        image_parts.append({"type": "text", "text": text_prompt})

    for attachment in attachments:
        if not attachment.is_valid or not attachment.is_image:
            continue
        try:
            with open(attachment.path, "rb") as fh:
                encoded = base64.b64encode(fh.read()).decode("ascii")
            media_type = mimetypes.guess_type(attachment.path)[0] or "image/jpeg"
            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{encoded}"},
                }
            )
        except OSError:
            continue

    if any(part["type"] == "image_url" for part in image_parts):
        return image_parts
    return text_prompt or ""

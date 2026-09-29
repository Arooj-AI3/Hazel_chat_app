"""
config.py

Central configuration for the Groq Chat App.

Responsibilities:
    * Load environment variables from a .env file (API key, base URL, default model,
      default language, default theme).
    * Persist and load lightweight user settings (theme, language, model, window
      geometry) to a local JSON file in the user's home directory, so preferences
      survive across sessions.
    * Provide the multilingual translation dictionary (English, Urdu, Spanish,
      French) used throughout the UI, plus a small helper class to fetch strings
      by key with a safe fallback to English.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

APP_DIR = Path(__file__).resolve().parent
ENV_PATH = APP_DIR / ".env"

# Where we keep small persisted user preferences (not secrets).
SETTINGS_DIR = Path.home() / ".groq_chat_app"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
HISTORY_PATH = SETTINGS_DIR / "history.json"
IMAGES_DIR = SETTINGS_DIR / "generated_images"
# Load the .env file (if present) into os.environ before anything reads it.
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    # Still attempt a default load in case the app is run from a different CWD
    # with a .env alongside it.
    load_dotenv()


# --------------------------------------------------------------------------- #
# Environment-derived defaults
# --------------------------------------------------------------------------- #

DEFAULT_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
DEFAULT_GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
DEFAULT_APP_LANGUAGE = os.getenv("APP_LANGUAGE", "en").strip()
DEFAULT_APP_THEME = os.getenv("APP_THEME", "dark").strip()
DEFAULT_OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
DEFAULT_OPENROUTER_IMAGE_MODEL = os.getenv(
    "OPENROUTER_IMAGE_MODEL", "inclusionai/ming-image-0.1-design-layer").strip()
DEFAULT_OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
DEFAULT_FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "openrouter").strip()
DEFAULT_FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openai/gpt-4o-mini").strip()
DEFAULT_OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
AVAILABLE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct-0905",
]

SUPPORTED_LANGUAGES = {
    "en": "English",
    "ur": "اردو",
    "es": "Español",
    "fr": "Français",
}

RTL_LANGUAGES = {"ur"}


# --------------------------------------------------------------------------- #
# Settings persistence
# --------------------------------------------------------------------------- #

def _ensure_settings_dir() -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> Dict[str, Any]:
    """Load persisted user settings, falling back to environment defaults."""
    _ensure_settings_dir()
    defaults: Dict[str, Any] = {
        "api_key": DEFAULT_GROQ_API_KEY,
        "base_url": DEFAULT_GROQ_BASE_URL,
        "model": DEFAULT_GROQ_MODEL,
        "openrouter_api_key": DEFAULT_OPENROUTER_API_KEY,
        "openrouter_image_model": DEFAULT_OPENROUTER_IMAGE_MODEL,
        "openrouter_model": DEFAULT_OPENROUTER_MODEL,
        "fallback_provider": DEFAULT_FALLBACK_PROVIDER,
        "fallback_model": DEFAULT_FALLBACK_MODEL,
        "OPENROUTER_api_key": DEFAULT_OPENROUTER_API_KEY,

    
        "language": DEFAULT_APP_LANGUAGE if DEFAULT_APP_LANGUAGE in SUPPORTED_LANGUAGES else "en",
        "theme": DEFAULT_APP_THEME if DEFAULT_APP_THEME in ("dark", "light") else "dark",
        "window_width": 1200,
        "window_height": 800,
    }
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            defaults.update({k: v for k, v in saved.items() if v is not None})
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


def save_settings(settings: Dict[str, Any]) -> None:
    _ensure_settings_dir()
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_history() -> list:
    _ensure_settings_dir()
    if HISTORY_PATH.exists():
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_history(threads: list) -> None:
    _ensure_settings_dir()
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as fh:
            json.dump(threads, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Translations
# --------------------------------------------------------------------------- #

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "app_title": "Groq Chat",
        "new_chat": "New Chat",
        "search_chats": "Search chats...",
        "settings": "Settings",
        "language": "Language",
        "theme": "Theme",
        "dark_theme": "Dark",
        "light_theme": "Light",
        "model": "Model",
        "api_key": "API Key",
        "save": "Save",
        "cancel": "Cancel",
        "type_message": "Message Groq...",
        "send": "Send",
        "attach_file": "Attach file",
        "you": "You",
        "assistant": "Groq",
        "thinking": "Thinking...",
        "stop_generating": "Stop generating",
        "delete_chat": "Delete chat",
        "rename_chat": "Rename chat",
        "untitled_chat": "New conversation",
        "no_api_key_title": "API Key Missing",
        "no_api_key_body": "Please set your Groq API key in Settings before sending messages.",
        "error_title": "Error",
        "copy": "Copy",
        "remove": "Remove",
        "clear_all_chats": "Clear all chats",
        "confirm_delete_title": "Delete chat?",
        "confirm_delete_body": "This will permanently delete this conversation.",
        "system_prompt_label": "You are a helpful, witty AI assistant powered by Groq. Respond in the same language the user writes in, unless asked otherwise.",
        "attached_files": "Attached files",
        "welcome_title": "How can I help you today?",
        "welcome_subtitle": "Ask me anything, or attach a file to get started.",
        "settings_saved": "Settings saved.",
        "file_too_large": "File is too large to attach (max 10 MB).",
        "unsupported_file": "Unsupported file type.",
        "edit": "Edit",
        "regenerate": "Regenerate",
        "share": "Share",
        "collapse_sidebar": "Collapse sidebar",
        "expand_sidebar": "Expand sidebar",
    },
    "ur": {
        "app_title": "Groq چیٹ",
        "new_chat": "نئی چیٹ",
        "search_chats": "چیٹس تلاش کریں...",
        "settings": "ترتیبات",
        "language": "زبان",
        "theme": "تھیم",
        "dark_theme": "ڈارک",
        "light_theme": "لائٹ",
        "model": "ماڈل",
        "api_key": "اے پی آئی کی",
        "save": "محفوظ کریں",
        "cancel": "منسوخ کریں",
        "type_message": "Groq کو پیغام بھیجیں...",
        "send": "بھیجیں",
        "attach_file": "فائل منسلک کریں",
        "you": "آپ",
        "assistant": "Groq",
        "thinking": "سوچ رہا ہے...",
        "stop_generating": "روکیں",
        "delete_chat": "چیٹ حذف کریں",
        "rename_chat": "چیٹ کا نام تبدیل کریں",
        "untitled_chat": "نئی گفتگو",
        "no_api_key_title": "اے پی آئی کی موجود نہیں",
        "no_api_key_body": "پیغام بھیجنے سے پہلے براہ کرم ترتیبات میں اپنی Groq اے پی آئی کی درج کریں۔",
        "error_title": "خرابی",
        "copy": "کاپی کریں",
        "remove": "ہٹائیں",
        "clear_all_chats": "تمام چیٹس صاف کریں",
        "confirm_delete_title": "چیٹ حذف کریں؟",
        "confirm_delete_body": "اس سے یہ گفتگو مستقل طور پر حذف ہو جائے گی۔",
        "system_prompt_label": "آپ ایک مددگار اور ذہین AI اسسٹنٹ ہیں جو Groq پر چلتا ہے۔ صارف جس زبان میں لکھے، اسی زبان میں جواب دیں جب تک کہ دوسری صورت میں نہ کہا جائے۔",
        "attached_files": "منسلک فائلیں",
        "welcome_title": "میں آپ کی کس طرح مدد کر سکتا ہوں؟",
        "welcome_subtitle": "کچھ بھی پوچھیں، یا شروع کرنے کے لیے فائل منسلک کریں۔",
        "settings_saved": "ترتیبات محفوظ ہو گئیں۔",
        "file_too_large": "فائل بہت بڑی ہے (زیادہ سے زیادہ 10 MB)۔",
        "unsupported_file": "غیر معاون فائل کی قسم۔",
        "edit": "ترمیم",
        "regenerate": "دوبارہ بنائیں",
        "share": "شیئر کریں",
        "collapse_sidebar": "سائیڈ بار سکیڑیں",
        "expand_sidebar": "سائیڈ بار پھیلائیں",
    },
    "es": {
        "app_title": "Groq Chat",
        "new_chat": "Nuevo chat",
        "search_chats": "Buscar chats...",
        "settings": "Configuración",
        "language": "Idioma",
        "theme": "Tema",
        "dark_theme": "Oscuro",
        "light_theme": "Claro",
        "model": "Modelo",
        "api_key": "Clave API",
        "save": "Guardar",
        "cancel": "Cancelar",
        "type_message": "Escribe un mensaje a Groq...",
        "send": "Enviar",
        "attach_file": "Adjuntar archivo",
        "you": "Tú",
        "assistant": "Groq",
        "thinking": "Pensando...",
        "stop_generating": "Detener generación",
        "delete_chat": "Eliminar chat",
        "rename_chat": "Renombrar chat",
        "untitled_chat": "Nueva conversación",
        "no_api_key_title": "Falta la clave API",
        "no_api_key_body": "Configura tu clave API de Groq en Configuración antes de enviar mensajes.",
        "error_title": "Error",
        "copy": "Copiar",
        "remove": "Quitar",
        "clear_all_chats": "Borrar todos los chats",
        "confirm_delete_title": "¿Eliminar chat?",
        "confirm_delete_body": "Esto eliminará permanentemente esta conversación.",
        "system_prompt_label": "Eres un asistente de IA útil e ingenioso impulsado por Groq. Responde en el mismo idioma que use el usuario, a menos que se indique lo contrario.",
        "attached_files": "Archivos adjuntos",
        "welcome_title": "¿Cómo puedo ayudarte hoy?",
        "welcome_subtitle": "Pregúntame lo que quieras, o adjunta un archivo para empezar.",
        "settings_saved": "Configuración guardada.",
        "file_too_large": "El archivo es demasiado grande (máx. 10 MB).",
        "unsupported_file": "Tipo de archivo no compatible.",
        "edit": "Editar",
        "regenerate": "Regenerar",
        "share": "Compartir",
        "collapse_sidebar": "Contraer barra lateral",
        "expand_sidebar": "Expandir barra lateral",
    },
    "fr": {
        "app_title": "Groq Chat",
        "new_chat": "Nouvelle discussion",
        "search_chats": "Rechercher des discussions...",
        "settings": "Paramètres",
        "language": "Langue",
        "theme": "Thème",
        "dark_theme": "Sombre",
        "light_theme": "Clair",
        "model": "Modèle",
        "api_key": "Clé API",
        "save": "Enregistrer",
        "cancel": "Annuler",
        "type_message": "Écrivez un message à Groq...",
        "send": "Envoyer",
        "attach_file": "Joindre un fichier",
        "you": "Vous",
        "assistant": "Groq",
        "thinking": "Réflexion en cours...",
        "stop_generating": "Arrêter la génération",
        "delete_chat": "Supprimer la discussion",
        "rename_chat": "Renommer la discussion",
        "untitled_chat": "Nouvelle conversation",
        "no_api_key_title": "Clé API manquante",
        "no_api_key_body": "Veuillez définir votre clé API Groq dans les paramètres avant d'envoyer des messages.",
        "error_title": "Erreur",
        "copy": "Copier",
        "remove": "Retirer",
        "clear_all_chats": "Effacer toutes les discussions",
        "confirm_delete_title": "Supprimer la discussion ?",
        "confirm_delete_body": "Cela supprimera définitivement cette conversation.",
        "system_prompt_label": "Vous êtes un assistant IA utile et spirituel propulsé par Groq. Répondez dans la même langue que l'utilisateur, sauf indication contraire.",
        "attached_files": "Fichiers joints",
        "welcome_title": "Comment puis-je vous aider aujourd'hui ?",
        "welcome_subtitle": "Posez-moi une question, ou joignez un fichier pour commencer.",
        "settings_saved": "Paramètres enregistrés.",
        "file_too_large": "Le fichier est trop volumineux (max 10 Mo).",
        "unsupported_file": "Type de fichier non pris en charge.",
        "edit": "Modifier",
        "regenerate": "Régénérer",
        "share": "Partager",
        "collapse_sidebar": "Réduire la barre latérale",
        "expand_sidebar": "Développer la barre latérale",
    },
}


class Translator:
    """Small helper wrapping TRANSLATIONS with a safe English fallback."""

    def __init__(self, language: str = "en") -> None:
        self.language = language if language in TRANSLATIONS else "en"

    def set_language(self, language: str) -> None:
        self.language = language if language in TRANSLATIONS else "en"

    def t(self, key: str) -> str:
        table = TRANSLATIONS.get(self.language, TRANSLATIONS["en"])
        return table.get(key, TRANSLATIONS["en"].get(key, key))

    def is_rtl(self) -> bool:
        return self.language in RTL_LANGUAGES


# Supported attachment extensions (kept here so UI + file_handler agree).
SUPPORTED_ATTACHMENT_EXTENSIONS = {
    ".txt", ".py", ".json", ".csv", ".pdf", ".md", ".log",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
}
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

"""
Configuration file for Intercom Translation Workflow
"""
import os
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Master catalogue of every language the user can choose from.
ALL_AVAILABLE_LANGUAGES: Dict[str, str] = {
    "ar": "Arabic",
    "bn-BD": "Bengali - Bangladesh",
    "bs": "Bosnian",
    "pt-BR": "Portuguese - Brazil",
    "bg": "Bulgarian",
    "ca": "Catalan",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish - Denmark",
    "nl": "Dutch",
    "et": "Estonian",
    "fi": "Finnish",
    "fr": "French",
    "de": "German",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese - Japan",
    "ko": "Korean",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "ms": "Malay",
    "mn": "Mongolian",
    "nb": "Norwegian",
    "fa": "Persian",
    "pl": "Polish",
    "pt": "Portuguese - Portugal",
    "ro": "Romanian",
    "ru": "Russian",
    "sr": "Serbian",
    "zh-CN": "Chinese - Simplified",
    "sl": "Slovenian",
    "es": "Spanish",
    "sw": "Swahili",
    "sv": "Swedish",
    "th": "Thai",
    "zh-TW": "Chinese - Traditional",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
}

# Default active target languages (used as seed if Supabase table is empty)
DEFAULT_TARGET_LANGUAGES: Dict[str, str] = {
    "ar": "Arabic",
    "zh-CN": "Chinese - Simplified",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese - Japan",
    "fa": "Persian",
    "es": "Spanish",
    "th": "Thai",
    "pt-BR": "Portuguese - Brazil",
}

# Mutable dict – updated at runtime from Supabase by language_service.
TARGET_LANGUAGES: Dict[str, str] = dict(DEFAULT_TARGET_LANGUAGES)

# Base language
BASE_LANGUAGE = "en"

# Intercom API Configuration
INTERCOM_ACCESS_TOKEN = os.getenv("INTERCOM_ACCESS_TOKEN", "")
INTERCOM_BASE_URL = "https://api.intercom.io"

# OpenAI API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Can use gpt-4o, gpt-4o-mini, gpt-4-turbo, etc.

# Translation settings
TRANSLATION_BATCH_SIZE = 5  # Number of articles to process in parallel
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Article filtering (optional - can filter by collection, tag, etc.)
INTERCOM_COLLECTION_ID = os.getenv("INTERCOM_COLLECTION_ID", "")  # Optional: specific collection
INTERCOM_TAG_ID = os.getenv("INTERCOM_TAG_ID", "")  # Optional: specific tag

# Supabase Configuration (backend data storage - mirrors Intercom articles)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://reiacekmluvuguqfswac.supabase.co")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJlaWFjZWttbHV2dWd1cWZzd2FjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MDAxMTE3NywiZXhwIjoyMDg1NTg3MTc3fQ.dAHUSTH5XhAS6WAGFA1YyqBcIFzjGCWWwsRj1jH8ruo")
# Optional: Postgres connection URI for running migrations (create table). From Dashboard > Database > Connection string (URI).
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")

# Super Admin Configuration (stored in environment variables)
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "sazzad@nextventures.io")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "Sazzad123")

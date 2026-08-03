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
    "uz": "Uzbek",
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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")  # Used for general app/server tasks
OPENAI_TRANSLATION_MODEL = os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini")  # Used for article translation

# Translation settings
TRANSLATION_BATCH_SIZE = 5  # Number of articles to process in parallel
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Article filtering (optional - can filter by collection, tag, etc.)
INTERCOM_COLLECTION_ID = os.getenv("INTERCOM_COLLECTION_ID", "")  # Optional: specific collection
INTERCOM_TAG_ID = os.getenv("INTERCOM_TAG_ID", "")  # Optional: specific tag

# Supabase Configuration (backend data storage - mirrors Intercom articles)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
# Optional: Postgres connection URI for running migrations (create table). From Dashboard > Database > Connection string (URI).
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")

# Super Admin Configuration (stored in environment variables)
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "sazzad@nextventures.io")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "")

# ─────────────────────────────────────────────────────────────────────────────
# Multi-product (tenant) registry
# ─────────────────────────────────────────────────────────────────────────────
# The hub serves several products (FundedNext, FN Market, ...) from ONE
# deployment. Each request resolves an "active product" and reads that product's
# secrets from the environment variables named below (resolved per-request in
# product_context.py). Non-secret branding/theme lives here in code; secrets
# never do. FundedNext reuses the ORIGINAL env var names, so its production
# configuration needs no changes and its behavior is unchanged.
#
# Adding a product later = one entry here + its env vars. No code path changes.
PRODUCTS: Dict[str, dict] = {
    "fundednext": {
        "name": "FundedNext",
        "short": "FN",
        "company": "NEXT Ventures",
        "domain": "fundednext.com",
        "support_email": "support@fundednext.com",
        "logo_file": "fn-logo.png",
        "help_center_match": "fundednext",
        "default_collection": "About FundedNext",
        # Names of the env vars holding this product's secrets (read per-request):
        "intercom_token_env": "INTERCOM_ACCESS_TOKEN",
        "supabase_url_env": "SUPABASE_URL",
        "supabase_key_env": "SUPABASE_SERVICE_KEY",
        "supabase_db_url_env": "SUPABASE_DB_URL",
        "openai_key_env": "OPENAI_API_KEY",
        "theme": {
            "primary": "#2E6DA4",
            "primary_hover": "#1A3D63",
            "accent": "#4A90C4",
            "sidebar_bg": "#0D2137",
            "sidebar_deep": "#102A4C",
            "bg": "#F2F8FD",
            "text": "#0D2137",
        },
        "default_languages": DEFAULT_TARGET_LANGUAGES,
    },
    # "fnmarket": { ... }  # added in Phase 3 (needs FN Market env vars + Supabase)
}

# The product used when a request specifies none (keeps cron/legacy calls working
# exactly as today).
DEFAULT_PRODUCT = "fundednext"

# ─────────────────────────────────────────────────────────────────────────────
# Control plane (auth / admins) — product-INDEPENDENT
# ─────────────────────────────────────────────────────────────────────────────
# Login must succeed before any product is chosen, so authentication uses a fixed
# control database, never the per-request product DB. For now that is FundedNext's
# existing Supabase (its current env vars). Override only if auth ever moves to a
# dedicated control project.
CONTROL_SUPABASE_URL = os.getenv("CONTROL_SUPABASE_URL", SUPABASE_URL)
CONTROL_SUPABASE_KEY = os.getenv("CONTROL_SUPABASE_KEY", SUPABASE_SERVICE_KEY)

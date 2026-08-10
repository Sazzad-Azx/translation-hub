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

# Shared cost analyzer: FundedNext and FN Market report the SAME API cost /
# cost-analysis data (one external OpenAI-usage analyzer, one set of key ids),
# so both product dashboards reference this single block. A future product that
# needs different (or no) cost data gets its own block, or omits `cost_analyzer`
# to hide the cost panel entirely.
_SHARED_COST_ANALYZER = {
    "url": "https://intercom-analyzer-shizans-projects-a7b50fa1.vercel.app/api",
    "target_keys": ["key_24T9PNCgnvWHZvxc", "key_DDHe898miisDLF3w"],
}

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
        # Live cost panel: shared analyzer (same data on every product's dashboard).
        # Omit `cost_analyzer` on a product to hide the cost card/chart entirely
        # (see templates/index.html).
        "cost_analyzer": _SHARED_COST_ANALYZER,
        # Postgres schema this product's data lives in (shared-DB isolation).
        "schema": "public",
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
    "fnmarket": {
        "name": "FNmarkets",
        "short": "FN",
        "company": "NEXT Ventures",
        "domain": "fnmarket.com",
        "support_email": "support@fnmarket.com",
        # Placeholder logo (reuses FN's asset so nothing 404s) — swap for a real
        # FN Market logo file in static/ when available.
        "logo_file": "fn-logo.png",
        "help_center_match": "fnmarket",
        "default_collection": "About FN Market",
        # Shares FundedNext's cost analyzer → identical API cost / cost analysis.
        "cost_analyzer": _SHARED_COST_ANALYZER,
        # Shared-DB isolation: FN Market reuses FundedNext's Supabase PROJECT but
        # its data lives in a separate `fnmarket` Postgres schema (selected per
        # request via PostgREST Accept-Profile/Content-Profile headers). So the
        # Supabase URL/key/db-url env vars are the SAME as FundedNext's — only the
        # schema differs. FN Market needs no FNMARKET_SUPABASE_* vars.
        "schema": "fnmarket",
        "intercom_token_env": "FNMARKET_INTERCOM_TOKEN",
        "supabase_url_env": "SUPABASE_URL",
        "supabase_key_env": "SUPABASE_SERVICE_KEY",
        "supabase_db_url_env": "SUPABASE_DB_URL",
        # Reuses FundedNext's OpenAI key/quota; set FNMARKET_OPENAI_KEY + change
        # this to it later if you want translation cost attributed separately.
        "openai_key_env": "OPENAI_API_KEY",
        # FNmarkets theme — "Direction B": navy sidebar + purple/indigo brand
        # accent (matches the final dashboard/control-tower mockups). Keys beyond
        # the base 7 drive the themeable tokens introduced for the multi-tenant
        # palette (see the :root override in templates/index.html). accent_rgb /
        # light_rgb are bare "r,g,b" channels used inside rgba() tints — NOT hex.
        "theme": {
            "primary": "#5B5BEF",        # brand (--primary / --mid)
            "primary_hover": "#4B49DE",  # brand-600 (button hover)
            "accent": "#8B7BFF",         # lighter brand (icons/accents/--steel)
            "sidebar_bg": "#122344",     # navy panel top
            "sidebar_deep": "#0A1730",   # navy panel bottom
            "bg": "#F4F6FB",             # cool app background tint
            "text": "#171634",           # ink (--text / --navy)
            "dark": "#211F45",           # dark-indigo headings (--dark)
            "light": "#B7C2DB",          # navy-tint sidebar text (--light)
            "mist": "#ECECFE",           # light brand tint (--mist / --primary-light)
            "mist2": "#DAD8FB",          # slightly deeper tint for gradients (--mist2)
            "text_muted": "#5A6480",     # ink-soft body/muted text (--text-muted)
            "accent_rgb": "91,91,239",   # brand rgb → purple active nav / hover glows
            "light_rgb": "183,194,219",  # navy-tint light rgb → sidebar nav text
            "line_rgb": "150,160,185",   # neutral cool-grey → hairline borders (~#E9ECF4)
            "chart_bar": "#5B5BEF",      # dashboard bar chart → brand purple
            "chart_line": "#5B5BEF",     # dashboard cost line → brand purple
            "grad_a": "#5B5BEF",         # primary-gradient start → bright brand
            "grad_b": "#4B49DE",         # primary-gradient end → brand-600
        },
        # Seed set (same as FundedNext's defaults); edit in-app per product.
        "default_languages": dict(DEFAULT_TARGET_LANGUAGES),
    },
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

# ─────────────────────────────────────────────────────────────────────────────
# Make the shared target-language set follow the active product (multi-tenant).
# TARGET_LANGUAGES above is the single-tenant seed; override it with a proxy that
# resolves to the active product's language cache. Imported lazily here to avoid a
# circular import (product_context only reads config attributes at call time).
# ─────────────────────────────────────────────────────────────────────────────
import product_context as _pc  # noqa: E402
TARGET_LANGUAGES = _pc.LazyDict(_pc.active_languages_dict)

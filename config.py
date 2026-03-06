"""
Configuration file for Intercom Translation Workflow
"""
import os
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Target languages based on the UI (11 languages)
TARGET_LANGUAGES: Dict[str, str] = {
    "ar": "Arabic (UAE)",
    "zh-CN": "Chinese - Simplified",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese - Japan",
    "fa": "Persian",
    "es": "Spanish",
    "th": "Thai",
    "pt-BR": "Portuguese - Brazil"
}

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

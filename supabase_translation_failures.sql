-- Last failed translation attempt per article × language.
-- A failed job never writes to article_translations, so without this the
-- Translate/Push pages can't tell "failed" from "never requested".
-- Row is written on failure and deleted on the next successful translation.
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/reiacekmluvuguqfswac/sql

CREATE TABLE IF NOT EXISTS public.translation_failures (
  parent_intercom_article_id TEXT NOT NULL,
  target_locale TEXT NOT NULL,
  error TEXT NOT NULL DEFAULT '',
  failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (parent_intercom_article_id, target_locale)
);

-- FN Market mirror (shared-DB isolation, see fnmarket_schema_setup.sql).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'fnmarket') THEN
    CREATE TABLE IF NOT EXISTS fnmarket.translation_failures (LIKE public.translation_failures INCLUDING ALL);
    GRANT ALL ON fnmarket.translation_failures TO service_role;
  END IF;
END $$;

NOTIFY pgrst, 'reload schema';

-- Migration: article_translations table for translation persistence
-- Run in Supabase Dashboard: SQL Editor (run this once to create the table).
--
-- Security: All writes/reads to this table are done server-side using
-- SUPABASE_SERVICE_KEY (service role). The browser must NOT have the service role key;
-- only the Flask backend uses it (see translation_supabase.py and app.py).

create table if not exists public.article_translations (
  id uuid primary key default gen_random_uuid(),
  content_item_id uuid not null,
  parent_intercom_article_id text not null,
  source_locale text not null default 'en',
  target_locale text not null,
  translated_title text,
  translated_body_html text,
  status text not null default 'draft',
  engine text,
  model text,
  source_checksum text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(parent_intercom_article_id, target_locale)
);

create index if not exists idx_article_translations_content_item_id
  on public.article_translations(content_item_id);
create index if not exists idx_article_translations_parent_intercom_article_id
  on public.article_translations(parent_intercom_article_id);
create index if not exists idx_article_translations_status
  on public.article_translations(status);

-- Push tracking columns (added for Push module)
ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS pushed_at timestamptz DEFAULT NULL;
ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS push_error text DEFAULT '';

-- Optional: FK to intercom_content_items (if you want referential integrity)
-- alter table public.article_translations
--   add constraint fk_article_translations_content_item
--   foreign key (content_item_id) references public.intercom_content_items(id) on delete cascade;

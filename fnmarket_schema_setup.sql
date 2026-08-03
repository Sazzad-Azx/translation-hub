-- ============================================================================
-- FN Market schema setup (shared-DB multi-tenant isolation)
-- Run this ONCE in the SQL Editor of the SAME Supabase project that hosts
-- FundedNext ("translation" project).
--
-- It creates an `fnmarket` schema whose tables mirror FundedNext's `public`
-- tables exactly (cloned with LIKE ... INCLUDING ALL), so FN Market's data lives
-- physically apart from FundedNext's. Admins/auth stay in `public` and are NOT
-- duplicated here (login is product-independent).
--
-- AFTER running this, you MUST also add `fnmarket` to the API's exposed schemas:
--   Supabase Dashboard -> Project Settings -> API -> "Exposed schemas"
--   -> add  fnmarket  (keep public, graphql_public) -> Save.
-- Without that, PostgREST rejects Accept-Profile: fnmarket requests.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS fnmarket;

-- Clone each product-data table from public into fnmarket (structure only, no
-- rows). Skips any table that doesn't exist in public instead of erroring.
DO $$
DECLARE
    t text;
    tables text[] := ARRAY[
        'intercom_articles',
        'article_translations',
        'pull_registry',
        'automation_settings',
        'daily_api_costs',
        'intercom_content_items',
        'intercom_content_versions',
        'glossaries',
        'glossary_terms',
        'glossary_term_translations',
        'glossary_usage_log'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS fnmarket.%I (LIKE public.%I INCLUDING ALL)',
                t, t
            );
            RAISE NOTICE 'created fnmarket.%', t;
        ELSE
            RAISE NOTICE 'skipped (public.% not found)', t;
        END IF;
    END LOOP;
END $$;

-- Grants so the API (service_role) can use the schema and its tables.
GRANT USAGE ON SCHEMA fnmarket TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA fnmarket TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA fnmarket TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA fnmarket GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA fnmarket GRANT ALL ON SEQUENCES TO service_role;

-- Ask PostgREST to reload so it picks up the new schema/tables.
NOTIFY pgrst, 'reload schema';

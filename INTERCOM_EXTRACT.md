# Extracting Information from Intercom (API 2.14)

This document summarizes the **official Intercom REST API** approach to extracting Help Center content, based on [Intercom's REST API Reference](https://developers.intercom.com/docs/references/rest-api/api.intercom.io).

## Authentication

- **Header**: `Authorization: Bearer <YOUR_ACCESS_TOKEN>`
- **API version**: `Intercom-Version: 2.14`
- **Base URL**: `https://api.intercom.io` (or `https://api.eu.intercom.io` / `https://api.au.intercom.io` for regional)

## Fetching Articles from a Specific Help Center (e.g. FundedNext)

When you have **multiple Help Centers**, the documented way to get articles for **one** Help Center is:

### 1. List all Help Centers

- **Endpoint**: `GET /help_center/help_centers`
- **Docs**: [List all Help Centers](https://developers.intercom.com/docs/references/rest-api/api.intercom.io/help-center/listhelpcenters)
- **Response**: `{ "type": "list", "data": [ { "id", "display_name", "identifier", "url", ... } ] }`
- Use this to find the Help Center whose `display_name` or `identifier` matches your target (e.g. "FundedNext Help Center").

### 2. Search articles scoped to that Help Center

- **Endpoint**: `GET /articles/search`
- **Query params**:
  - `help_center_id` (integer) – ID of the Help Center from step 1
  - `state` – `published` | `draft` | `all`
  - `phrase` (optional) – search phrase; omit or empty to get all articles in that Help Center
  - Pagination: `page`, `per_page` (response includes `pages.next`, `total_pages`)
- **Docs**: [Search for articles](https://developers.intercom.com/docs/references/rest-api/api.intercom.io/articles/searcharticles)
- **Response**: `{ "type": "list", "total_count", "data": { "articles": [...], "highlights": [...] }, "pages": {...} }`

### 3. Get full article details (optional)

- **Endpoint**: `GET /articles/{id}`
- **Docs**: [Retrieve an article](https://developers.intercom.com/docs/references/rest-api/api.intercom.io/articles/retrievearticle)
- Use this when the search result does not include full `body` or `title` and you need complete content.

## Alternative: Collections

- **List collections**: `GET /help_center/collections` (each collection has `help_center_id`)
- **List articles**: `GET /articles` (optionally with `collection_id` if supported by your API version)
- You can list collections for the app, filter by `help_center_id` to those belonging to FundedNext, then fetch articles per collection. Alternatively, fetch all articles via `GET /articles` and filter client-side by collection IDs that belong to the target Help Center.

## Summary: FundedNext Help Center flow in this repo

1. **List Help Centers** → find the one with "FundedNext" in `display_name`, `name`, or `identifier`.
2. If none match by name, use the **first** Help Center in the list (often the Default one in the UI).
3. **Search articles** → `GET /articles/search?help_center_id=<id>&state=published` (paginate as needed).
4. **Enrich** → For any article missing `body`/`title`, call `GET /articles/{id}`.

This is implemented in:

- `intercom_client.get_fundednext_help_center_articles(limit=..., fetch_full=True)` – single method that does steps 1–4.
- `fetch_and_dump_10_articles.py` – uses that method first, then falls back to collections + list + search if no articles are returned.

**Token / workspace:** The Help Centers list is per app/workspace. If your token only sees one Help Center (e.g. `identifier='n8n-dev'`), that one is used. To see "FundedNext Help Center", "Affiliate and payment partner section", and "FN Futures" in the API, use an access token from the Intercom app that shows those in **All Help Centers**. Run `python list_help_centers.py` to see what your token returns.

## References

- [Articles API (List, Retrieve, Search)](https://developers.intercom.com/docs/references/rest-api/api.intercom.io/articles)
- [Help Center (List Help Centers, List Collections)](https://developers.intercom.com/docs/references/rest-api/api.intercom.io/help-center)
- [Fetching articles from a specific help center (Community)](https://community.intercom.com/api-webhooks-23/fetching-articles-from-a-specific-help-center-using-api-11270)

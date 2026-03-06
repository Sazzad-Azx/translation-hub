"""
Intercom API Client for pulling and updating articles
"""
import requests
import time
from typing import List, Dict, Optional
from config import INTERCOM_ACCESS_TOKEN, INTERCOM_BASE_URL, MAX_RETRIES, RETRY_DELAY


class IntercomClient:
    """Client for interacting with Intercom Help Center API"""
    
    def __init__(self, access_token: str = None):
        self.access_token = access_token or INTERCOM_ACCESS_TOKEN
        self.base_url = INTERCOM_BASE_URL
        # Intercom uses Basic Auth with the access token
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Intercom-Version": "2.14"  # Use latest API version for Help Center / Articles
        }
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.request(method, url, headers=self.headers, **kwargs)
                
                # Debug: Print response details on error
                if response.status_code >= 400:
                    print(f"API Error {response.status_code}: {response.text[:200]}")
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", RETRY_DELAY))
                    print(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.RequestException as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                print(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(RETRY_DELAY * (attempt + 1))
        
        raise Exception(f"Failed to make request after {MAX_RETRIES} attempts")
    
    def get_articles(self, collection_id: Optional[str] = None, tag_id: Optional[str] = None) -> List[Dict]:
        """
        Fetch all articles from Intercom Help Center
        
        Args:
            collection_id: Optional collection ID to filter articles
            tag_id: Optional tag ID to filter articles
            
        Returns:
            List of article dictionaries
        """
        articles = []
        page = 1
        per_page = 50
        
        while True:
            params = {
                "page": page,
                "per_page": per_page
            }
            
            # Add filters if provided
            if collection_id:
                params["collection_id"] = collection_id
            
            response = self._make_request("GET", "/articles", params=params)
            data = response.json()
            
            articles_batch = data.get("data", [])
            
            # Filter by tag if provided
            if tag_id:
                articles_batch = [
                    article for article in articles_batch
                    if tag_id in [tag.get("id") for tag in article.get("tags", {}).get("data", [])]
                ]
            
            articles.extend(articles_batch)
            
            # Check if there are more pages
            if not data.get("pages", {}).get("next"):
                break
            
            page += 1
        
        return articles

    def get_published_articles(self, limit: int = 10, collection_id: Optional[str] = None) -> List[Dict]:
        """
        Fetch published articles from Intercom Help Center (for demo/sync).
        Returns up to `limit` published articles.
        """
        articles = []
        page = 1
        per_page = min(50, max(limit, 20))
        while len(articles) < limit:
            params = {"page": page, "per_page": per_page}
            if collection_id:
                params["collection_id"] = collection_id
            response = self._make_request("GET", "/articles", params=params)
            data = response.json()
            batch = data.get("data", [])
            for a in batch:
                if (a.get("state") or "").lower() == "published":
                    articles.append(a)
                    if len(articles) >= limit:
                        return articles
            if not batch or not data.get("pages", {}).get("next"):
                break
            page += 1
        return articles
    
    def get_help_centers(self) -> List[Dict]:
        """
        Fetch all Help Centers (e.g. FundedNext Help Center).
        GET /help_center/help_centers - returns list of help centers with id, display_name, etc.
        """
        response = self._make_request("GET", "/help_center/help_centers")
        data = response.json()
        return data.get("data", [])

    def get_collections(self) -> List[Dict]:
        """
        Fetch all collections from Intercom Help Center.
        Returns list of collections (each has id, name, etc.).
        """
        collections = []
        page = 1
        per_page = 50
        while True:
            params = {"page": page, "per_page": per_page}
            response = self._make_request("GET", "/help_center/collections", params=params)
            data = response.json()
            batch = data.get("data", [])
            collections.extend(batch)
            pages = data.get("pages") or {}
            if not batch or not pages.get("next"):
                break
            page = (pages.get("page") or page) + 1
        return collections
    
    def get_articles_by_collection_name(self, collection_name: str) -> List[Dict]:
        """
        Get all articles in a collection by collection name (e.g. 'About FundedNext').
        """
        collections = self.get_collections()
        collection_id = None
        for c in collections:
            name = (c.get("name") or "").strip()
            if name and collection_name.lower() in name.lower():
                collection_id = c.get("id")
                break
        if not collection_id:
            raise ValueError(f"Collection not found: {collection_name}")
        return self.get_articles(collection_id=collection_id)

    def get_all_help_center_articles(self) -> List[Dict]:
        """
        Fetch all articles from the Help Center by listing every collection
        and getting articles in each. Returns deduplicated list (by article id).
        Use this to access all articles in e.g. FundedNext Help Center.
        """
        seen_ids = set()
        out = []
        collections = self.get_collections()
        for c in collections:
            cid = c.get("id")
            if not cid:
                continue
            for article in self.get_articles(collection_id=str(cid)):
                aid = article.get("id")
                if aid is not None and str(aid) not in seen_ids:
                    seen_ids.add(str(aid))
                    out.append(article)
        return out

    def search_articles(
        self,
        help_center_id: Optional[int] = None,
        state: str = "published",
        phrase: str = "",
        limit: int = 50,
    ) -> List[Dict]:
        """
        Search articles (GET /articles/search). Use help_center_id to scope to a
        specific Help Center (e.g. FundedNext). phrase can be empty to get all.
        """
        articles = []
        page = 1
        per_page = min(25, max(10, limit))
        while len(articles) < limit:
            params = {"state": state, "per_page": per_page, "page": page}
            if help_center_id is not None:
                params["help_center_id"] = help_center_id
            if phrase:
                params["phrase"] = phrase
            try:
                response = self._make_request("GET", "/articles/search", params=params)
            except Exception:
                break
            data = response.json()
            batch = (data.get("data") or {}).get("articles") or []
            articles.extend(batch)
            pages = data.get("pages") or {}
            if not batch or not pages.get("next") or page >= (pages.get("total_pages") or 1):
                break
            page += 1
        return articles[:limit]

    def get_fundednext_help_center_articles(
        self,
        limit: int = 100,
        fetch_full: bool = True,
    ) -> List[Dict]:
        """
        Fetch articles from the FundedNext Help Center using official Intercom API flow:

        1. GET /help_center/help_centers - list all Help Centers
        2. Find the Help Center for "FundedNext Help Center" (display_name, identifier, or name)
        3. If none match by name, use the first Help Center in the list (often the Default one)
        4. GET /articles/search?help_center_id={id}&state=published
        5. Optionally GET /articles/{id} for each to get full body/title if missing

        See: https://developers.intercom.com/docs/references/rest-api/api.intercom.io/articles/searcharticles
        and https://developers.intercom.com/docs/references/rest-api/api.intercom.io/help-center/listhelpcenters
        """
        help_centers = self.get_help_centers()
        fundednext_id = None
        first_id = None
        for hc in help_centers:
            try:
                hc_id = int(hc.get("id"))
            except (TypeError, ValueError):
                continue
            if first_id is None:
                first_id = hc_id
            display_name = (hc.get("display_name") or hc.get("name") or "").lower()
            identifier = (hc.get("identifier") or "").lower()
            if "fundednext" in display_name or "fundednext" in identifier:
                fundednext_id = hc_id
                break
        if fundednext_id is None and first_id is not None:
            fundednext_id = first_id
        if fundednext_id is None:
            return []
        # When API returns only one Help Center (e.g. per-app token), we use it.
        # When it returns multiple (e.g. FundedNext Help Center, Affiliate section, FN Futures),
        # we prefer the one whose name contains "fundednext", else the first (often Default).
        articles = self.search_articles(
            help_center_id=fundednext_id,
            state="published",
            phrase="",
            limit=limit,
        )
        if fetch_full and articles:
            out = []
            for a in articles:
                if a.get("body") is not None and a.get("title"):
                    out.append(a)
                    continue
                try:
                    full = self.get_article(str(a.get("id", "")))
                    if full:
                        out.append(full)
                    else:
                        out.append(a)
                except Exception:
                    out.append(a)
            return out
        return articles

    def get_article(self, article_id: str) -> Dict:
        """
        Get a specific article by ID
        
        Args:
            article_id: The article ID
            
        Returns:
            Article dictionary
        """
        response = self._make_request("GET", f"/articles/{article_id}")
        return response.json()
    
    def get_article_translations(self, article_id: str) -> Dict[str, Dict]:
        """
        Get all translations for an article
        
        Args:
            article_id: The article ID
            
        Returns:
            Dictionary mapping language codes to translation data
        """
        try:
            response = self._make_request("GET", f"/articles/{article_id}/translations")
            translations = {}
            
            for translation in response.json().get("data", []):
                lang_code = translation.get("locale", {}).get("code", "")
                translations[lang_code] = translation
            
            return translations
        except requests.exceptions.HTTPError as e:
            # 404 means no translations exist yet, which is fine
            if e.response.status_code == 404:
                return {}
            raise
    
    def create_or_update_translation(
        self,
        article_id: str,
        locale: str,
        title: str,
        body: str,
        description: Optional[str] = None
    ) -> Dict:
        """
        Create or update a translation for an article.

        Tries multiple approaches in order:
        1. POST /articles/{id}/translations (dedicated translations endpoint)
        2. PUT /articles/{id} with translated_content (multi-language workspaces)
        3. Create a separate article with [LOCALE] prefix (fallback for workspaces
           without multi-language support)
        
        Args:
            article_id: The article ID
            locale: Language code (e.g., 'fr', 'de', 'es')
            title: Translated title
            body: Translated body/content
            description: Optional translated description
            
        Returns:
            Updated/created article or translation dictionary
        """
        translation_data = {
            "title": title,
            "body": body,
            "locale": locale
        }
        
        if description:
            translation_data["description"] = description
        
        # ── Approach 1: /translations sub-endpoint ──
        try:
            existing_translations = self.get_article_translations(article_id)
            if locale in existing_translations:
                translation_id = existing_translations[locale]["id"]
                response = self._make_request(
                    "PUT",
                    f"/articles/{article_id}/translations/{translation_id}",
                    json=translation_data
                )
                return response.json()
        except Exception:
            pass

        try:
            response = self._make_request(
                "POST",
                f"/articles/{article_id}/translations",
                json=translation_data
            )
            return response.json()
        except requests.exceptions.HTTPError:
            pass  # endpoint not available – continue
        except Exception:
            pass

        # ── Approach 2: PUT article with translated_content ──
        try:
            parent_article = self.get_article(article_id)
            article_update = {
                "translated_content": {
                    locale: {
                        "title": title,
                        "body": body,
                        "state": "published"
                    }
                }
            }
            if description:
                article_update["translated_content"][locale]["description"] = description
            if "author_id" in parent_article:
                article_update["author_id"] = parent_article["author_id"]

            response = self._make_request("PUT", f"/articles/{article_id}", json=article_update)
            result = response.json()

            # Verify translated_content was actually saved
            verify = self._make_request("GET", f"/articles/{article_id}")
            if verify.json().get("translated_content"):
                return result
            # translated_content silently ignored → fall through
        except Exception:
            pass

        # ── Approach 3: Create separate translated article ──
        locale_upper = locale.upper()
        translated_title = f"[{locale_upper}] {title}"
        print(f"    [INFO] Creating separate [{locale_upper}] article in Intercom...")
        created = self.create_article(
            title=translated_title,
            body=body,
            description=description or "",
            state="published",
        )
        return created
    
    def create_article(
        self,
        title: str,
        body: str,
        description: str = "",
        author_id: Optional[str] = None,
        state: str = "published",
    ) -> Dict:
        """
        Create a new article in the Intercom Help Center.

        Args:
            title: Article title
            body: Article body (HTML)
            description: Short description
            author_id: Author admin ID (if None, auto-detected via /me)
            state: 'published' or 'draft'

        Returns:
            Created article dictionary (contains 'id', 'title', etc.)
        """
        if not author_id:
            # Auto-detect author_id from /me
            try:
                me_resp = self._make_request("GET", "/me")
                me_data = me_resp.json()
                author_id = str(me_data.get("id", ""))
            except Exception:
                pass

        article_data: Dict = {
            "title": title,
            "body": body,
            "state": state,
        }
        if author_id:
            article_data["author_id"] = int(author_id)
        if description:
            article_data["description"] = description

        response = self._make_request("POST", "/articles", json=article_data)
        return response.json()
    
    def publish_article(self, article_id: str) -> Dict:
        """
        Publish an article
        
        Args:
            article_id: The article ID
            
        Returns:
            Updated article dictionary
        """
        response = self._make_request("PUT", f"/articles/{article_id}", json={"state": "published"})
        return response.json()

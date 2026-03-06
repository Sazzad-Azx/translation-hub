"""
Main workflow orchestrator for Intercom translation process
"""
import time
import requests
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from intercom_client import IntercomClient
from translator import GPTTranslator
from config import (
    TARGET_LANGUAGES,
    BASE_LANGUAGE,
    TRANSLATION_BATCH_SIZE,
    INTERCOM_COLLECTION_ID,
    INTERCOM_TAG_ID,
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY
)


class TranslationWorkflow:
    """Orchestrates the pull-translate-push workflow"""
    
    def __init__(self, intercom_client: IntercomClient = None, translator: GPTTranslator = None):
        self.intercom_client = intercom_client or IntercomClient()
        self.translator = translator or GPTTranslator()
        self.stats = {
            "articles_processed": 0,
            "translations_created": 0,
            "translations_updated": 0,
            "errors": []
        }
    
    def _get_article_from_supabase(self, article_id: str) -> Optional[Dict]:
        """Try to get article from Supabase (intercom_articles or content tables)."""
        try:
            from supabase_client import list_articles
            
            # Try intercom_articles table first
            try:
                articles = list_articles()
                for a in articles:
                    if str(a.get('intercom_id', '')) == str(article_id):
                        return {
                            'id': a.get('intercom_id'),
                            'title': a.get('title', ''),
                            'description': a.get('description', ''),
                            'body': a.get('body', '')
                        }
            except Exception:
                pass
            
            # Try content_items/versions tables
            try:
                if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                    REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1"
                    headers = {
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                    }
                    # Find content_item by external_id
                    items_url = f"{REST_BASE}/intercom_content_items"
                    items_resp = requests.get(
                        items_url,
                        headers=headers,
                        params={"external_id": f"eq.{article_id}", "select": "id"},
                        timeout=30,
                    )
                    if items_resp.ok and items_resp.text:
                        items = items_resp.json()
                        if items and len(items) > 0:
                            item_id = items[0].get('id')
                            # Get version with locale='en' or first available
                            versions_url = f"{REST_BASE}/intercom_content_versions"
                            versions_resp = requests.get(
                                versions_url,
                                headers=headers,
                                params={"content_item_id": f"eq.{item_id}", "select": "title,body_raw,locale", "order": "locale.asc"},
                                timeout=30,
                            )
                            if versions_resp.ok and versions_resp.text:
                                versions = versions_resp.json()
                                if versions and len(versions) > 0:
                                    # Prefer 'en' locale, else first
                                    version = next((v for v in versions if v.get('locale') == 'en'), versions[0])
                                    return {
                                        'id': article_id,
                                        'title': version.get('title', ''),
                                        'description': '',
                                        'body': version.get('body_raw', '')
                                    }
            except Exception:
                pass
        except Exception:
            pass
        return None
    
    def _ensure_article_in_intercom(self, article: Dict) -> str:
        """
        Ensure an article exists in the Intercom workspace accessible by the
        current API token.  If the article (by its original Intercom ID) is not
        found, create it in Intercom and return the NEW Intercom article ID.
        Returns the usable Intercom article ID (str).
        """
        original_id = str(article.get("id", ""))
        # Quick check: does the article already exist in the accessible workspace?
        try:
            existing = self.intercom_client.get_article(original_id)
            if existing and existing.get("id"):
                return str(existing["id"])
        except Exception:
            pass  # Article not found with original ID

        # Article does not exist in this workspace -> create it
        title = article.get("title", "Untitled")
        body = article.get("body") or article.get("body_raw") or ""
        description = article.get("description") or ""

        print(f"    [INFO] Article not in Intercom workspace. Creating it...")
        created = self.intercom_client.create_article(
            title=title,
            body=body,
            description=description,
            state="published",
        )
        new_id = str(created.get("id", ""))
        print(f"    [INFO] Created article in Intercom with new ID: {new_id}")
        return new_id
    
    def process_article(self, article: Dict, languages: List[str] = None) -> Dict:
        """
        Process a single article: translate and update in Intercom
        
        Args:
            article: Article dictionary from Intercom or Supabase
            languages: List of language codes to translate to (default: all target languages)
            
        Returns:
            Dictionary with processing results
        """
        article_id = article.get("id")
        article_title = article.get("title", "Unknown")
        
        if not languages:
            languages = list(TARGET_LANGUAGES.keys())
        
        results = {
            "article_id": article_id,
            "article_title": article_title,
            "translations": {},
            "errors": []
        }
        
        print(f"\nProcessing article: {article_title} (ID: {article_id})")
        
        # Ensure article exists in the Intercom workspace; create if needed
        try:
            intercom_article_id = self._ensure_article_in_intercom(article)
            print(f"  Using Intercom article ID: {intercom_article_id}")
        except Exception as e:
            error_msg = f"Failed to ensure article in Intercom: {str(e)}"
            print(f"  [ERROR] {error_msg}")
            results["errors"].append(error_msg)
            self.stats["errors"].append({
                "article_id": article_id,
                "article_title": article_title,
                "error": error_msg
            })
            return results

        # Get base article content - use the article passed in (already fetched)
        base_article = article
        
        # Translate to each target language
        for lang_code in languages:
            lang_name = TARGET_LANGUAGES.get(lang_code, lang_code)
            
            try:
                print(f"  Translating to {lang_name} ({lang_code})...")
                
                # Translate the article
                translated_content = self.translator.translate_article(
                    base_article,
                    target_language=lang_code,
                    source_language=BASE_LANGUAGE
                )
                
                # Update translation in Intercom using the valid article ID
                try:
                    self.intercom_client.create_or_update_translation(
                        article_id=intercom_article_id,
                        locale=lang_code,
                        title=translated_content["title"],
                        body=translated_content["body"],
                        description=translated_content.get("description")
                    )
                    results["translations"][lang_code] = "success (Intercom)"
                    print(f"    [OK] Successfully translated to {lang_name} (saved to Intercom)")
                except Exception as intercom_error:
                    error_str = str(intercom_error)
                    print(f"    [WARNING] Intercom translation update failed: {error_str}")
                    # Fallback: save to Supabase
                    print(f"    [INFO] Saving translation to Supabase as fallback...")
                    try:
                        from translation_supabase import upsert_article_translation
                        upsert_article_translation(
                            parent_intercom_article_id=str(article_id),
                            target_locale=lang_code,
                            translated_title=translated_content["title"],
                            translated_body_html=translated_content["body"],
                            status="draft",
                            source_locale=BASE_LANGUAGE
                        )
                        results["translations"][lang_code] = "success (Supabase fallback)"
                        print(f"    [OK] Translation saved to Supabase for {lang_name}")
                    except Exception as supabase_error:
                        error_msg = f"Intercom: {error_str}; Supabase: {str(supabase_error)}"
                        print(f"    [ERROR] {error_msg}")
                        results["errors"].append(error_msg)
                        self.stats["errors"].append({
                            "article_id": article_id,
                            "article_title": article_title,
                            "language": lang_code,
                            "error": error_msg
                        })
                
                self.stats["translations_created"] += 1
                
                # Small delay to avoid rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                error_msg = f"Failed to translate {article_title} to {lang_name}: {str(e)}"
                print(f"    [ERROR] Error: {error_msg}")
                results["errors"].append(error_msg)
                self.stats["errors"].append({
                    "article_id": article_id,
                    "article_title": article_title,
                    "language": lang_code,
                    "error": str(e)
                })
        
        self.stats["articles_processed"] += 1
        return results
    
    def run(
        self,
        collection_id: Optional[str] = None,
        tag_id: Optional[str] = None,
        article_ids: Optional[List[str]] = None,
        languages: Optional[List[str]] = None
    ) -> Dict:
        """
        Run the complete translation workflow
        
        Args:
            collection_id: Optional collection ID to filter articles
            tag_id: Optional tag ID to filter articles
            article_ids: Optional list of specific article IDs to process
            languages: Optional list of language codes to translate to
            
        Returns:
            Dictionary with workflow results and statistics
        """
        print("=" * 60)
        print("Intercom Translation Workflow")
        print("=" * 60)
        
        # Get articles
        if article_ids:
            print(f"\nFetching {len(article_ids)} specific articles...")
            articles = []
            for article_id in article_ids:
                try:
                    # Try to get from Supabase first
                    article = self._get_article_from_supabase(article_id)
                    
                    # If not in Supabase, try Intercom
                    if not article:
                        article = self.intercom_client.get_article(article_id)
                    
                    if article:
                        articles.append(article)
                    else:
                        raise Exception(f"Article {article_id} not found in Supabase or Intercom")
                except Exception as e:
                    print(f"  [ERROR] Failed to fetch article {article_id}: {e}")
                    self.stats["errors"].append({
                        "article_id": article_id,
                        "error": f"Failed to fetch: {str(e)}"
                    })
        else:
            print("\nFetching articles from Intercom...")
            collection_id = collection_id or INTERCOM_COLLECTION_ID
            tag_id = tag_id or INTERCOM_TAG_ID
            
            articles = self.intercom_client.get_articles(
                collection_id=collection_id,
                tag_id=tag_id
            )
        
        if not articles:
            print("No articles found to translate.")
            return self.stats
        
        print(f"Found {len(articles)} article(s) to translate")
        
        if languages:
            print(f"Target languages: {', '.join([TARGET_LANGUAGES.get(l, l) for l in languages])}")
        else:
            print(f"Target languages: {', '.join(TARGET_LANGUAGES.values())}")
        
        # Process articles
        results = []
        
        # Process in batches to avoid overwhelming the APIs
        for i in range(0, len(articles), TRANSLATION_BATCH_SIZE):
            batch = articles[i:i + TRANSLATION_BATCH_SIZE]
            print(f"\nProcessing batch {i // TRANSLATION_BATCH_SIZE + 1} ({len(batch)} articles)...")
            
            # Process articles sequentially to avoid rate limits
            # (Can be parallelized with proper rate limiting)
            for article in batch:
                try:
                    result = self.process_article(article, languages=languages)
                    results.append(result)
                except Exception as e:
                    error_msg = f"Failed to process article {article.get('id')}: {str(e)}"
                    print(f"  [ERROR] {error_msg}")
                    self.stats["errors"].append({
                        "article_id": article.get("id"),
                        "article_title": article.get("title", "Unknown"),
                        "error": str(e)
                    })
            
            # Delay between batches
            if i + TRANSLATION_BATCH_SIZE < len(articles):
                print(f"\nWaiting before next batch...")
                time.sleep(2)
        
        # Print summary
        print("\n" + "=" * 60)
        print("Workflow Complete!")
        print("=" * 60)
        print(f"Articles processed: {self.stats['articles_processed']}")
        print(f"Translations created/updated: {self.stats['translations_created']}")
        print(f"Errors: {len(self.stats['errors'])}")
        
        if self.stats["errors"]:
            print("\nErrors encountered:")
            for error in self.stats["errors"][:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(self.stats["errors"]) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more errors")
        
        return {
            "stats": self.stats,
            "results": results
        }

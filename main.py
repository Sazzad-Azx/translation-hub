"""
Main entry point for Intercom Translation Workflow
"""
import argparse
import sys
from workflow import TranslationWorkflow
from config import TARGET_LANGUAGES


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Translate Intercom FAQ articles to multiple languages using GPT"
    )
    
    parser.add_argument(
        "--collection-id",
        type=str,
        help="Intercom collection ID to filter articles"
    )
    
    parser.add_argument(
        "--tag-id",
        type=str,
        help="Intercom tag ID to filter articles"
    )
    
    parser.add_argument(
        "--article-ids",
        type=str,
        nargs="+",
        help="Specific article IDs to translate (space-separated)"
    )
    
    parser.add_argument(
        "--languages",
        type=str,
        nargs="+",
        choices=list(TARGET_LANGUAGES.keys()),
        help=f"Specific languages to translate to (choices: {', '.join(TARGET_LANGUAGES.keys())})"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - fetch articles but don't translate or update"
    )
    
    args = parser.parse_args()
    
    # Validate environment variables
    import os
    from config import INTERCOM_ACCESS_TOKEN, OPENAI_API_KEY
    
    if not INTERCOM_ACCESS_TOKEN:
        print("ERROR: INTERCOM_ACCESS_TOKEN environment variable is not set")
        sys.exit(1)
    
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY environment variable is not set")
        sys.exit(1)
    
    # Run workflow
    try:
        workflow = TranslationWorkflow()
        
        if args.dry_run:
            print("DRY RUN MODE - No translations will be performed")
            # Just fetch and display articles
            from intercom_client import IntercomClient
            client = IntercomClient()
            articles = client.get_articles(
                collection_id=args.collection_id,
                tag_id=args.tag_id
            )
            print(f"\nFound {len(articles)} article(s):")
            for article in articles:
                print(f"  - {article.get('title')} (ID: {article.get('id')})")
        else:
            workflow.run(
                collection_id=args.collection_id,
                tag_id=args.tag_id,
                article_ids=args.article_ids,
                languages=args.languages
            )
    
    except KeyboardInterrupt:
        print("\n\nWorkflow interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

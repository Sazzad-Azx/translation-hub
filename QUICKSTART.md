# Quick Start Guide

## Setup (5 minutes)

1. **Install dependencies:**
```bash
cd intercom-translator
pip install -r requirements.txt
```

2. **Configure API keys:**

The API keys have been provided:
- **Intercom API Key**: `your_intercom_access_token_here`
- **OpenAI API Key**: `your_openai_api_key_here`

**Create a `.env` file** in the `intercom-translator` directory:

```env
INTERCOM_ACCESS_TOKEN=your_intercom_access_token_here
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o
```

Or run the setup script:
```bash
python setup_env.py
```

## Usage

### Test the connection (Dry Run)
First, test that everything works without making changes:

```bash
python main.py --dry-run
```

This will:
- Connect to Intercom
- Fetch articles
- Display what would be translated
- **No translations or updates will be made**

### Translate All Articles

Translate all articles in your Intercom Help Center to all 11 languages:

```bash
python main.py
```

### Translate Specific Articles

Translate only specific articles by ID:

```bash
python main.py --article-ids ARTICLE_ID_1 ARTICLE_ID_2
```

### Translate to Specific Languages

Translate only to French, German, and Spanish:

```bash
python main.py --languages fr de es
```

### Filter by Collection

Translate articles from a specific collection:

```bash
python main.py --collection-id YOUR_COLLECTION_ID
```

## What Gets Translated

For each article, the system translates:
- **Title** - Article title
- **Body** - Article content (preserves HTML/formatting)
- **Description** - Article description (if present)

## Target Languages

The system translates to these 11 languages:
1. Arabic (UAE) - `ar`
2. Chinese - Simplified - `zh-CN`
3. French - `fr`
4. German - `de`
5. Hindi - `hi`
6. Italian - `it`
7. Japanese - `ja`
8. Persian - `fa`
9. Spanish - `es`
10. Thai - `th`
11. Portuguese - Brazil - `pt-BR`

## Troubleshooting

### "INTERCOM_ACCESS_TOKEN environment variable is not set"
- Make sure you created the `.env` file
- Or set the environment variable: `$env:INTERCOM_ACCESS_TOKEN="your_token"` (PowerShell)

### "OpenAI API key is required"
- Check your `.env` file has `OPENAI_API_KEY` set
- Verify the API key is correct

### API Errors
- Check that your Intercom token has the right permissions
- Verify the API endpoints are accessible
- Check Intercom API documentation for any changes

### Rate Limiting
- The system handles rate limits automatically
- If you see many rate limit errors, increase `RETRY_DELAY` in `config.py`

## Next Steps

1. Run a dry-run to verify setup
2. Test with 1-2 articles first: `python main.py --article-ids ARTICLE_ID`
3. Once verified, run on all articles: `python main.py`

## Support

Check the main `README.md` for detailed documentation.

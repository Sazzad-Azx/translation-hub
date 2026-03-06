# Intercom Translation Workflow

A Python-based workflow system that automatically translates Intercom FAQ articles to multiple languages using GPT language models.

## Features

- **Pull Articles**: Fetches articles from Intercom Help Center
- **GPT Translation**: Uses OpenAI GPT models to translate content to 11 target languages
- **Update Intercom**: Automatically creates/updates translations in Intercom
- **Batch Processing**: Handles multiple articles efficiently
- **Error Handling**: Robust error handling and retry logic
- **Rate Limiting**: Built-in rate limit handling for API calls

## Target Languages

The system translates to the following 11 languages (from English):

1. Arabic (UAE) - `ar`
2. Chinese - Simplified - `zh-CN`
3. French - `fr`
4. German - `de`
5. Hindi - `hi`
6. Italian - `it`
7. Japanese - Japan - `ja`
8. Persian - `fa`
9. Spanish - `es`
10. Thai - `th`
11. Portuguese - Brazil - `pt-BR`

## Prerequisites

- Python 3.8 or higher
- Intercom API access token
- OpenAI API key

## Installation

1. Clone or navigate to the project directory:
```bash
cd intercom-translator
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:

**Option 1: Use the setup script (recommended)**
```bash
python setup_env.py
```

**Option 2: Create .env file manually**
Create a `.env` file in the `intercom-translator` directory with:
```env
INTERCOM_ACCESS_TOKEN=your_intercom_access_token_here
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o
```

**Option 3: Set environment variables directly**
```bash
# Windows PowerShell
$env:INTERCOM_ACCESS_TOKEN="your_intercom_access_token_here"
$env:OPENAI_API_KEY="your_openai_api_key_here"

# Linux/Mac
export INTERCOM_ACCESS_TOKEN="your_intercom_access_token_here"
export OPENAI_API_KEY="your_openai_api_key_here"
```

## Usage

### Basic Usage

Translate all articles in your Intercom Help Center:

```bash
python main.py
```

### Filter by Collection

Translate articles from a specific collection:

```bash
python main.py --collection-id YOUR_COLLECTION_ID
```

### Filter by Tag

Translate articles with a specific tag:

```bash
python main.py --tag-id YOUR_TAG_ID
```

### Translate Specific Articles

Translate specific articles by ID:

```bash
python main.py --article-ids ARTICLE_ID_1 ARTICLE_ID_2 ARTICLE_ID_3
```

### Translate to Specific Languages

Translate only to specific languages:

```bash
python main.py --languages fr de es
```

### Dry Run

Test the workflow without making changes:

```bash
python main.py --dry-run
```

### Combined Options

```bash
python main.py --collection-id COLLECTION_ID --languages fr de es
```

## Configuration

Edit `config.py` to customize:

- **TARGET_LANGUAGES**: Add or remove target languages
- **OPENAI_MODEL**: Change the GPT model (default: `gpt-4o`)
- **TRANSLATION_BATCH_SIZE**: Adjust batch processing size
- **MAX_RETRIES**: Configure retry attempts
- **RETRY_DELAY**: Set delay between retries

## How It Works

1. **Pull Articles**: The workflow fetches articles from Intercom Help Center API
2. **Translate**: Each article is translated to all target languages using GPT
3. **Update**: Translations are created or updated in Intercom via API

The workflow processes articles sequentially to avoid rate limits and includes:
- Automatic retry logic for failed requests
- Rate limit handling (429 responses)
- Progress tracking and error reporting
- Translation quality optimized for help center content

## API Requirements

### Intercom API

You need an Intercom access token with permissions to:
- Read articles
- Create/update article translations
- Publish articles (optional)

Get your token from: Intercom Settings > Developers > Developer Hub > Authentication

### OpenAI API

You need an OpenAI API key with access to GPT models.

Get your key from: https://platform.openai.com/api-keys

## Error Handling

The system includes comprehensive error handling:
- Failed translations are logged but don't stop the workflow
- Rate limits are automatically handled with retries
- Network errors are retried with exponential backoff
- All errors are reported in the final summary

## Output

The workflow provides:
- Real-time progress updates
- Success/failure status for each translation
- Final statistics summary
- Error report for any failures

## Limitations

- Rate limits: Both Intercom and OpenAI APIs have rate limits. The workflow includes delays to respect these limits.
- Cost: GPT API calls incur costs. Monitor your OpenAI usage.
- Article size: Very large articles may need to be split or processed differently.

## API testing with curl

Run the Flask server first (`python app.py` or `flask run`), then use these commands to verify the API. All responses are JSON (errors never return HTML).

**Health check (GET):**
```bash
curl -i http://127.0.0.1:5000/api/health
```
Expected: `200 OK` and body `{"ok":true}`.

**List saved translations (GET):**
```bash
curl -i http://127.0.0.1:5000/api/article-translations
```
Expected: `200 OK` and JSON with `success`, `translations`, `count`.

**Save a translation (POST):**
```bash
curl -i -X POST http://127.0.0.1:5000/api/article-translations \
  -H "Content-Type: application/json" \
  -d "{\"parent_intercom_article_id\":\"12345\",\"target_locale\":\"ar\",\"translated_title\":\"Test Title\",\"translated_body_html\":\"<p>Test body</p>\",\"status\":\"draft\",\"source_locale\":\"en\"}"
```
Expected: `200 OK` and JSON with `success: true`, `translation`, `message`. Requires Supabase `article_translations` table and env configured.

**Windows PowerShell** (same POST, one line):
```powershell
curl -i -X POST http://127.0.0.1:5000/api/article-translations -H "Content-Type: application/json" -d "{\"parent_intercom_article_id\":\"12345\",\"target_locale\":\"ar\",\"translated_title\":\"Test Title\",\"translated_body_html\":\"<p>Test body</p>\",\"status\":\"draft\",\"source_locale\":\"en\"}"
```

Server logs every request as `METHOD /path` (e.g. `POST /api/article-translations`) so you can confirm the route is hit.

## Troubleshooting

### "INTERCOM_ACCESS_TOKEN environment variable is not set"
- Set the environment variable or add it to `.env` file

### "OpenAI API key is required"
- Set the `OPENAI_API_KEY` environment variable

### Rate limit errors
- The workflow handles rate limits automatically, but you may need to increase delays in `config.py`

### Translation quality issues
- Try using a different GPT model (e.g., `gpt-4-turbo`)
- Adjust the temperature in `translator.py` (currently 0.3)
- Review and refine the system prompt in `translator.py`

## License

This project is provided as-is for internal use.

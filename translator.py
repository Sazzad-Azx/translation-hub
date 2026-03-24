"""
GPT-based translation service

Uses a chunk-based approach for HTML body translation: the body is split into
individual block-level elements, each is translated in a single GPT call as a
JSON array, and the results are reassembled.  This guarantees the original HTML
structure (paragraph breaks, headings, spacing) is preserved exactly.
"""
import json
import re
from openai import OpenAI
from typing import Dict, List, Optional
from config import OPENAI_API_KEY, OPENAI_MODEL, TARGET_LANGUAGES

# Block-level tags that act as chunk boundaries
_BLOCK_RE = re.compile(
    r'(</?(?:p|h[1-6]|div|ul|ol|li|table|tr|td|th|thead|tbody|blockquote|figure|figcaption|section|article|header|footer|nav|aside|details|summary|pre|hr|br\s*/?)(?:\s[^>]*)?>)',
    re.IGNORECASE,
)

# Max chunks per GPT call (to stay within token limits)
_MAX_CHUNKS_PER_CALL = 60


def _split_into_chunks(html: str) -> List[str]:
    """
    Split HTML into translatable chunks at block-level tag boundaries.
    Each chunk is either a block tag itself or the content between block tags.
    Adjacent chunks are grouped so that each entry is one complete block element
    (e.g. '<p>some text</p>').
    """
    if not html or not html.strip():
        return [html or ""]

    parts = _BLOCK_RE.split(html)
    # Recombine into logical blocks: merge sequences into complete elements
    # Simple approach: just return the raw parts, keeping empties for structure
    chunks = []
    current = ""
    for part in parts:
        current += part
        # If we just closed a block tag, flush
        if re.search(r'</(?:p|h[1-6]|div|ul|ol|li|table|tr|td|th|thead|tbody|blockquote|figure|figcaption|section|article|header|footer|nav|aside|details|summary|pre)>', part, re.IGNORECASE):
            chunks.append(current)
            current = ""
        # Self-closing / void block tags (hr, br) also flush
        elif re.search(r'<(?:hr|br)\s*/?>$', part, re.IGNORECASE):
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)

    return chunks if chunks else [html]


def _is_translatable(chunk: str) -> bool:
    """Check if a chunk has visible text worth translating."""
    text = re.sub(r'<[^>]+>', '', chunk).strip()
    # Skip empty, whitespace-only, or purely numeric/symbolic chunks
    return len(text) > 0 and not re.match(r'^[\s\d\W]*$', text)


def _clean_gpt_response(text: str, is_html: bool = True) -> str:
    """Strip markdown code fences and (for plain text) any HTML tags."""
    if not text:
        return text
    text = re.sub(r'^```(?:html|json)?\s*\n?', '', text.strip())
    text = re.sub(r'\n?```\s*$', '', text.strip())
    if not is_html:
        text = re.sub(r'<[^>]+>', '', text).strip()
    return text


class GPTTranslator:
    """Translation service using OpenAI GPT models"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.model = model or OPENAI_MODEL
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    # ------------------------------------------------------------------
    # Low-level: translate a single plain-text or HTML snippet
    # ------------------------------------------------------------------

    def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str = "en",
        context: Optional[str] = None,
        glossary_prompt: str = "",
        is_html: bool = True
    ) -> str:
        if not self.client:
            raise ValueError("OpenAI API key is required for translation. Set OPENAI_API_KEY environment variable.")
        language_name = TARGET_LANGUAGES.get(target_language, target_language)

        if is_html:
            system_prompt = f"""You are a professional translator specializing in help center and FAQ content.
Translate the following text from {source_language} to {language_name} ({target_language}).

CRITICAL HTML RULES — you MUST follow these exactly:
- The input is HTML. Your output MUST be valid HTML with the EXACT same tag structure.
- Preserve EVERY HTML tag exactly as it appears.
- Do NOT merge, remove, or rearrange any HTML tags.
- Preserve ALL spacing elements: empty paragraphs, line breaks, whitespace-only tags.
- Only translate the visible text content between tags. Never translate attribute values.
- Maintain the original tone appropriate for help center documentation.
- Do NOT wrap output in markdown code fences. Return raw HTML only.
"""
        else:
            system_prompt = f"""You are a professional translator specializing in help center and FAQ content.
Translate the following text from {source_language} to {language_name} ({target_language}).

RULES:
- This is plain text (NOT HTML). Return only the translated plain text.
- Do NOT wrap the output in any HTML tags such as <p>, <div>, <span>, etc.
- Maintain the original tone appropriate for help center documentation.
"""

        if context:
            system_prompt += f"\nContext: {context}"
        if glossary_prompt:
            system_prompt += f"\n\n{glossary_prompt}"

        user_prompt = f"Translate the following text to {language_name}:\n\n{text}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=16000
            )
            translated_text = response.choices[0].message.content.strip()
            return _clean_gpt_response(translated_text, is_html)
        except Exception as e:
            raise Exception(f"Translation failed: {str(e)}")

    # ------------------------------------------------------------------
    # Batch: translate a list of HTML chunks in one GPT call via JSON
    # ------------------------------------------------------------------

    def _translate_chunks_batch(
        self,
        chunks: List[str],
        target_language: str,
        source_language: str = "en",
        context: Optional[str] = None,
        glossary_prompt: str = "",
    ) -> List[str]:
        """Translate multiple HTML chunks in a single GPT call using JSON I/O."""
        if not self.client:
            raise ValueError("OpenAI API key is required.")
        language_name = TARGET_LANGUAGES.get(target_language, target_language)

        system_prompt = f"""You are a professional translator for help center content.
Translate from {source_language} to {language_name} ({target_language}).

INPUT: A JSON array of HTML snippets.
OUTPUT: A JSON array of the same length with each snippet translated.

RULES:
- Return ONLY a valid JSON array. No markdown, no commentary.
- Each element in the output array corresponds to the same-index element in the input.
- Preserve ALL HTML tags, attributes, and structure exactly. Only translate visible text.
- Do NOT merge, split, add, or remove any HTML elements.
- Elements that are only tags with no visible text (e.g. "<br>", "<p><br></p>") must be returned unchanged.
- Maintain the original tone appropriate for help center documentation.
"""
        if context:
            system_prompt += f"\nContext: {context}"
        if glossary_prompt:
            system_prompt += f"\n\n{glossary_prompt}"

        user_prompt = json.dumps(chunks, ensure_ascii=False)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=16000,
            )
            raw = response.choices[0].message.content.strip()
            raw = _clean_gpt_response(raw, is_html=True)

            # Parse JSON array from response
            result = json.loads(raw)
            if isinstance(result, list) and len(result) == len(chunks):
                return result

            # Length mismatch — fall back to one-by-one
            print(f"  [WARN] Chunk batch returned {len(result)} items, expected {len(chunks)}. Falling back.", flush=True)
            return self._translate_chunks_individually(chunks, target_language, source_language, context, glossary_prompt)

        except (json.JSONDecodeError, Exception) as e:
            print(f"  [WARN] Batch translation failed ({e}). Falling back to individual.", flush=True)
            return self._translate_chunks_individually(chunks, target_language, source_language, context, glossary_prompt)

    def _translate_chunks_individually(
        self,
        chunks: List[str],
        target_language: str,
        source_language: str = "en",
        context: Optional[str] = None,
        glossary_prompt: str = "",
    ) -> List[str]:
        """Fallback: translate each chunk one at a time."""
        results = []
        for chunk in chunks:
            if _is_translatable(chunk):
                results.append(self.translate_text(chunk, target_language, source_language, context, glossary_prompt, is_html=True))
            else:
                results.append(chunk)
        return results

    # ------------------------------------------------------------------
    # High-level: translate an HTML body preserving structure
    # ------------------------------------------------------------------

    def translate_body(
        self,
        body: str,
        target_language: str,
        source_language: str = "en",
        context: Optional[str] = None,
        glossary_prompt: str = "",
    ) -> str:
        """
        Translate an HTML body while guaranteeing structural preservation.
        Splits into block-level chunks, translates via batched JSON, reassembles.
        """
        if not body or not body.strip():
            return body

        chunks = _split_into_chunks(body)

        # Separate translatable vs non-translatable (keep indices)
        translatable_indices = []
        translatable_chunks = []
        for i, chunk in enumerate(chunks):
            if _is_translatable(chunk):
                translatable_indices.append(i)
                translatable_chunks.append(chunk)

        if not translatable_chunks:
            return body

        # Translate in batches
        translated_chunks = []
        for batch_start in range(0, len(translatable_chunks), _MAX_CHUNKS_PER_CALL):
            batch = translatable_chunks[batch_start:batch_start + _MAX_CHUNKS_PER_CALL]
            translated_batch = self._translate_chunks_batch(
                batch, target_language, source_language, context, glossary_prompt
            )
            translated_chunks.extend(translated_batch)

        # Reassemble: replace translatable chunks with translated versions
        result = list(chunks)
        for idx, trans_idx in enumerate(translatable_indices):
            if idx < len(translated_chunks):
                result[trans_idx] = translated_chunks[idx]

        return "".join(result)

    # ------------------------------------------------------------------
    # Public: translate a full article
    # ------------------------------------------------------------------

    def translate_article(
        self,
        article: Dict,
        target_language: str,
        source_language: str = "en",
        glossary_prompt: str = ""
    ) -> Dict[str, str]:
        title = article.get("title", "")
        body = article.get("body", "")
        description = article.get("description", "")

        context = "FAQ article for help center"

        translated = {
            "title": self.translate_text(title, target_language, source_language, context, glossary_prompt, is_html=False),
            "body": self.translate_body(body, target_language, source_language, context, glossary_prompt),
        }

        if description:
            translated["description"] = self.translate_text(
                description, target_language, source_language, context, glossary_prompt, is_html=False
            )

        return translated

"""
GPT-based translation service
"""
from openai import OpenAI
from typing import Dict, Optional
from config import OPENAI_API_KEY, OPENAI_MODEL, TARGET_LANGUAGES


class GPTTranslator:
    """Translation service using OpenAI GPT models"""
    
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.model = model or OPENAI_MODEL
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
    
    def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str = "en",
        context: Optional[str] = None,
        glossary_prompt: str = ""
    ) -> str:
        """
        Translate text using GPT model
        
        Args:
            text: Text to translate
            target_language: Target language code
            source_language: Source language code (default: 'en')
            context: Optional context about the content (e.g., "FAQ article", "help center")
            glossary_prompt: Optional glossary constraint section to enforce terminology
            
        Returns:
            Translated text
        """
        if not self.client:
            raise ValueError("OpenAI API key is required for translation. Set OPENAI_API_KEY environment variable.")
        language_name = TARGET_LANGUAGES.get(target_language, target_language)
        
        system_prompt = f"""You are a professional translator specializing in help center and FAQ content.
Translate the following text from {source_language} to {language_name} ({target_language}).

CRITICAL HTML RULES — you MUST follow these exactly:
- The input is HTML. Your output MUST be valid HTML with the EXACT same tag structure.
- Preserve EVERY HTML tag exactly as it appears: <h1>, <h2>, <h3>, <p>, <ul>, <ol>, <li>, <table>, <tr>, <td>, <th>, <div>, <span>, <blockquote>, <b>, <strong>, <i>, <em>, <a>, <br>, <img>, etc.
- Do NOT merge, remove, or rearrange any HTML tags. Every opening and closing tag in the source must appear in the translation.
- Do NOT merge a heading tag into the preceding paragraph. Headings (<h1>, <h2>, <h3>, etc.) must remain as separate block elements.
- Only translate the visible text content between tags. Never translate attribute values (href, src, class, id, style, etc.).
- Maintain the original tone and ensure the translation is natural and appropriate for help center documentation.
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
                temperature=0.3,  # Lower temperature for more consistent translations
                max_tokens=16000  # Large enough to handle full article translations without truncation
            )
            
            translated_text = response.choices[0].message.content.strip()
            return translated_text
            
        except Exception as e:
            raise Exception(f"Translation failed: {str(e)}")
    
    def translate_article(
        self,
        article: Dict,
        target_language: str,
        source_language: str = "en",
        glossary_prompt: str = ""
    ) -> Dict[str, str]:
        """
        Translate an article (title, body, and optionally description)
        
        Args:
            article: Article dictionary with title, body, etc.
            target_language: Target language code
            source_language: Source language code (default: 'en')
            glossary_prompt: Optional glossary constraint section to enforce terminology
            
        Returns:
            Dictionary with translated title, body, and description
        """
        title = article.get("title", "")
        body = article.get("body", "")
        description = article.get("description", "")
        
        context = "FAQ article for help center"
        
        translated = {
            "title": self.translate_text(title, target_language, source_language, context, glossary_prompt),
            "body": self.translate_text(body, target_language, source_language, context, glossary_prompt)
        }
        
        if description:
            translated["description"] = self.translate_text(
                description, target_language, source_language, context, glossary_prompt
            )
        
        return translated

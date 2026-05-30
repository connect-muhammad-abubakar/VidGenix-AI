import json
import logging
import re
from typing import List
from loguru import logger
from openai import OpenAI
from app.config import config

# Import the new Google GenAI SDK
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

# Global Constants
_max_retries = 3
_DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
_DEPRECATED_GEMINI_MODELS = ["gemini-pro", "gemini-1.0-pro", "gemini-pro-vision"]

def _normalize_text_response(content, llm_provider: str) -> str:
    if content is None:
        raise ValueError(f"[{llm_provider}] returned empty text content")
    content = str(content).strip()
    return content.replace("\n", " ")

def _generate_response(prompt: str) -> str:
    llm_provider = config.app.get("llm_provider", "gemini")
    
    if llm_provider == "gemini":
        api_key = config.app.get("gemini_api_key")
        model_name = config.app.get("gemini_model_name")
        
        if not api_key:
            raise ValueError("Gemini API key is missing in config.toml")
        if not genai:
            raise ImportError("google-genai package not found. Run: pip install google-genai")

        if not model_name or any(m in model_name for m in _DEPRECATED_GEMINI_MODELS):
            model_name = _DEFAULT_GEMINI_MODEL

        client = genai.Client(api_key=api_key)
        
        # Safety settings to prevent content filtering from stopping generation
        safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        ]

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(safety_settings=safety_settings)
            )
            return _normalize_text_response(response.text, llm_provider)
        except Exception as e:
            logger.error(f"Gemini API Error: {str(e)}")
            raise e
    else:
        api_key = config.app.get(f"{llm_provider}_api_key")
        base_url = config.app.get(f"{llm_provider}_base_url", "")
        model_name = config.app.get(f"{llm_provider}_model_name", "")
        
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_name, 
            messages=[{"role": "user", "content": prompt}]
        )
        return _normalize_text_response(response.choices[0].message.content, llm_provider)

def generate_script(video_subject: str, language: str = "", paragraph_number: int = 1) -> str:
    prompt = f"Write a video script about '{video_subject}' in {language}. It should be {paragraph_number} paragraphs long. Do not include any intro/outro or markdown formatting, just the spoken text."
    for i in range(_max_retries):
        try:
            script = _generate_response(prompt)
            if script: 
                return script
        except Exception as e:
            logger.error(f"Script generation attempt {i+1} failed: {e}")
    return ""

def generate_terms(video_subject: str, video_script: str, amount: int = 5) -> List[str]:
    prompt = f"Based on this script: '{video_script}', generate {amount} search terms for stock footage in English. Return ONLY a JSON list of strings, like [\"term1\", \"term2\"]."
    
    for i in range(_max_retries):
        try:
            response = _generate_response(prompt)
            # Enhanced regex to catch JSON even if wrapped in ```json blocks
            match = re.search(r"\[\s*\".*?\"\s*\]", response, re.DOTALL)
            if match:
                terms = json.loads(match.group())
                if isinstance(terms, list) and len(terms) > 0:
                    return terms
        except Exception as e:
            logger.warning(f"Terms generation attempt {i+1} failed: {e}")
            
    # CRITICAL FALLBACK: If AI fails, provide generic terms so the video still generates
    logger.warning("All term generation attempts failed. Using fallback terms.")
    return ["technology", "innovation", "digital", "workspace", "creativity"]

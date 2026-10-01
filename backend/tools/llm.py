"""
Unified Gemini LLM Client.

Strictly follows the required Gemini model hierarchy:
1. Gemini 2.5 Pro (Preferred)
2. Gemini 2.5 Flash
3. Gemini 2.0 Pro
4. Gemini 2.0 Flash
5. Gemini 1.5 Pro
(followed by active latest Gemini release aliases)

Never uses Qwen. If no Gemini model is reachable, raises RuntimeError to stop execution.
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional
import requests
from dotenv import load_dotenv

# Load environment variables
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

logger = logging.getLogger(__name__)

# Ordered priority list of Gemini models
GEMINI_MODELS_DIRECT: List[str] = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-pro",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-flash-latest",
    "gemini-pro-latest",
]

GEMINI_MODELS_OPENROUTER: List[str] = [
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-001",
    "google/gemini-2.0-pro-exp-02-05:free",
]


class LLM:
    """
    Interface for Google Gemini models adhering strictly to model priority:
    Gemini 2.5 Pro > Gemini 2.5 Flash > Gemini 2.0 Pro > Gemini 2.0 Flash > Gemini 1.5 Pro.
    """

    @classmethod
    def _call_gemini_direct(cls, model_name: str, prompt: str, system: str, api_key: str) -> Optional[str]:
        """Calls Google Generative Language REST API directly."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        body: dict = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
            },
        }
        if system:
            body["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(url, headers=headers, json=body, timeout=25)
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text_parts = [p.get("text", "") for p in parts if p.get("text")]
                    if text_parts:
                        return "\n".join(text_parts).strip()
            else:
                logger.debug("Gemini direct [%s] HTTP %s: %s", model_name, response.status_code, response.text[:200])
        except Exception as exc:
            logger.debug("Gemini direct [%s] error: %s", model_name, exc)
        return None

    @classmethod
    def _call_gemini_openrouter(cls, model_name: str, prompt: str, system: str, api_key: str) -> Optional[str]:
        """Calls OpenRouter with Gemini model target and explicit token limit."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "AI Job Agent",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": 2500,
            "temperature": 0.2,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
            else:
                logger.debug("OpenRouter [%s] HTTP %s: %s", model_name, response.status_code, response.text[:200])
        except Exception as exc:
            logger.debug("OpenRouter [%s] error: %s", model_name, exc)
        return None

    @classmethod
    def generate(cls, prompt: str, system: str = "") -> str:
        """
        Generates text using the highest available Gemini model in sequence.
        Raises RuntimeError if no Gemini model is available.
        Never switches to Qwen.
        """
        gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        # 1. Attempt official Google Gemini API in strict priority
        if gemini_api_key:
            for model in GEMINI_MODELS_DIRECT:
                result = cls._call_gemini_direct(model, prompt, system, gemini_api_key)
                if result:
                    logger.info("Successfully generated response using direct %s", model)
                    return result

        # 2. Attempt OpenRouter Gemini models in strict priority
        if openrouter_api_key:
            for model in GEMINI_MODELS_OPENROUTER:
                result = cls._call_gemini_openrouter(model, prompt, system, openrouter_api_key)
                if result:
                    logger.info("Successfully generated response using OpenRouter %s", model)
                    return result

        # If no Gemini model succeeded, stop and raise error per model requirement
        raise RuntimeError(
            "No Gemini model is available. Please add GEMINI_API_KEY to backend/.env "
            "(get one free from https://aistudio.google.com/) or verify your OpenRouter balance. "
            "Execution halted in accordance with the Gemini-only requirement."
        )

import json
from typing import Any, Dict

from tools.llm import LLM


class OllamaService:
    """
    Service wrapper maintained for backwards compatibility.
    Strictly delegates all generation to LLM (Gemini hierarchy: 2.5 Pro > 2.5 Flash > 2.0 Pro > 2.0 Flash > 1.5 Pro).
    Never uses Qwen.
    """

    @staticmethod
    def extract_profile(resume_text: str) -> Dict[str, Any]:
        prompt = f"""
Extract information from the following resume.

Return ONLY valid JSON in exactly this format:

{{
    "name": "",
    "email": "",
    "phone": "",
    "linkedin": "",
    "github": "",
    "skills": [],
    "experience": [],
    "education": [],
    "projects": [],
    "summary": ""
}}

Resume:

{resume_text}
"""
        output = LLM.generate(prompt)

        if output.startswith("```json"):
            output = output[7:]
        if output.startswith("```"):
            output = output[3:]
        if output.endswith("```"):
            output = output[:-3]

        return json.loads(output.strip())

    @staticmethod
    def generate(prompt: str) -> str:
        return LLM.generate(prompt)
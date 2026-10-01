import json

from services.ollama_service import OllamaService


class Planner:

    @staticmethod
    def run(goal: str):

        prompt = f"""
You are an AI Planning Agent.

The user goal is:

{goal}

Create a short execution plan.

Return ONLY valid JSON.

Example:

[
    "Search remote jobs",
    "Analyze job descriptions",
    "Match resume",
    "Generate application email"
]
"""

        try:

            response = OllamaService.generate(prompt)

            if response.startswith("```json"):
                response = response[7:]

            if response.startswith("```"):
                response = response[3:]

            if response.endswith("```"):
                response = response[:-3]

            return json.loads(response.strip())

        except Exception:

            return [
                "Search jobs",
                "Match resume",
                "Generate email"
            ]
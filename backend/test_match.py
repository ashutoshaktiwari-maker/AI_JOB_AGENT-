from match_agent import analyze_match

resume = {
    "skills": ["Python","FastAPI","RAG","SQL"]
}

job = """
Looking for Python developer with FastAPI,
Docker,
AWS,
LLM,
SQL.
"""

print(analyze_match(resume, job))
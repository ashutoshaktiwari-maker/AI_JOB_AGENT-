from pathlib import Path
from services.cover_letter_generator import CoverLetterGenerator

profile_file = Path("data/profile.json")

target_jd = """
Role: AI Solutions Architect
Company: Nexus Innovations
Requirements:
- Proven experience designing and implementing end-to-end automation workflows.
- Expertise with Python, REST API integrations, and workflow platforms (n8n, Make).
- Practical experience deploying AI agents and LLM-powered applications.
- Strong communication and business analysis capabilities.
"""

print(f"Candidate profile exists: {profile_file.exists()}")
result = CoverLetterGenerator.generate(
    resume=str(profile_file),
    job_description=target_jd,
    company_name="Nexus Innovations",
    role_title="AI Solutions Architect",
    save_path="data/cover_letter.txt"
)

print("\n--- COVER LETTER GENERATION STATUS ---")
print("Mode:", result.get("mode"))
print("Target Company:", result.get("company_name"))
print("Target Role:", result.get("role_title"))
print("Saved to:", result.get("save_path"))

print("\n--- COVER LETTER SNIPPET ---")
text = result.get("cover_letter_text", "")
print(text[:700] + ("..." if len(text) > 700 else ""))

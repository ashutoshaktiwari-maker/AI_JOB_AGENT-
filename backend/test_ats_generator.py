from pathlib import Path
from services.resume_generator import ATSResumeGenerator

profile_file = Path("data/profile.json")

target_jd = """
Role: Senior AI Automation Engineer
Company: CloudScale AI
Requirements:
- Strong experience with Python and REST APIs
- Hands-on expertise building AI Agents and LLM-powered automation workflows
- Experience with workflow orchestration platforms (n8n, Make.com)
- Proven ability to automate business operations and integrate third-party APIs
- Knowledge of prompt engineering and LLM integrations
"""

print(f"Loading candidate profile: {profile_file.exists()}")
result = ATSResumeGenerator.generate_tailored_resume(
    resume=str(profile_file),
    job_description=target_jd
)

print("\n--- GENERATION STATUS ---")
print("Mode:", result.get("mode"))
print("Emphasized Skills:", result.get("emphasized_skills"))
print("\n--- TAILORED ATS RESUME SNIPPET ---")
text = result.get("tailored_resume_text", "")
print(text[:600] + ("..." if len(text) > 600 else ""))

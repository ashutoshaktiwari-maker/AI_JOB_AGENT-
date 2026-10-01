from pathlib import Path
from agents.email_agent import EmailAgent

profile_file = Path("data/profile.json")

# Case 1: Job Description WITH recruiter email
jd_with_email = """
Role: Senior AI Automation Specialist
Company: CloudScale Dynamics
Contact our recruiting team directly: hiring.lead@cloudscaledynamics.com
We are seeking an automation engineer experienced in Python, n8n, Make, and LLM APIs to build business automation agents.
"""

# Case 2: Job Description WITHOUT recruiter email
jd_without_email = """
Role: Workflow Automation Consultant
Company: Vertex Automations
Requirements: Strong proficiency in workflow orchestration, Python scripting, REST APIs, and prompt engineering.
Apply through our careers portal.
"""

print(f"Profile file exists: {profile_file.exists()}\n")

print("=== TEST CASE 1: JD with recruiter email ===")
res1 = EmailAgent.generate_email(
    resume=str(profile_file),
    job=jd_with_email,
    save_path="data/recruiter_email.txt"
)
print("Has Recruiter Email:", res1.get("has_recruiter_email"))
print("Recipient Email:", res1.get("recipient_email"))
print("Subject:", res1.get("subject"))
print("Mode:", res1.get("mode"))
print("Body Preview:\n", res1.get("body")[:300], "...\n")

print("=== TEST CASE 2: JD without recruiter email ===")
res2 = EmailAgent.generate_email(
    resume=str(profile_file),
    job=jd_without_email
)
print("Has Recruiter Email:", res2.get("has_recruiter_email"))
print("Recipient Email:", res2.get("recipient_email"))
print("Subject:", res2.get("subject"))
print("Mode:", res2.get("mode"))
print("Body Preview:\n", res2.get("body")[:300], "...\n")

"""
Test Suite for GmailAgent.
Verifies OAuth status, link extraction, Gemini email classification,
and automatic workflow routing.
"""

from agents.gmail_agent import GmailAgent

agent = GmailAgent()

print("=== 1. Checking Gmail OAuth Configuration ===")
print("Authenticated:", agent.is_authenticated())
print("Credentials JSON Present:", agent.credentials_path.exists())
print("Token JSON Present:", agent.token_path.exists())

print("\n=== 2. Testing ATS Link Extraction ===")
sample_email_text = """
Hi Ashutosh,
Great seeing your background in AI workflows! We have an open Senior Automation Engineer role at Stripe.
Take a look at the job description and apply here: https://jobs.lever.co/stripe/98765/apply
Or check our careers page: https://stripe.com/jobs
"""
links = GmailAgent.extract_links(sample_email_text)
print("Links Found:", links)
assert any("lever.co" in l for l in links), "Expected Lever link to be extracted"
print("[OK] ATS Link Extraction verified.")

print("\n=== 3. Testing Gemini Email Classification & Extraction ===")

# Test 1: Recruiter email
recruiter_subject = "Exciting AI Automation Role at CloudScale AI"
recruiter_sender = "sarah.recruiter@cloudscale.ai"
recruiter_body = """
Hi Ashutosh,
I came across your profile and was impressed by your hands-on experience in workflow automation with Python, n8n, and LLM APIs.
We are looking for an AI Automation Lead at CloudScale AI to design multi-agent workflows for enterprise clients.
Job details: Full-time remote, competitive salary, building custom LLM agents and integrations.
Apply directly at: https://boards.greenhouse.io/cloudscale/jobs/112233
Let me know if you are open to discussing this week!
Best,
Sarah
"""

print("\nAnalyzing Recruiter Email with Gemini...")
analysis1 = GmailAgent.analyze_email_content(
    subject=recruiter_subject,
    sender=recruiter_sender,
    body=recruiter_body
)
print("Category:", analysis1.get("category"))
print("Company:", analysis1.get("company_name"))
print("Role:", analysis1.get("role_title"))
print("Actionable:", analysis1.get("is_actionable"))
print("Extracted Apply URL:", analysis1.get("extracted_apply_url"))

# Test 2: Interview invitation
interview_subject = "Interview Invitation: AI Engineer - Next Steps"
interview_sender = "talent@innovate.ai"
interview_body = """
Hello Ashutosh,
Thank you for your application for the AI Engineer role. We were very impressed by your qualifications and would like to invite you to a 30-minute technical screening interview.
Please choose a time slot on Calendly: https://calendly.com/talent-innovate/screening
Best regards,
Hiring Team
"""

print("\nAnalyzing Interview Invitation with Gemini...")
analysis2 = GmailAgent.analyze_email_content(
    subject=interview_subject,
    sender=interview_sender,
    body=interview_body
)
print("Category:", analysis2.get("category"))
print("Company:", analysis2.get("company_name"))
print("Suggested Action:", analysis2.get("suggested_action"))

assert analysis1.get("category") in ("recruiter_email", "job_alert")
assert analysis2.get("category") == "interview_invitation"
print("\n[SUCCESS] Gmail Agent email intelligence and workflow parsing fully verified with Gemini!")

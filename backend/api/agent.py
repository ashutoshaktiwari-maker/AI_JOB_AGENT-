from fastapi import APIRouter
from pydantic import BaseModel

from agents.orchestrator import Orchestrator

router = APIRouter(
    prefix="/agent",
    tags=["Agent"],
)


class AgentRequest(BaseModel):
    goal: str


@router.post("/run")
async def run_agent(request: AgentRequest):

    result = Orchestrator.run(request.goal)

    return result


from typing import Optional
from agents.gmail_agent import GmailAgent


class EmailAnalyzeRequest(BaseModel):
    subject: str
    sender: str
    body: str


class AutoApplyRequest(BaseModel):
    email_data: dict
    headless: bool = True


@router.get("/gmail/status")
async def get_gmail_status():
    agent = GmailAgent()
    is_auth = agent.is_authenticated()
    has_creds = agent.credentials_path.exists()
    return {
        "authenticated": is_auth,
        "credentials_configured": has_creds,
        "token_exists": agent.token_path.exists(),
        "instruction": "Download client secrets as credentials.json to enable live Gmail sync" if not has_creds else "Ready to scan"
    }


@router.post("/gmail/analyze")
async def analyze_email(request: EmailAnalyzeRequest):
    return GmailAgent.analyze_email_content(
        subject=request.subject,
        sender=request.sender,
        body=request.body
    )


@router.post("/gmail/auto-apply")
async def auto_apply_from_email(request: AutoApplyRequest):
    return GmailAgent.process_and_auto_apply(
        email_data=request.email_data,
        headless=request.headless
    )
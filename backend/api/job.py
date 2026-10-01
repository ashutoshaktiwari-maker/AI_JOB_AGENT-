from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.job_matcher import JobMatcher

router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobRequest(BaseModel):
    job_description: str


@router.post("/match")
async def match_job(request: JobRequest):

    profile_path = Path("data/profile.json")

    if not profile_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Profile not found. Upload your resume first."
        )

    result = JobMatcher.match(
        str(profile_path),
        request.job_description
    )

    return result


from typing import Optional
from services.cover_letter_generator import CoverLetterGenerator


class CoverLetterRequest(BaseModel):
    job_description: str
    company_name: Optional[str] = None
    role_title: Optional[str] = None


@router.post("/cover-letter")
async def generate_cover_letter(request: CoverLetterRequest):
    profile_path = Path("data/profile.json")

    if not profile_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Profile not found. Upload your resume first."
        )

    save_path = "data/cover_letter.txt"
    result = CoverLetterGenerator.generate(
        resume=str(profile_path),
        job_description=request.job_description,
        company_name=request.company_name,
        role_title=request.role_title,
        save_path=save_path
    )

    return result


from agents.email_agent import EmailAgent


class RecruiterEmailRequest(BaseModel):
    job_description: str
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    recruiter_email: Optional[str] = None


@router.post("/recruiter-email")
async def generate_recruiter_email(request: RecruiterEmailRequest):
    profile_path = Path("data/profile.json")

    if not profile_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Profile not found. Upload your resume first."
        )

    save_path = "data/recruiter_email.txt"
    result = EmailAgent.generate_email(
        resume=str(profile_path),
        job=request.job_description,
        company_name=request.company_name,
        role_title=request.role_title,
        recruiter_email=request.recruiter_email,
        save_path=save_path
    )

    return result


from services.application_automator import ApplicationAutomator


class ApplyJobRequest(BaseModel):
    apply_url: str
    tailored_resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    headless: bool = True


@router.post("/apply")
async def apply_to_job(request: ApplyJobRequest):
    profile_path = Path("data/profile.json")

    if not profile_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Profile not found. Upload your resume first."
        )

    result = ApplicationAutomator.apply_to_job(
        apply_url=request.apply_url,
        resume_profile=str(profile_path),
        tailored_resume_path=request.tailored_resume_path,
        cover_letter_path=request.cover_letter_path,
        headless=request.headless
    )

    return result
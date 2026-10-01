import json
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from tools.resume_parser import ResumeParser

router = APIRouter(prefix="/resume", tags=["Resume"])


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=415,
            detail="Only PDF files are allowed."
        )

    # Create folders
    upload_dir = Path("uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded PDF
    file_path = upload_dir / file.filename

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Extract text
    extracted_text = ResumeParser.extract_text(str(file_path))

    # Save raw text
    with open(data_dir / "resume.txt", "w", encoding="utf-8") as f:
        f.write(extracted_text)

    # -------- BASIC PROFILE EXTRACTION --------

    email = ""
    phone = ""
    linkedin = ""
    github = ""

    email_match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        extracted_text,
    )
    if email_match:
        email = email_match.group()

    phone_match = re.search(
        r"(\+?\d[\d\s\-]{8,}\d)",
        extracted_text,
    )
    if phone_match:
        phone = phone_match.group()

    linkedin_match = re.search(
        r"https?://(?:www\.)?linkedin\.com/in/[^\s]+",
        extracted_text,
    )
    if linkedin_match:
        linkedin = linkedin_match.group()

    github_match = re.search(
        r"https?://(?:www\.)?github\.com/[^\s]+",
        extracted_text,
    )
    if github_match:
        github = github_match.group()

    lines = [
        line.strip()
        for line in extracted_text.splitlines()
        if line.strip()
    ]

    name = lines[0] if lines else ""

    profile = {
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "resume_path": str(file_path),
        "resume_text_path": str(data_dir / "resume.txt"),
        "resume_text": extracted_text
    }

    # Save profile
    with open(data_dir / "profile.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=4, ensure_ascii=False)

    return {
        "message": "Resume uploaded successfully",
        "filename": file.filename,
        "profile_created": True,
        "profile_path": str(data_dir / "profile.json")
    }


from pydantic import BaseModel
from services.resume_generator import ATSResumeGenerator


class TailorResumeRequest(BaseModel):
    job_description: str


@router.post("/tailor")
async def tailor_resume(request: TailorResumeRequest):
    data_dir = Path("data")
    profile_path = data_dir / "profile.json"

    if not profile_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Profile not found. Upload your resume first."
        )

    save_path = str(data_dir / "tailored_resume.txt")
    result = ATSResumeGenerator.generate_tailored_resume(
        resume=str(profile_path),
        job_description=request.job_description,
        save_path=save_path
    )

    return result
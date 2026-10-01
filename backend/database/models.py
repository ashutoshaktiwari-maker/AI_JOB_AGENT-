"""
Data Models for Application Tracker.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    APPLIED = "Applied"
    INTERVIEW = "Interview"
    REJECTED = "Rejected"
    OFFER = "Offer"


class ApplicationCreate(BaseModel):
    company: str = Field(..., description="Target company name")
    role: str = Field(..., description="Job role or title")
    apply_url: Optional[str] = Field(None, description="Job application web URL")
    resume_version: Optional[str] = Field(None, description="File path or label of resume used")
    cover_letter_version: Optional[str] = Field(None, description="File path or label of cover letter used")
    status: ApplicationStatus = Field(default=ApplicationStatus.APPLIED, description="Current application status")
    applied_date: str = Field(default_factory=lambda: date.today().isoformat(), description="Date applied (YYYY-MM-DD)")
    interview_date: Optional[str] = Field(None, description="Date of interview if scheduled")
    notes: Optional[str] = Field(None, description="Additional context, notes, or recruiter contact")


class ApplicationUpdate(BaseModel):
    status: Optional[ApplicationStatus] = None
    interview_date: Optional[str] = None
    notes: Optional[str] = None
    resume_version: Optional[str] = None
    cover_letter_version: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: int
    company: str
    role: str
    apply_url: Optional[str]
    resume_version: Optional[str]
    cover_letter_version: Optional[str]
    status: str
    applied_date: str
    interview_date: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str

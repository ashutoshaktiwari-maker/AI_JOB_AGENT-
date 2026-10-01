"""
FastAPI Router for Application Tracker.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from database.db import db
from database.models import ApplicationCreate, ApplicationResponse, ApplicationUpdate

router = APIRouter(prefix="/tracker", tags=["Application Tracker"])


@router.get("", response_model=List[ApplicationResponse])
async def list_applications(status: Optional[str] = Query(None, description="Filter by status")):
    """List all tracked job applications."""
    return db.get_all_applications(status=status)


@router.get("/stats")
async def get_tracker_stats():
    """Retrieve application status metrics breakdown."""
    return db.get_stats()


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: int):
    """Get single application details."""
    app = db.get_application_by_id(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    return app


@router.post("", response_model=ApplicationResponse)
async def create_application(application: ApplicationCreate):
    """Record a new job application."""
    return db.add_application(application)


@router.patch("/{app_id}", response_model=ApplicationResponse)
async def update_application(app_id: int, updates: ApplicationUpdate):
    """Update application status, interview date, or notes."""
    updated = db.update_application(app_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Application not found.")
    return updated


@router.delete("/{app_id}")
async def delete_application(app_id: int):
    """Delete an application record."""
    success = db.delete_application(app_id)
    if not success:
        raise HTTPException(status_code=404, detail="Application not found.")
    return {"message": "Application deleted successfully", "id": app_id}

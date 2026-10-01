from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.resume import router as resume_router
from api.job import router as job_router
from api.agent import router as agent_router
from api.tracker import router as tracker_router


app = FastAPI(title="AI Job Agent")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(resume_router)
app.include_router(job_router)
app.include_router(agent_router)
app.include_router(tracker_router)


@app.get("/")
async def root():
    return {
        "status": "running",
        "project": "AI Job Agent",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }
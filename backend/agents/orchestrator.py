from agents.planner import Planner
from agents.job_search_agent import JobSearchAgent
from agents.resume_match_agent import ResumeMatchAgent


class Orchestrator:

    @staticmethod
    def run(goal: str):

        plan = Planner.create_plan(goal)

        jobs = JobSearchAgent.run(goal)

        ranked_jobs = ResumeMatchAgent.match(jobs)

        return {
            "goal": goal,
            "plan": [task.name for task in plan],
            "total_jobs": len(ranked_jobs),
            "jobs": ranked_jobs
        }
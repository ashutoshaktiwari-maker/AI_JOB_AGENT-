from services.remoteok import RemoteOK


class JobSearchAgent:

    @staticmethod
    def run(goal: str):

        print(f"\n🔍 Searching jobs for: {goal}")

        jobs = RemoteOK.search(goal)

        print(f"✅ Found {len(jobs)} jobs")

        return jobs
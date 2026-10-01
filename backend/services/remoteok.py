import logging
import re
import requests

logger = logging.getLogger(__name__)


class RemoteOK:

    URL = "https://remoteok.com/api"

    @staticmethod
    def search(keyword: str):

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        try:
            response = requests.get(
                RemoteOK.URL,
                headers=headers,
                timeout=20,
            )

            response.raise_for_status()

            data = response.json()

        except Exception as e:
            logger.error("RemoteOK Error: %s", e)
            return []

        jobs = []

        for job in data[1:]:
            text = (
                f"{job.get('position', '')} "
                f"{job.get('description', '')} "
                f"{' '.join(job.get('tags', []))}"
            ).lower()

            if keyword.lower() not in text:
                continue

            desc = job.get("description", "")
            clean_desc = re.sub(r"<[^>]+>", " ", desc).strip()

            jobs.append({
                "portal": "RemoteOK",
                "company": job.get("company"),
                "title": job.get("position"),
                "location": job.get("location"),
                "url": job.get("url"),
                "tags": job.get("tags", []),
                "description": clean_desc or desc,
            })

        return jobs[:20]
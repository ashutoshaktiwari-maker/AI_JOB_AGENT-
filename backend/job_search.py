import requests

def search_jobs(query: str) -> list:
    url = f"https://remoteok.io/api?query={query}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        jobs = []
        for item in data:
            if item['type'] == 'job':
                jobs.append({
                    "title": item['position'],
                    "company": item['company'],
                    "location": item['location'],
                    "apply_url": item['url'],
                    "source": "RemoteOK"
                })
        return jobs
    except requests.RequestException:
        return []
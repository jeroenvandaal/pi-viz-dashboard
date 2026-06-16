import os
import httpx

def post_features(items: list[dict]) -> dict:
    if not items:
        return {"inserted": 0, "updated": 0}
    url = os.environ["VIZ_PI_URL"].rstrip("/") + "/api/features"
    resp = httpx.post(url, json={"items": items},
                      headers={"X-Dashboard-Token": os.environ["VIZ_TOKEN"]}, timeout=20)
    resp.raise_for_status()
    return resp.json()

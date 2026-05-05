import httpx

from .schemas import Comment


class JiraClient:
    def __init__(self, base_url: str, user: str, token: str):
        self._base = base_url
        self._auth = (user, token)

    def _get(self, path: str) -> dict:
        resp = httpx.get(
            f"{self._base}{path}",
            auth=self._auth,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    def get_issue(self, ticket_id: str) -> dict:
        return self._get(f"/rest/api/2/issue/{ticket_id}")

    def get_comments(self, ticket_id: str) -> list[dict]:
        data = self._get(f"/rest/api/2/issue/{ticket_id}/comment?maxResults=5000&orderBy=created")
        return data.get("comments", [])


def parse_comments(raw: list[dict]) -> list[Comment]:
    return [
        Comment(
            author=c.get("author", {}).get("displayName") or "",
            created=c.get("created") or "",
            body=c.get("body") or "",
        )
        for c in raw
    ]

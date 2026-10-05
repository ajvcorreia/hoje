"""A tiny stand-in for FelizAnniv's people API, for the Playwright suite only.

GET /api/v1/people?page=&pageSize= with ``Authorization: Bearer fa_live_e2e_fake_key_0123456789``
answers FelizAnniv's envelope with two people: Ada Lovelace on the 15th of the current month
(born 30 years ago) and Grace Hopper on 29 February (no year). Anything else: 401 or 404.
Standard library only; runs in the hoje-api image (deploy/compose.e2e.yml).
"""

import datetime as dt
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

API_KEY = "fa_live_e2e_fake_key_0123456789"  # throwaway, test stack only


def people() -> list[dict]:
    today = dt.date.today()
    return [
        {
            "id": "7a1d5f3e-0000-4000-8000-000000000001",
            "name": "Ada Lovelace",
            "birthMonth": today.month,
            "birthDay": 15,
            "birthYear": today.year - 30,
            "notes": "never stored by Hoje",
        },
        {
            "id": "7a1d5f3e-0000-4000-8000-000000000002",
            "name": "Grace Hopper",
            "birthMonth": 2,
            "birthDay": 29,
            "birthYear": None,
            "notes": None,
        },
    ]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        if parts.path == "/healthz":
            self._send(200, {"status": "ok"})
            return
        if parts.path != "/api/v1/people":
            self._send(404, {"error": {"code": "NOT_FOUND", "message": "Route not found"}})
            return
        if self.headers.get("Authorization") != f"Bearer {API_KEY}":
            self._send(401, {"error": {"code": "UNAUTHORIZED", "message": "Invalid API key"}})
            return
        query = parse_qs(parts.query)
        page = int(query.get("page", ["1"])[0])
        size = int(query.get("pageSize", ["25"])[0])
        everyone = people()
        items = everyone[(page - 1) * size : page * size]
        total_pages = -(-len(everyone) // size)
        self._send(
            200,
            {
                "items": items,
                "page": page,
                "pageSize": size,
                "total": len(everyone),
                "totalPages": total_pages,
            },
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 4000), Handler).serve_forever()  # noqa: S104 - container

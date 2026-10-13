"""A tiny stand-in for FelizAnniv's people API, for the Playwright suite only.

Every API key of the form ``fa_live_e2e_fake_key_<anything>`` has its own people, so specs do not
disturb each other. A key starts with two people: Ada Lovelace on the 15th of the current month
(born 30 years ago) and Grace Hopper on 29 February (no year). Supported, like the real API:

    GET    /api/v1/people?page=&pageSize=   FelizAnniv's paginated envelope
    POST   /api/v1/people                   201 {"person": {...}}
    PATCH  /api/v1/people/{id}              200 {"person": {...}}
    DELETE /api/v1/people/{id}              204

Anything else: 401 (wrong key), 400 (invalid body) or 404. State lives in memory and is lost when
the container stops. Standard library only; runs in the hoje-api image (deploy/compose.e2e.yml).
"""

import datetime as dt
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

KEY_PREFIX = "fa_live_e2e_fake_key_"  # throwaway, test stack only
PEOPLE_PATH = "/api/v1/people"

_lock = threading.Lock()
_people: dict[str, list[dict]] = {}


def initial_people() -> list[dict]:
    today = dt.date.today()
    return [
        {
            "id": "7a1d5f3e-0000-4000-8000-000000000001",
            "name": "Ada Lovelace",
            "birthMonth": today.month,
            "birthDay": 15,
            "birthYear": today.year - 30,
            "notes": "Analyst",
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


def valid(body: object, *, partial: bool) -> bool:
    """FelizAnniv's own limits for a person."""
    if not isinstance(body, dict):
        return False
    if not partial and not {"name", "birthMonth", "birthDay"} <= body.keys():
        return False
    name, month, day = body.get("name"), body.get("birthMonth"), body.get("birthDay")
    year, notes = body.get("birthYear"), body.get("notes")
    if "name" in body and not (isinstance(name, str) and 1 <= len(name) <= 120):
        return False
    if "birthMonth" in body and not (isinstance(month, int) and 1 <= month <= 12):
        return False
    if "birthDay" in body and not (isinstance(day, int) and 1 <= day <= 31):
        return False
    if year is not None and not (isinstance(year, int) and 1900 <= year <= dt.date.today().year):
        return False
    return notes is None or (isinstance(notes, str) and len(notes) <= 2000)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict | None = None) -> None:
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send(status, {"error": {"code": code, "message": message}})

    def _key(self) -> str | None:
        header = self.headers.get("Authorization", "")
        key = header.removeprefix("Bearer ")
        return key if header.startswith("Bearer ") and key.startswith(KEY_PREFIX) else None

    def _json(self) -> object:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            return None

    def _route(self, method: str) -> None:
        parts = urlsplit(self.path)
        if parts.path == "/healthz":
            self._send(200, {"status": "ok"})
            return
        if parts.path != PEOPLE_PATH and not parts.path.startswith(PEOPLE_PATH + "/"):
            self._error(404, "NOT_FOUND", "Route not found")
            return
        key = self._key()
        if key is None:
            self._error(401, "UNAUTHORIZED", "Invalid API key")
            return
        person_id = parts.path.removeprefix(PEOPLE_PATH).strip("/")
        with _lock:
            everyone = _people.setdefault(key, initial_people())
            if not person_id:
                self._collection(method, parts.query, everyone)
            else:
                self._member(method, person_id, everyone)

    def _collection(self, method: str, query: str, everyone: list[dict]) -> None:
        if method == "GET":
            params = parse_qs(query)
            page = int(params.get("page", ["1"])[0])
            size = int(params.get("pageSize", ["25"])[0])
            self._send(
                200,
                {
                    "items": everyone[(page - 1) * size : page * size],
                    "page": page,
                    "pageSize": size,
                    "total": len(everyone),
                    "totalPages": -(-len(everyone) // size),
                },
            )
        elif method == "POST":
            body = self._json()
            if not isinstance(body, dict) or not valid(body, partial=False):
                self._error(400, "VALIDATION", "Invalid person")
                return
            person = {"birthYear": None, "notes": None, **body, "id": str(uuid.uuid4())}
            everyone.append(person)
            self._send(201, {"person": person})
        else:
            self._error(404, "NOT_FOUND", "Route not found")

    def _member(self, method: str, person_id: str, everyone: list[dict]) -> None:
        person = next((p for p in everyone if p["id"] == person_id), None)
        if person is None:
            self._error(404, "NOT_FOUND", "Person not found")
        elif method == "PATCH":
            body = self._json()
            if not isinstance(body, dict) or not valid(body, partial=True):
                self._error(400, "VALIDATION", "Invalid person")
                return
            person.update({k: v for k, v in body.items() if k != "id"})
            self._send(200, {"person": person})
        elif method == "DELETE":
            everyone.remove(person)
            self._send(204)
        elif method == "GET":
            self._send(200, {"person": person})
        else:
            self._error(404, "NOT_FOUND", "Route not found")

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def do_PATCH(self) -> None:
        self._route("PATCH")

    def do_DELETE(self) -> None:
        self._route("DELETE")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 4000), Handler).serve_forever()  # noqa: S104 - container

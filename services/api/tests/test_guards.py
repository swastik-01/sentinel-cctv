"""guards.py: input PostgreSQL or the JSON encoder cannot take is a 4xx before any route, and a validation refusal
never repeats what was sent (scripts/edge_checks.py found each of these as a 500)."""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from sentinel_api.guards import MAX_JSON_BYTES, RequestGuard, validation_refusal


class Body(BaseModel):
    name: str
    lat: float = Field(0, ge=-90, le=90)
    password: str | None = None


def client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestGuard)
    app.add_middleware(CORSMiddleware, allow_origins=["http://ui"], allow_methods=["*"], allow_headers=["*"])
    app.add_exception_handler(RequestValidationError, validation_refusal)

    @app.get("/items/{code}")
    def item(code: str, q: str | None = None):
        return {"code": code, "q": q}

    @app.post("/items")
    def make(b: Body):
        return b.model_dump()

    return TestClient(app)


def test_ordinary_requests_pass():
    c = client()
    assert c.get("/items/CAM01", params={"q": "ગુજરાત %_"}).json() == {"code": "CAM01", "q": "ગુજરાત %_"}
    assert c.post("/items", json={"name": "Gate 🚦"}).json()["name"] == "Gate 🚦"


def test_a_nul_in_the_path_query_or_body_is_a_422():
    c = client()
    assert c.get("/items/a%00b").status_code == 422
    assert c.get("/items/CAM01", params={"q": "a\x00b"}).status_code == 422
    assert c.post("/items", json={"name": "a\x00b"}).status_code == 422
    assert c.post("/items", content=b'{"name": "a\\u0000b"}', headers={"Content-Type": "application/json"}).status_code == 422


def test_a_nul_is_refused_whatever_the_body_says_it_is():
    c = client()
    body = b'{"name": "a\u0000b"}'
    assert c.post("/items", content=body).status_code == 422                       # no content type: still JSON
    assert c.post("/items", content=body, headers={"Content-Type": "application/vnd.api+json"}).status_code == 422
    assert c.post("/items", content=body, headers={"Content-Type": "text/plain"}).status_code != 500


def test_a_literal_backslash_u_text_that_is_not_nul_passes():
    r = client().post("/items", json={"name": "C:\\users\\u0001"})
    assert r.status_code == 200


def test_nan_in_a_body_is_a_422_not_a_500():
    r = client().post("/items", content=b'{"name": "x", "lat": NaN}', headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "lat"]


def test_a_refusal_does_not_echo_the_submitted_values():
    r = client().post("/items", json={"name": 5, "password": "hunter2-secret"})
    assert r.status_code == 422
    assert "hunter2-secret" not in r.text and "input" not in r.json()["detail"][0]


def test_an_oversized_json_body_is_a_413():
    big = b'{"name": "' + b"x" * (MAX_JSON_BYTES + 10) + b'"}'
    assert client().post("/items", content=big, headers={"Content-Type": "application/json"}).status_code == 413


def test_a_refusal_still_carries_cors_headers():
    r = client().get("/items/a%00b", headers={"Origin": "http://ui"})
    assert r.status_code == 422
    assert r.headers.get("access-control-allow-origin") == "http://ui"

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, local_backend):
    monkeypatch.setenv("SANDBOX_TOKEN", "s3cret")
    import sandbox.main as m
    importlib.reload(m)
    with TestClient(m.create_app(local_backend)) as c:
        yield c


def test_health(client):
    r = client.get("/health").json()
    assert r["ok"] and r["backend"] == "local" and set(r["images"]) == {"python", "c", "cpp", "java"}


def test_run_requires_token(client):
    assert client.post("/run", json={"language": "python", "source": "print(1)"}).status_code == 401


def test_run(client):
    r = client.post("/run", headers={"X-Sandbox-Token": "s3cret"},
                    json={"language": "python", "source": "print(input()[::-1])", "tests": ["abc"]})
    assert r.status_code == 200 and r.json()["tests"][0]["stdout"] == "cba\n"


@pytest.mark.parametrize("body", [
    {"language": "ruby", "source": "x"},
    {"language": "java", "source": "x", "entrypoint": "a/b"},
])
def test_rejects_bad_requests(client, body):
    assert client.post("/run", headers={"X-Sandbox-Token": "s3cret"}, json=body).status_code == 400

"""Integration tests run against the Compose PostgreSQL and MinIO services."""

import os
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def login(client: TestClient, role: str) -> dict:
    response = client.post("/api/login", data={"username": role, "password": os.environ[f"{role.upper()}_PASSWORD"]})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_upload_index_permissions_citations_and_abstention():
    with TestClient(app) as client:
        admin = login(client, "admin")
        hr = login(client, "hr")
        finance = login(client, "finance")
        title = f"Synthetic policy {uuid4().hex[:8]}"
        badge = f"sapphire{uuid4().hex[:8]}"
        upload = client.post(
            "/api/documents",
            headers=admin,
            data={"title": title, "roles": "hr"},
            files={"file": ("badge-policy.md", f"# Badge renewal\n\nThe badge {badge} is renewed every 17 days.".encode(), "text/markdown")},
        )
        assert upload.status_code == 201, upload.text
        document_id = upload.json()["id"]
        assert upload.json()["status"] == "ready"
        assert upload.json()["sections"] == 1

        hr_docs = client.get("/api/documents", headers=hr).json()
        assert any(doc["id"] == document_id and doc["status"] == "ready" for doc in hr_docs)
        assert all(doc["id"] != document_id for doc in client.get("/api/documents", headers=finance).json())
        assert client.get(f"/api/documents/{document_id}", headers=finance).status_code == 404

        question = {"question": f"How many days until the badge {badge} is renewed?"}
        answer = client.post("/api/ask", headers=hr, json=question).json()
        assert not answer["abstained"], answer
        assert "17 days" in answer["answer"]
        assert answer["citations"][0]["document_id"] == document_id
        assert answer["citations"][0]["section"] == "Badge renewal"
        assert answer["citations"][0]["quote"] == answer["answer"]

        hidden = client.post("/api/ask", headers=finance, json=question).json()
        assert hidden["abstained"]
        assert hidden["citations"] == []
        unknown = client.post("/api/ask", headers=hr, json={"question": f"Which planet issued the badge {badge}?"}).json()
        assert unknown["abstained"]


def test_upload_requires_admin_and_valid_file():
    with TestClient(app) as client:
        employee = login(client, "employee")
        admin = login(client, "admin")
        data = {"title": "Bad", "roles": "employee"}
        files = {"file": ("bad.exe", b"hello", "application/octet-stream")}
        assert client.post("/api/documents", headers=employee, data=data, files=files).status_code == 403
        assert client.post("/api/documents", headers=admin, data=data, files=files).status_code == 422
        assert client.get("/api/admin/stats", headers=employee).status_code == 403

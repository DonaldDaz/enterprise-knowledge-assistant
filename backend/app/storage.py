from io import BytesIO
from pathlib import Path
from uuid import uuid4

import psycopg
from minio import Minio
from psycopg.rows import dict_row

from .config import BUCKET, settings
from .rag import embedding_provider, sections_from_text, vector_literal


def connection():
    return psycopg.connect(host=settings.postgres_host, dbname="knowledge", user="knowledge", password=settings.postgres_password, row_factory=dict_row)


def object_store():
    return Minio(settings.minio_endpoint, access_key=settings.minio_user, secret_key=settings.minio_password, secure=False)


SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY, title text NOT NULL, object_key text NOT NULL,
    filename text NOT NULL, roles text[] NOT NULL, status text NOT NULL,
    error text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sections (
    id bigserial PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal integer NOT NULL, heading text NOT NULL, content text NOT NULL,
    embedding vector(128) NOT NULL
);
CREATE INDEX IF NOT EXISTS documents_roles_idx ON documents USING gin (roles);
CREATE INDEX IF NOT EXISTS sections_document_idx ON sections (document_id);
CREATE TABLE IF NOT EXISTS requests (
    id bigserial PRIMARY KEY, username text NOT NULL, role text NOT NULL,
    abstained boolean NOT NULL, latency_ms double precision NOT NULL,
    estimated_cost_usd double precision NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS requests_user_time_idx ON requests (username, created_at);
"""


def initialize():
    with connection() as db:
        db.execute(SCHEMA)
    store = object_store()
    if not store.bucket_exists(BUCKET):
        store.make_bucket(BUCKET)


def ingest(title: str, filename: str, data: bytes, roles: list[str], *, document_id=None):
    """Persist the original, then index synchronously so ready means searchable."""
    from pypdf import PdfReader

    document_id = document_id or uuid4()
    suffix = Path(filename).suffix.lower()
    if suffix not in (".md", ".txt", ".pdf"):
        raise ValueError("Only .md, .txt, and .pdf files are supported")
    if suffix == ".pdf":
        try:
            text = "\n\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
        except Exception as exc:
            raise ValueError("The PDF could not be read") from exc
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("The file must be UTF-8 encoded") from exc
    parts = sections_from_text(text, suffix)
    if not parts or not any(content.strip() for _, content in parts):
        raise ValueError("The document contains no extractable text")

    key = f"{document_id}/{Path(filename).name}"
    store = object_store()
    store.put_object(BUCKET, key, BytesIO(data), len(data), content_type={".md": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf"}[suffix])
    with connection() as db:
        db.execute("INSERT INTO documents (id,title,object_key,filename,roles,status) VALUES (%s,%s,%s,%s,%s,'indexing')", (document_id, title, key, filename, roles))
    try:
        with connection() as db:
            for ordinal, (heading, content) in enumerate(parts, 1):
                db.execute("INSERT INTO sections (document_id,ordinal,heading,content,embedding) VALUES (%s,%s,%s,%s,%s::vector)", (document_id, ordinal, heading, content, vector_literal(embedding_provider.embed(f"{heading} {content}"))))
            db.execute("UPDATE documents SET status='ready' WHERE id=%s", (document_id,))
    except Exception:
        with connection() as db:
            db.execute("UPDATE documents SET status='failed', error='Indexing failed' WHERE id=%s", (document_id,))
        raise
    return document_id, len(parts)


def seed_documents(data_dir: Path):
    with connection() as db:
        existing = db.execute("SELECT count(*) AS n FROM documents").fetchone()["n"]
    if existing:
        return
    for name, title, roles in [
        ("travel-policy.md", "Travel and Expense Policy", ["employee", "hr", "finance"]),
        ("people-handbook.md", "People Handbook", ["hr"]),
        ("budget-policy.md", "Project Budget Policy", ["finance"]),
    ]:
        path = data_dir / name
        ingest(title, name, path.read_bytes(), roles)

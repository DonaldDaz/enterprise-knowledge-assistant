import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from .config import ROLES, settings
from .rag import answer_provider, embedding_provider, vector_literal
from .security import admin_user, authenticate, current_user
from .storage import connection, ingest, initialize, seed_demo
from .telemetry import tracer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("knowledge")


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    demo_dir = Path("/app/demo")
    if demo_dir.exists():
        seed_demo(demo_dir)
    yield


app = FastAPI(title="Enterprise Knowledge Assistant", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def log_metadata(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    # Paths and bodies can contain sensitive data. Record only the route class and status.
    route = request.scope.get("route")
    route_name = route.path if route else "unmatched"
    logger.info("method=%s route=%s status=%d duration_ms=%.1f", request.method, route_name, response.status_code, (time.perf_counter() - start) * 1000)
    return response


class Question(BaseModel):
    question: str = Field(min_length=5, max_length=500)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    result = authenticate(form.username, form.password)
    if not result:
        raise HTTPException(401, "Credenziali non valide")
    return result


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


@app.post("/api/documents", status_code=201)
def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    roles: str = Form(...),
    _: dict = Depends(admin_user),
):
    allowed = sorted(set(part.strip() for part in roles.split(",") if part.strip()))
    if not allowed or any(role not in ROLES for role in allowed):
        raise HTTPException(422, f"Scegli almeno un ruolo tra: {', '.join(ROLES)}")
    if not title.strip() or len(title) > 120:
        raise HTTPException(422, "Titolo obbligatorio (massimo 120 caratteri)")
    data = file.file.read(1_000_001)
    if len(data) > 1_000_000:
        raise HTTPException(413, "Dimensione massima: 1 MB")
    with tracer.start_as_current_span("document.ingest") as span:
        span.set_attribute("document.bytes", len(data))
        span.set_attribute("document.role_count", len(allowed))
        try:
            document_id, count = ingest(title.strip(), file.filename or "document.txt", data, allowed)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        span.set_attribute("document.sections", count)
    return {"id": document_id, "title": title.strip(), "status": "ready", "sections": count, "roles": allowed}


@app.get("/api/documents")
def list_documents(user: dict = Depends(current_user)):
    with connection() as db:
        rows = db.execute("""
            SELECT d.id,d.title,d.filename,d.roles,d.status,d.error,d.created_at,
                   count(s.id)::int AS sections
            FROM documents d LEFT JOIN sections s ON s.document_id=d.id
            WHERE %s=ANY(d.roles) OR %s='admin'
            GROUP BY d.id ORDER BY d.created_at DESC
        """, (user["role"], user["role"])).fetchall()
    return rows


@app.get("/api/documents/{document_id}")
def read_document(document_id: UUID, user: dict = Depends(current_user)):
    with connection() as db:
        row = db.execute("SELECT id,title,roles,status FROM documents WHERE id=%s AND (%s=ANY(roles) OR %s='admin')", (document_id, user["role"], user["role"])).fetchone()
        if not row:
            raise HTTPException(404, "Documento non disponibile")
        rows = db.execute("SELECT ordinal,heading,content FROM sections WHERE document_id=%s ORDER BY ordinal", (document_id,)).fetchall()
    return {**row, "sections": rows}


@app.post("/api/ask")
def ask(payload: Question, user: dict = Depends(current_user)):
    start = time.perf_counter()
    username, role = user["username"], user["role"]
    # The estimate is intentionally transparent and conservative for this extractive provider.
    estimated_tokens = (len(payload.question) + 1200) / 4
    estimated_cost = round(estimated_tokens * settings.usd_per_1k_tokens / 1000, 6)
    with connection() as db:
        recent = db.execute("SELECT count(*)::int AS n FROM requests WHERE username=%s AND created_at>now()-interval '1 minute'", (username,)).fetchone()["n"]
        daily = db.execute("SELECT coalesce(sum(estimated_cost_usd),0) AS total FROM requests WHERE created_at>=date_trunc('day',now())", ()).fetchone()["total"]
    if recent >= settings.max_requests_per_minute:
        raise HTTPException(429, "Limite di richieste al minuto raggiunto")
    if estimated_cost > settings.max_request_cost_usd or daily + estimated_cost > settings.max_daily_cost_usd:
        raise HTTPException(429, "Budget stimato esaurito")

    with tracer.start_as_current_span("rag.answer") as span:
        span.set_attribute("enduser.role", role)
        with tracer.start_as_current_span("rag.embed"):
            vector = vector_literal(embedding_provider.embed(payload.question))
        with tracer.start_as_current_span("rag.retrieve"):
            with connection() as db:
                rows = db.execute("""
                    SELECT s.document_id,d.title,s.heading AS section,s.content,
                           1-(s.embedding <=> %s::vector) AS similarity
                    FROM sections s JOIN documents d ON d.id=s.document_id
                    WHERE d.status='ready' AND (%s=ANY(d.roles) OR %s='admin')
                    ORDER BY s.embedding <=> %s::vector LIMIT 8
                """, (vector, role, role, vector)).fetchall()
        span.set_attribute("rag.retrieved_count", len(rows))
        with tracer.start_as_current_span("rag.generate"):
            answer, citations = answer_provider.answer(payload.question, rows)
        abstained = not citations
        span.set_attribute("rag.abstained", abstained)
        span.set_attribute("rag.citation_count", len(citations))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        with connection() as db:
            db.execute("INSERT INTO requests (username,role,abstained,latency_ms,estimated_cost_usd) VALUES (%s,%s,%s,%s,%s)", (username, role, abstained, latency_ms, estimated_cost))
    trace_id = format(span.get_span_context().trace_id, "032x")
    return {"answer": answer, "citations": citations, "abstained": abstained, "latency_ms": latency_ms, "estimated_cost_usd": estimated_cost, "trace_id": trace_id}


@app.get("/api/admin/stats")
def statistics(_: dict = Depends(admin_user)):
    with connection() as db:
        row = db.execute("""
            SELECT count(*)::int AS requests,
                   count(*) FILTER (WHERE abstained)::int AS abstentions,
                   round(coalesce(avg(latency_ms),0)::numeric,2) AS avg_latency_ms,
                   round(coalesce(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),0)::numeric,2) AS p95_latency_ms,
                   round(coalesce(sum(estimated_cost_usd),0)::numeric,6) AS estimated_cost_usd
            FROM requests
        """).fetchone()
        docs = db.execute("SELECT status,count(*)::int AS count FROM documents GROUP BY status").fetchall()
    return {**row, "documents_by_status": {entry["status"]: entry["count"] for entry in docs}}

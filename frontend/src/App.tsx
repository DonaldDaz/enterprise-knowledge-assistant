import { useState, type FormEvent } from "react";

type Role = "admin" | "hr" | "finance" | "employee";
type Session = { access_token: string; username: string; role: Role };
type Citation = {
  document_id: string;
  title: string;
  section: string;
  quote: string;
};
type Answer = {
  answer: string;
  citations: Citation[];
  abstained: boolean;
  latency_ms: number;
  estimated_cost_usd: number;
  trace_id: string;
};
type Document = {
  id: string;
  title: string;
  filename: string;
  roles: Role[];
  status: string;
  sections: number;
  created_at: string;
};
type Stats = {
  requests: number;
  abstentions: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  estimated_cost_usd: number;
  documents_by_status: Record<string, number>;
};
type Section = { ordinal: number; heading: string; content: string };

const accounts: { role: Role; label: string; initials: string }[] = [
  { role: "employee", label: "Employee", initials: "EM" },
  { role: "hr", label: "Team HR", initials: "HR" },
  { role: "finance", label: "Finance", initials: "FI" },
  { role: "admin", label: "Admin", initials: "AD" },
];

const prompts = [
  "What is the nightly hotel limit?",
  "How many days before parental leave must the request be submitted?",
  "Which project expenses require Finance approval?",
  "What color is the company logo?",
];

async function request<T>(
  path: string,
  token?: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Error ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  const paths: Record<string, React.ReactNode> = {
    spark: (
      <>
        <path d="m12 3 1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8L12 3Z" />
        <path d="m19 18 .5 1.5L21 20l-1.5.5L19 22l-.5-1.5L17 20l1.5-.5L19 18Z" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14m-6-6 6 6-6 6" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V4m-4 4 4-4 4 4" />
        <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
      </>
    ),
    file: (
      <>
        <path d="M6 3h8l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
        <path d="M14 3v5h5M8 13h8M8 17h6" />
      </>
    ),
    lock: (
      <>
        <rect x="5" y="10" width="14" height="11" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </>
    ),
    pulse: (
      <>
        <path d="M3 12h4l3-6 4 12 3-6h4" />
      </>
    ),
    check: (
      <>
        <path d="m5 12 4 4L19 6" />
      </>
    ),
    x: (
      <>
        <path d="M6 6 18 18M18 6 6 18" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    database: (
      <>
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
      </>
    ),
  };
  return (
    <svg {...common} aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [chosenRole, setChosenRole] = useState<Role>("employee");
  const [password, setPassword] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<{
    title: string;
    sections: Section[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadRoles, setUploadRoles] = useState<Role[]>(["employee"]);

  const loadData = async (current: Session) => {
    const documents = await request<Document[]>(
      "/api/documents",
      current.access_token,
    );
    setDocs(documents);
    if (current.role === "admin")
      setStats(await request<Stats>("/api/admin/stats", current.access_token));
    else setStats(null);
  };

  const login = async (event: FormEvent) => {
    event.preventDefault();
    const body = new URLSearchParams({ username: chosenRole, password });
    setError("");
    setAnswer(null);
    setSelectedDoc(null);
    setLoading(true);
    try {
      const current = await request<Session>("/api/login", undefined, {
        method: "POST",
        body,
      });
      setSession(current);
      setPassword("");
      await loadData(current);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const switchRole = (role: Role) => {
    setChosenRole(role);
    setSession(null);
    setPassword("");
    setAnswer(null);
    setDocs([]);
    setStats(null);
    setError("");
  };

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    if (!session || !question.trim()) return;
    setLoading(true);
    setError("");
    setAnswer(null);
    try {
      const result = await request<Answer>("/api/ask", session.access_token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      setAnswer(result);
      if (session.role === "admin") await loadData(session);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const upload = async (event: FormEvent) => {
    event.preventDefault();
    if (!session || !uploadFile) return;
    setLoading(true);
    setError("");
    const body = new FormData();
    body.append("file", uploadFile);
    body.append("title", uploadTitle);
    body.append("roles", uploadRoles.join(","));
    try {
      await request("/api/documents", session.access_token, {
        method: "POST",
        body,
      });
      setUploadFile(null);
      setUploadTitle("");
      const input = document.getElementById(
        "document-file",
      ) as HTMLInputElement;
      if (input) input.value = "";
      await loadData(session);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const openDocument = async (id: string) => {
    if (!session) return;
    try {
      setSelectedDoc(
        await request(`/api/documents/${id}`, session.access_token),
      );
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="#top" className="brand">
          <span className="brand-mark">
            <Icon name="spark" size={22} />
          </span>
          <span>
            knowledge<span className="brand-accent">hub</span>
            <small>ENTERPRISE ASSISTANT</small>
          </span>
        </a>
        <div className="sidebar-label">NAVIGATION</div>
        <nav className="nav">
          <a href="#assistant" className="active">
            <Icon name="spark" size={18} /> Assistant
          </a>
          <a href="#documents">
            <Icon name="file" size={18} /> Documents
          </a>
          <a href="#how-it-works">
            <Icon name="database" size={18} /> How it works
          </a>
          {session?.role === "admin" && (
            <a href="#admin">
              <Icon name="pulse" size={18} /> Administration
            </a>
          )}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> System ready
          <br />
          <small>Local provider · no API charges</small>
        </div>
      </aside>

      <main id="top" className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            WORKSPACE <span>/</span> KNOWLEDGE ASSISTANT
          </div>
          <div className="topbar-right">
            <span className="live-pill">
              <span className="status-dot" /> SERVICE ACTIVE
            </span>
            <a
              href="http://localhost:16686"
              target="_blank"
              rel="noreferrer"
              className="top-link"
            >
              Open traces ↗
            </a>
          </div>
        </header>
        <div className="page-wrap">
          <div className="intro-grid">
            <div>
              <div className="eyebrow">
                <span className="eyebrow-line" /> DOCUMENTS AND ANSWERS / 01
              </div>
              <h1>
                Enterprise knowledge,
                <br />
                <em>with sources in sight.</em>
              </h1>
              <p className="lead">
                Upload documents and ask questions. The RAG assistant retrieves
                only authorized information. Every answer is verifiable; when
                sources are insufficient, it abstains.
              </p>
              <div className="hero-tags">
                <span>
                  <Icon name="check" size={14} /> Verifiable citations
                </span>
                <span>
                  <Icon name="lock" size={14} /> Role-based access
                </span>
                <span>
                  <Icon name="pulse" size={14} /> End-to-end tracing
                </span>
              </div>
            </div>
            <div className="hero-graphic">
              <div className="orbit orbit-one" />
              <div className="orbit orbit-two" />
              <div className="graphic-card left-card">
                <Icon name="file" size={20} />
                <span>Documents</span>
              </div>
              <div className="graphic-center">
                <Icon name="spark" size={30} />
              </div>
              <div className="graphic-card right-card">
                <Icon name="check" size={20} />
                <span>Answer</span>
              </div>
              <div className="graphic-caption">RETRIEVE → VERIFY → ANSWER</div>
            </div>
          </div>

          <section className="workflow-strip" aria-label="RAG workflow">
            <div>
              <b>01</b>
              <span>Upload & index</span>
            </div>
            <i />
            <div>
              <b>02</b>
              <span>Filter by role</span>
            </div>
            <i />
            <div>
              <b>03</b>
              <span>Retrieve sections</span>
            </div>
            <i />
            <div>
              <b>04</b>
              <span>Answer or abstain</span>
            </div>
          </section>

          <section id="assistant" className="section assistant">
            <div className="section-head">
              <div>
                <div className="eyebrow">QUESTIONS AND ANSWERS</div>
                <h2>Assistant</h2>
                <p>
                  Available sources depend on the selected role.
                </p>
              </div>
              <span className="section-number">01 / 03</span>
            </div>
            <div className="play-grid">
              <div className="card ask-card">
                <div className="card-top">
                  <div className="card-icon violet">
                    <Icon name="search" />
                  </div>
                  <div>
                    <h3>Ask a question</h3>
                    <p>Access is checked before retrieval.</p>
                  </div>
                </div>
                <div className="field-label">ACTIVE ROLE</div>
                <div className="role-row">
                  {accounts.map((account) => (
                    <button
                      key={account.role}
                      onClick={() => switchRole(account.role)}
                      className={`role-chip ${chosenRole === account.role ? "selected" : ""}`}
                    >
                      <span>{account.initials}</span>
                      {account.label}
                    </button>
                  ))}
                </div>
                {!session && (
                  <form className="login-form" onSubmit={login}>
                    <label className="field-label" htmlFor="password">
                      PASSWORD · SEE .ENV.EXAMPLE
                    </label>
                    <div className="login-row">
                      <input
                        id="password"
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder={`Password for ${chosenRole}`}
                        required
                      />
                      <button type="submit" disabled={loading}>
                        Sign in <Icon name="arrow" size={15} />
                      </button>
                    </div>
                  </form>
                )}
                <form onSubmit={ask}>
                  <label className="field-label" htmlFor="question">
                    YOUR QUESTION
                  </label>
                  <textarea
                    id="question"
                    rows={4}
                    placeholder="E.g. What is the nightly hotel limit?"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                  />
                  <button
                    className="primary-button"
                    disabled={loading || !session || question.trim().length < 5}
                    type="submit"
                  >
                    {loading ? "Searching…" : "Search documents"}
                    <Icon name="arrow" size={17} />
                  </button>
                </form>
                <div className="suggestions">
                  <span>SUGGESTED QUESTIONS</span>
                  {prompts.map((prompt) => (
                    <button key={prompt} onClick={() => setQuestion(prompt)}>
                      {prompt}
                      <Icon name="arrow" size={14} />
                    </button>
                  ))}
                </div>
              </div>
              <div className={`card answer-card ${answer ? "has-answer" : ""}`}>
                <div className="card-top">
                  <div className="card-icon mint">
                    <Icon name="spark" />
                  </div>
                  <div>
                    <h3>Answer & sources</h3>
                    <p>Every answer identifies its source section.</p>
                  </div>
                </div>
                {answer ? (
                  <div className="answer-content">
                    <div
                      className={`answer-status ${answer.abstained ? "abstained" : ""}`}
                    >
                      <Icon name={answer.abstained ? "x" : "check"} size={15} />
                      {answer.abstained
                        ? "INSUFFICIENT SOURCES"
                        : "SOURCE-BACKED ANSWER"}
                    </div>
                    <p className="answer-text">{answer.answer}</p>
                    {answer.citations.map((citation) => (
                      <button
                        className="citation"
                        key={`${citation.document_id}-${citation.section}`}
                        onClick={() => openDocument(citation.document_id)}
                      >
                        <span>
                          <Icon name="file" size={18} />
                        </span>
                        <span>
                          <b>{citation.title}</b>
                          <small>Section: {citation.section}</small>
                        </span>
                        <Icon name="arrow" size={17} />
                      </button>
                    ))}
                    <div className="answer-meta">
                      <span>
                        Latency <b>{answer.latency_ms} ms</b>
                      </span>
                      <span>
                        Estimated cost{" "}
                        <b>${answer.estimated_cost_usd.toFixed(4)}</b>
                      </span>
                    </div>
                    <div className="trace-id">Trace ID: {answer.trace_id}</div>
                  </div>
                ) : (
                  <div className="empty-answer">
                    <div className="empty-art">
                      <Icon name="spark" size={33} />
                    </div>
                    <b>Waiting for your question</b>
                    <p>
                      The answer, citation, and request metrics will appear
                      here.
                    </p>
                  </div>
                )}
              </div>
            </div>
            {error && (
              <div className="error-banner" role="alert">
                {error}
              </div>
            )}
          </section>

          <section id="documents" className="section">
            <div className="section-head">
              <div>
                <div className="eyebrow">SYNTHETIC CORPUS</div>
                <h2>Available documents</h2>
                <p>
                  Each role sees only its assigned documents. Open one to read
                  its indexed sections.
                </p>
              </div>
              <span className="section-number">02 / 03</span>
            </div>
            <div className="document-grid">
              {docs.map((doc) => (
                <button
                  className="document-card"
                  key={doc.id}
                  onClick={() => openDocument(doc.id)}
                >
                  <div className="doc-icon">
                    <Icon name="file" size={24} />
                  </div>
                  <span className="ready">
                    <span className="status-dot" />
                    {doc.status}
                  </span>
                  <h3>{doc.title}</h3>
                  <p>
                    {doc.sections} {doc.sections === 1 ? "section" : "sections"}{" "}
                    · {doc.filename}
                  </p>
                  <div className="doc-roles">
                    {doc.roles.map((role) => (
                      <span key={role}>{role}</span>
                    ))}
                  </div>
                  <span className="doc-link">
                    View sections <Icon name="arrow" size={15} />
                  </span>
                </button>
              ))}
              {docs.length === 0 && (
                <div className="no-docs">
                  No documents are visible to this role.
                </div>
              )}
            </div>
          </section>

          {session?.role === "admin" && (
            <section id="admin" className="section">
              <div className="section-head">
                <div>
                  <div className="eyebrow">CONTROL ROOM</div>
                  <h2>Administration</h2>
                  <p>
                    Upload a synthetic file and assign the roles that may read
                    it.
                  </p>
                </div>
                <span className="section-number">ADMIN</span>
              </div>
              <div className="admin-grid">
                <form className="card upload-card" onSubmit={upload}>
                  <div className="card-top">
                    <div className="card-icon peach">
                      <Icon name="upload" />
                    </div>
                    <div>
                      <h3>New document</h3>
                      <p>Markdown, text, or PDF · maximum 1 MB</p>
                    </div>
                  </div>
                  <label className="field-label" htmlFor="upload-title">
                    TITLE
                  </label>
                  <input
                    id="upload-title"
                    value={uploadTitle}
                    onChange={(e) => setUploadTitle(e.target.value)}
                    placeholder="E.g. Purchasing policy"
                    required
                  />
                  <label className="field-label" htmlFor="document-file">
                    FILE
                  </label>
                  <input
                    id="document-file"
                    type="file"
                    accept=".md,.txt,.pdf"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    required
                  />
                  <div className="field-label">VISIBLE TO</div>
                  <div className="checkbox-row">
                    {accounts
                      .filter((a) => a.role !== "admin")
                      .map((account) => (
                        <label key={account.role}>
                          <input
                            type="checkbox"
                            checked={uploadRoles.includes(account.role)}
                            onChange={(e) =>
                              setUploadRoles(
                                e.target.checked
                                  ? [...uploadRoles, account.role]
                                  : uploadRoles.filter(
                                      (role) => role !== account.role,
                                    ),
                              )
                            }
                          />
                          {account.label}
                        </label>
                      ))}
                  </div>
                  <button
                    className="primary-button"
                    disabled={loading || !uploadRoles.length}
                    type="submit"
                  >
                    Upload and index <Icon name="arrow" size={17} />
                  </button>
                </form>
                <div className="card stats-card">
                  <div className="card-top">
                    <div className="card-icon mint">
                      <Icon name="pulse" />
                    </div>
                    <div>
                      <h3>Request statistics</h3>
                      <p>Metadata only, without question text.</p>
                    </div>
                  </div>
                  <div className="stats-grid">
                    <div>
                      <span>Requests</span>
                      <b>{stats?.requests ?? "—"}</b>
                    </div>
                    <div>
                      <span>Abstentions</span>
                      <b>{stats?.abstentions ?? "—"}</b>
                    </div>
                    <div>
                      <span>Average latency</span>
                      <b>
                        {stats?.avg_latency_ms ?? "—"} <small>ms</small>
                      </b>
                    </div>
                    <div>
                      <span>P95 latency</span>
                      <b>
                        {stats?.p95_latency_ms ?? "—"} <small>ms</small>
                      </b>
                    </div>
                    <div>
                      <span>Estimated cost</span>
                      <b>
                        ${Number(stats?.estimated_cost_usd ?? 0).toFixed(4)}
                      </b>
                    </div>
                    <div>
                      <span>Ready documents</span>
                      <b>{stats?.documents_by_status.ready ?? 0}</b>
                    </div>
                  </div>
                  <p className="stats-note">
                    Request and cost limits are configurable in{" "}
                    <code>.env</code>.
                  </p>
                </div>
              </div>
            </section>
          )}

          <section id="how-it-works" className="section methodology">
            <div className="section-head">
              <div>
                <div className="eyebrow">UNDER THE HOOD</div>
                <h2>How it works</h2>
                <p>
                  A complete workflow with replaceable components and visible
                  outcomes.
                </p>
              </div>
              <span className="section-number">03 / 03</span>
            </div>
            <div className="method-grid">
              <div>
                <span>01 / INGESTION</span>
                <Icon name="upload" />
                <h3>From file to sections</h3>
                <p>
                  MinIO stores the original. The backend extracts text, keeps
                  headings as citation anchors, and stores embeddings and
                  metadata in PostgreSQL.
                </p>
              </div>
              <div>
                <span>02 / RETRIEVAL</span>
                <Icon name="lock" />
                <h3>Permissions in the query</h3>
                <p>
                  The database filters sections by role before ordering them
                  by pgvector cosine distance.
                </p>
              </div>
              <div>
                <span>03 / GROUNDING</span>
                <Icon name="check" />
                <h3>Verifiable answer</h3>
                <p>
                  The local provider selects a sentence from a source. If the
                  evidence is insufficient, it abstains.
                </p>
              </div>
              <div>
                <span>04 / OBSERVABILITY</span>
                <Icon name="pulse" />
                <h3>Measure without exposing content</h3>
                <p>
                  OpenTelemetry traces each stage. Statistics record role,
                  latency, and estimated cost without questions or answers.
                </p>
              </div>
            </div>
          </section>
          <footer>
            <span>
              KNOWLEDGE HUB <b>·</b> Synthetic documents
            </span>
            <span>FastAPI · pgvector · MinIO · React · OpenTelemetry</span>
          </footer>
        </div>
      </main>
      {selectedDoc && (
        <div className="modal-backdrop" onClick={() => setSelectedDoc(null)}>
          <div
            className="document-modal"
            role="dialog"
            aria-modal="true"
            aria-label={selectedDoc.title}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <div className="eyebrow">SYNTHETIC DOCUMENT</div>
                <h2>{selectedDoc.title}</h2>
              </div>
              <button aria-label="Close" onClick={() => setSelectedDoc(null)}>
                <Icon name="x" />
              </button>
            </div>
            <div className="modal-content">
              {selectedDoc.sections.map((section) => (
                <section key={section.ordinal}>
                  <span>
                    SECTION {String(section.ordinal).padStart(2, "0")}
                  </span>
                  <h3>{section.heading}</h3>
                  <p>{section.content}</p>
                </section>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

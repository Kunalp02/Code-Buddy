import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ProjectMeta } from "../api/client";
import AppShell from "../components/layout/AppShell";

type SourceTab = "local" | "github" | "gitlab";

export default function HomePage() {
  const navigate = useNavigate();
  const [sourceTab, setSourceTab] = useState<SourceTab>("local");
  const [path, setPath] = useState("/workspace");
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [token, setToken] = useState("");
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<{ has_api_key: boolean; ollama_model: string } | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const project = await api.createProject({
        source: sourceTab,
        path: sourceTab === "local" ? path : undefined,
        url: sourceTab !== "local" ? url : undefined,
        branch: sourceTab !== "local" && branch ? branch : undefined,
        token: sourceTab !== "local" && token ? token : undefined,
      });
      setProjects((prev) => [project, ...prev.filter((p) => p.id !== project.id)]);
      navigate(`/project/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to index project");
    } finally {
      setLoading(false);
    }
  }

  function sourceIcon(s: string | undefined) {
    if (s === "github") return "GitHub";
    if (s === "gitlab") return "GitLab";
    return "Local";
  }

  return (
    <AppShell>
      <div className="home-layout">
        <section className="home-hero">
          <p className="eyebrow">Enterprise codebase intelligence</p>
          <h1>Understand, document, and assist across your repositories</h1>
          <p className="hero-lead">
            Index from a local path, GitHub, or GitLab. Explore architecture diagrams, search the code
            graph, chat with an evidence-backed agent, generate documentation, and build context packs for AI tools.
          </p>
          {health && (
            <div className="status-row">
              <span className={`status-chip ${health.has_api_key ? "ok" : "warn"}`}>
                {health.has_api_key ? "AI chat ready" : "Set OLLAMA_API_KEY for chat"}
              </span>
              <span className="status-chip neutral">Model: {health.ollama_model}</span>
            </div>
          )}
        </section>

        <section className="panel import-panel">
          <div className="panel-header">
            <h2>Import project</h2>
            <p>Choose a source and index the codebase into a searchable graph.</p>
          </div>

          <div className="source-tabs">
            {(["local", "github", "gitlab"] as SourceTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                className={`source-tab ${sourceTab === tab ? "active" : ""}`}
                onClick={() => setSourceTab(tab)}
              >
                {tab === "local" ? "Local directory" : tab === "github" ? "GitHub" : "GitLab"}
              </button>
            ))}
          </div>

          <form className="import-form" onSubmit={handleSubmit}>
            {sourceTab === "local" && (
              <div className="form-field">
                <label htmlFor="local-path">Directory path</label>
                <input
                  id="local-path"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder="/home/you/projects/my-app"
                  disabled={loading}
                />
                <span className="field-hint">Absolute path on the machine running Code-Buddy</span>
              </div>
            )}

            {sourceTab !== "local" && (
              <>
                <div className="form-field">
                  <label htmlFor="git-url">Repository URL or path</label>
                  <input
                    id="git-url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder={
                      sourceTab === "github"
                        ? "https://github.com/org/repo or org/repo"
                        : "https://gitlab.com/org/repo or org/repo"
                    }
                    disabled={loading}
                  />
                </div>
                <div className="form-row">
                  <div className="form-field">
                    <label htmlFor="git-branch">Branch</label>
                    <input
                      id="git-branch"
                      value={branch}
                      onChange={(e) => setBranch(e.target.value)}
                      placeholder="main"
                      disabled={loading}
                    />
                  </div>
                  <div className="form-field">
                    <label htmlFor="git-token">Access token (optional)</label>
                    <input
                      id="git-token"
                      type="password"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      placeholder="For private repositories"
                      disabled={loading}
                      autoComplete="off"
                    />
                  </div>
                </div>
              </>
            )}

            {error && <div className="alert alert-error">{error}</div>}

            <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
              {loading ? "Indexing repository…" : "Scan & index project"}
            </button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Recent projects</h2>
            <p>{projects.length} indexed workspace{projects.length !== 1 ? "s" : ""}</p>
          </div>

          {projects.length === 0 ? (
            <div className="empty-state">
              <p>No projects yet. Import a repository to get started.</p>
            </div>
          ) : (
            <div className="project-table-wrap">
              <table className="project-table">
                <thead>
                  <tr>
                    <th>Project</th>
                    <th>Source</th>
                    <th>Symbols</th>
                    <th>Modules</th>
                    <th>Framework</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <button type="button" className="table-link" onClick={() => navigate(`/project/${p.id}`)}>
                          <strong>{p.name}</strong>
                          <span className="table-sub">{p.source_url || p.path}</span>
                        </button>
                      </td>
                      <td><span className={`source-badge source-${p.source || "local"}`}>{sourceIcon(p.source)}</span></td>
                      <td>{p.stats?.symbols ?? 0}</td>
                      <td>{p.stats?.modules ?? 0}</td>
                      <td>{p.framework || "—"}</td>
                      <td>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate(`/project/${p.id}`)}>
                          Open
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="feature-grid">
          {[
            { title: "Architecture", desc: "System, module, and request-flow diagrams from code evidence." },
            { title: "Explorer", desc: "Search symbols, browse files, and jump to source with line precision." },
            { title: "Agent chat", desc: "Ask questions grounded in the graph with cited path:line evidence." },
            { title: "Documentation", desc: "Generate professional docs from org templates and export to repo." },
            { title: "Context packs", desc: "Compact prompts for Claude/Cursor — whole project or task-specific." },
          ].map((f) => (
            <article key={f.title} className="feature-card">
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </article>
          ))}
        </section>
      </div>
    </AppShell>
  );
}

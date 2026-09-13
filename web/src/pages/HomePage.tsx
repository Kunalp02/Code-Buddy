import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ProjectMeta } from "../api/client";

export default function HomePage() {
  const [path, setPath] = useState("/workspace");
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<{ has_api_key: boolean; ollama_model: string } | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  async function handleScan(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const project = await api.createProject(path);
      setProjects((prev) => [project, ...prev.filter((p) => p.id !== project.id)]);
      window.location.href = `/project/${project.id}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to index project");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="home-page">
      <header className="hero">
        <div className="hero-badge">Local-first codebase intelligence</div>
        <h1>Code-Buddy</h1>
        <p>
          Point at a local project path. Get a living architecture map, searchable code graph,
          and an AI agent powered by Ollama Cloud.
        </p>
      </header>

      <section className="card load-card">
        <h2>Load Project</h2>
        <form onSubmit={handleScan}>
          <label>
            Local project path
            <input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/home/you/projects/my-app"
              disabled={loading}
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Indexing…" : "Scan & Index"}
          </button>
        </form>
        {error && <div className="error-banner">{error}</div>}
        {health && (
          <div className="health-row">
            <span className={health.has_api_key ? "pill ok" : "pill warn"}>
              {health.has_api_key ? "Ollama API key configured" : "Set OLLAMA_API_KEY for chat"}
            </span>
            <span className="pill">Model: {health.ollama_model}</span>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Recent Projects</h2>
        {projects.length === 0 ? (
          <p className="muted">No projects indexed yet.</p>
        ) : (
          <div className="project-grid">
            {projects.map((p) => (
              <Link key={p.id} to={`/project/${p.id}`} className="project-card">
                <div className="project-card-title">{p.name}</div>
                <div className="project-card-path">{p.path}</div>
                <div className="project-card-meta">
                  <span>{p.stats?.symbols ?? 0} symbols</span>
                  <span>{p.stats?.modules ?? 0} modules</span>
                  <span>{p.framework || "unknown"}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

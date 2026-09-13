import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ProjectMeta } from "../api/client";
import AppShell from "../components/layout/AppShell";

type SourceTab = "local" | "github" | "gitlab";

interface GitHubRepo {
  id: number;
  name: string;
  full_name: string;
  owner: string;
  default_branch: string;
}

interface GitLabProject {
  id: number;
  name: string;
  path_with_namespace: string;
  default_branch: string;
}

export default function HomePage() {
  const navigate = useNavigate();
  const [sourceTab, setSourceTab] = useState<SourceTab>("local");
  const [path, setPath] = useState("/workspace");
  const [token, setToken] = useState("");
  const [gitlabHost, setGitlabHost] = useState("https://gitlab.com");
  const [githubRepos, setGithubRepos] = useState<GitHubRepo[]>([]);
  const [gitlabProjects, setGitlabProjects] = useState<GitLabProject[]>([]);
  const [branches, setBranches] = useState<string[]>([]);
  const [selectedGithubRepo, setSelectedGithubRepo] = useState("");
  const [selectedGitlabProject, setSelectedGitlabProject] = useState("");
  const [branch, setBranch] = useState("main");
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<{ has_api_key: boolean; ollama_model: string } | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  const selectedGh = githubRepos.find((r) => r.full_name === selectedGithubRepo);
  const selectedGl = gitlabProjects.find((p) => String(p.id) === selectedGitlabProject);

  async function connectRemote() {
    if (!token.trim()) {
      setError("Enter your personal access token first.");
      return;
    }
    setConnecting(true);
    setError(null);
    setBranches([]);
    try {
      if (sourceTab === "github") {
        const repos = await api.listGitHubRepos(token);
        setGithubRepos(repos);
        if (repos[0]) {
          setSelectedGithubRepo(repos[0].full_name);
          await loadGithubBranches(repos[0].owner, repos[0].name, repos[0].default_branch);
        }
      } else {
        const list = await api.listGitLabProjects(token, gitlabHost);
        setGitlabProjects(list);
        if (list[0]) {
          setSelectedGitlabProject(String(list[0].id));
          await loadGitlabBranches(list[0].id, list[0].default_branch);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect");
    } finally {
      setConnecting(false);
    }
  }

  async function loadGithubBranches(owner: string, repo: string, defaultBranch?: string) {
    const list = await api.listGitHubBranches(token, owner, repo);
    const names = list.map((b) => b.name);
    setBranches(names);
    setBranch(defaultBranch && names.includes(defaultBranch) ? defaultBranch : names[0] || "main");
  }

  async function loadGitlabBranches(projectId: number, defaultBranch?: string) {
    const list = await api.listGitLabBranches(token, projectId, gitlabHost);
    const names = list.map((b) => b.name);
    setBranches(names);
    setBranch(defaultBranch && names.includes(defaultBranch) ? defaultBranch : names[0] || "main");
  }

  async function onGithubRepoChange(fullName: string) {
    setSelectedGithubRepo(fullName);
    const r = githubRepos.find((x) => x.full_name === fullName);
    if (r && token) await loadGithubBranches(r.owner, r.name, r.default_branch);
  }

  async function onGitlabProjectChange(id: string) {
    setSelectedGitlabProject(id);
    const p = gitlabProjects.find((x) => String(x.id) === id);
    if (p && token) await loadGitlabBranches(p.id, p.default_branch);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      let body;
      if (sourceTab === "local") {
        body = { source: "local" as const, path };
      } else if (sourceTab === "github") {
        if (!selectedGh) throw new Error("Select a repository");
        body = {
          source: "github" as const,
          token,
          owner: selectedGh.owner,
          repo: selectedGh.name,
          url: `https://github.com/${selectedGh.full_name}`,
          branch,
        };
      } else {
        if (!selectedGl) throw new Error("Select a project");
        body = {
          source: "gitlab" as const,
          token,
          gitlab_project_id: selectedGl.id,
          gitlab_host: gitlabHost,
          url: selectedGl.path_with_namespace,
          branch,
        };
      }
      const project = await api.createProject(body);
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
            Import from a local path, GitHub, or GitLab. Remote repos are read via API — no git clone.
            Select a repository and branch, then index into a searchable graph.
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
            <p>Local path or connect with a token to browse repos and branches (read-only via API).</p>
          </div>

          <div className="source-tabs">
            {(["local", "github", "gitlab"] as SourceTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                className={`source-tab ${sourceTab === tab ? "active" : ""}`}
                onClick={() => {
                  setSourceTab(tab);
                  setError(null);
                  setBranches([]);
                }}
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
                <div className="api-read-banner">
                  <strong>Read-only via API</strong> — files are fetched from {sourceTab === "github" ? "GitHub" : "GitLab"} using your token.
                  Nothing is cloned. Your token is used only for this session and is not stored.
                </div>

                {sourceTab === "gitlab" && (
                  <div className="form-field">
                    <label htmlFor="gitlab-host">GitLab host</label>
                    <input
                      id="gitlab-host"
                      value={gitlabHost}
                      onChange={(e) => setGitlabHost(e.target.value)}
                      placeholder="https://gitlab.com"
                      disabled={loading}
                    />
                  </div>
                )}

                <div className="form-row">
                  <div className="form-field">
                    <label htmlFor="git-token">Personal access token</label>
                    <input
                      id="git-token"
                      type="password"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      placeholder={sourceTab === "github" ? "ghp_…" : "glpat-…"}
                      disabled={loading}
                      autoComplete="off"
                    />
                  </div>
                  <div className="form-field form-field-action">
                    <label>&nbsp;</label>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={connectRemote}
                      disabled={connecting || loading || !token.trim()}
                    >
                      {connecting ? "Connecting…" : "List repositories"}
                    </button>
                  </div>
                </div>

                {sourceTab === "github" && githubRepos.length > 0 && (
                  <div className="form-field">
                    <label htmlFor="gh-repo">Repository</label>
                    <select
                      id="gh-repo"
                      value={selectedGithubRepo}
                      onChange={(e) => onGithubRepoChange(e.target.value)}
                      disabled={loading}
                    >
                      {githubRepos.map((r) => (
                        <option key={r.id} value={r.full_name}>{r.full_name}</option>
                      ))}
                    </select>
                  </div>
                )}

                {sourceTab === "gitlab" && gitlabProjects.length > 0 && (
                  <div className="form-field">
                    <label htmlFor="gl-project">Project</label>
                    <select
                      id="gl-project"
                      value={selectedGitlabProject}
                      onChange={(e) => onGitlabProjectChange(e.target.value)}
                      disabled={loading}
                    >
                      {gitlabProjects.map((p) => (
                        <option key={p.id} value={String(p.id)}>{p.path_with_namespace}</option>
                      ))}
                    </select>
                  </div>
                )}

                {branches.length > 0 && (
                  <div className="form-field">
                    <label htmlFor="git-branch">Branch</label>
                    <select
                      id="git-branch"
                      value={branch}
                      onChange={(e) => setBranch(e.target.value)}
                      disabled={loading}
                    >
                      {branches.map((b) => (
                        <option key={b} value={b}>{b}</option>
                      ))}
                    </select>
                  </div>
                )}
              </>
            )}

            {error && <div className="alert alert-error">{error}</div>}

            <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
              {loading ? "Reading & indexing…" : "Scan & index project"}
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
                    <th>Branch</th>
                    <th>Symbols</th>
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
                      <td>{p.branch || "—"}</td>
                      <td>{p.stats?.symbols ?? 0}</td>
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
      </div>
    </AppShell>
  );
}

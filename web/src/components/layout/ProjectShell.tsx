import { Link } from "react-router-dom";
import { ProjectMeta } from "../../api/client";

export type ProjectTab = "diagram" | "explorer" | "chat" | "docs" | "context";

const NAV: { id: ProjectTab; label: string; desc: string }[] = [
  { id: "diagram", label: "Architecture", desc: "System & module diagrams" },
  { id: "explorer", label: "Explorer", desc: "Files, symbols, code" },
  { id: "chat", label: "Search", desc: "Codebase Q&A with citations" },
  { id: "docs", label: "Documentation", desc: "Reference docs & exports" },
  { id: "context", label: "Context Pack", desc: "Editor context blocks" },
];

interface Props {
  project: ProjectMeta;
  tab: ProjectTab;
  onTabChange: (tab: ProjectTab) => void;
  children: React.ReactNode;
}

function sourceLabel(project: ProjectMeta): string {
  const s = project.source || "local";
  if (s === "github") return "GitHub";
  if (s === "gitlab") return "GitLab";
  return "Local";
}

export default function ProjectShell({ project, tab, onTabChange, children }: Props) {
  return (
    <div className="project-shell">
      <aside className="project-sidebar">
        <Link to="/" className="sidebar-back">← All projects</Link>

        <div className="sidebar-project">
          <div className="sidebar-project-head">
            <h1>{project.name}</h1>
            <span className={`source-badge source-${project.source || "local"}`}>{sourceLabel(project)}</span>
          </div>
          <p className="sidebar-path" title={project.path}>{project.path}</p>
          {project.source_url && (
            <p className="sidebar-url" title={project.source_url}>{project.source_url}</p>
          )}
          {project.branch && (
            <p className="sidebar-branch">Branch: <strong>{project.branch}</strong></p>
          )}
          {project.read_mode === "api" && (
            <span className="read-mode-badge">Read via API · no clone</span>
          )}
        </div>

        <div className="sidebar-stats">
          <div className="sidebar-stat">
            <strong>{project.stats?.files_parsed ?? 0}</strong>
            <span>Files</span>
          </div>
          <div className="sidebar-stat">
            <strong>{project.stats?.symbols ?? 0}</strong>
            <span>Symbols</span>
          </div>
          <div className="sidebar-stat">
            <strong>{project.stats?.symbol_refs ?? 0}</strong>
            <span>Refs</span>
          </div>
          <div className="sidebar-stat">
            <strong>{project.stats?.routes ?? 0}</strong>
            <span>Routes</span>
          </div>
          <div className="sidebar-stat">
            <strong>{project.framework || "—"}</strong>
            <span>Stack</span>
          </div>
          {project.stats?.roslyn?.enabled && (
            <div className="sidebar-stat roslyn-badge">
              <strong>Roslyn</strong>
              <span>C# deep index</span>
            </div>
          )}
        </div>

        <nav className="sidebar-nav">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`sidebar-nav-item ${tab === item.id ? "active" : ""}`}
              onClick={() => onTabChange(item.id)}
            >
              <span className="sidebar-nav-label">{item.label}</span>
              <span className="sidebar-nav-desc">{item.desc}</span>
            </button>
          ))}
        </nav>
      </aside>

      <div className="project-main">
        <div className="project-workspace">{children}</div>
      </div>
    </div>
  );
}

export { NAV as PROJECT_NAV };

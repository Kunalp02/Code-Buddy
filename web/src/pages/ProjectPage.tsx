import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, DiagramData, EvidenceItem, ProjectMeta } from "../api/client";
import ChatPanel from "../components/ChatPanel";
import CodeViewer from "../components/CodeViewer";
import DiagramView from "../components/DiagramView";
import Explorer from "../components/Explorer";

type Tab = "explorer" | "diagram" | "chat";

export default function ProjectPage() {
  const { id = "" } = useParams();
  const [project, setProject] = useState<ProjectMeta | null>(null);
  const [tab, setTab] = useState<Tab>("diagram");
  const [diagram, setDiagram] = useState<DiagramData | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedLine, setSelectedLine] = useState<number>(1);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const p = await api.getProject(id);
      setProject(p);
      const d = await api.getSystemDiagram(id);
      setDiagram(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  function openFile(path: string, line = 1) {
    setSelectedFile(path);
    setSelectedLine(line);
    setTab("explorer");
  }

  function onEvidenceClick(item: EvidenceItem) {
    openFile(item.path, item.line || 1);
  }

  if (error) {
    return (
      <div className="project-page">
        <div className="error-banner">{error}</div>
        <Link to="/">← Back</Link>
      </div>
    );
  }

  if (!project) {
    return <div className="project-page loading-state">Loading project…</div>;
  }

  return (
    <div className="project-page">
      <header className="project-header">
        <div>
          <Link to="/" className="back-link">← Projects</Link>
          <h1>{project.name}</h1>
          <p className="project-path">{project.path}</p>
        </div>
        <div className="stats-row">
          <div className="stat"><strong>{project.stats?.files_parsed ?? 0}</strong><span>files</span></div>
          <div className="stat"><strong>{project.stats?.symbols ?? 0}</strong><span>symbols</span></div>
          <div className="stat"><strong>{project.stats?.modules ?? 0}</strong><span>modules</span></div>
          <div className="stat"><strong>{project.stats?.routes ?? 0}</strong><span>routes</span></div>
          <div className="stat"><strong>{project.framework || "—"}</strong><span>framework</span></div>
        </div>
      </header>

      <nav className="tab-bar">
        <button className={tab === "diagram" ? "active" : ""} onClick={() => setTab("diagram")}>Diagram</button>
        <button className={tab === "explorer" ? "active" : ""} onClick={() => setTab("explorer")}>Explorer</button>
        <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>Agent Chat</button>
      </nav>

      <div className="project-content">
        {tab === "diagram" && (
          <DiagramView
            projectId={id}
            diagram={diagram}
            onRefresh={async () => setDiagram(await api.getSystemDiagram(id))}
            onNodeClick={(node) => {
              if (node.file_path) openFile(node.file_path, node.start_line || node.line || 1);
              else if (node.path) {
                const files = project.entry_points || [];
                if (files[0]) openFile(files[0], 1);
              }
            }}
          />
        )}
        {tab === "explorer" && (
          <div className="explorer-layout">
            <Explorer projectId={id} selectedFile={selectedFile} onSelectFile={openFile} />
            <CodeViewer projectId={id} filePath={selectedFile} startLine={selectedLine} />
          </div>
        )}
        {tab === "chat" && (
          <ChatPanel
            projectId={id}
            onEvidenceClick={onEvidenceClick}
            onCodeRefClick={(path, line) => openFile(path, line || 1)}
          />
        )}
      </div>
    </div>
  );
}

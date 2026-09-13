import { useCallback, useEffect, useState } from "react";
import { api, streamDocumentation } from "../api/client";
import MarkdownMessage from "./MarkdownMessage";

interface Props {
  projectId: string;
  projectName: string;
  onCodeRefClick?: (path: string, line?: number) => void;
}

export default function DocsPanel({ projectId, projectName, onCodeRefClick }: Props) {
  const [content, setContent] = useState("");
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const loadExisting = useCallback(async () => {
    try {
      const doc = await api.getDocumentation(projectId);
      setContent(doc.content);
      setGeneratedAt(doc.generated_at || null);
      setError(null);
    } catch {
      setContent("");
      setGeneratedAt(null);
    }
  }, [projectId]);

  useEffect(() => {
    loadExisting();
  }, [loadExisting]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    setStatus("Gathering project context…");
    setContent("");

    try {
      await streamDocumentation(projectId, "default", (event) => {
        if (event.type === "meta") {
          setStatus(`Generating with ${event.model as string}…`);
        }
        if (event.type === "token") {
          setContent((prev) => prev + (event.content as string));
        }
        if (event.type === "saved") {
          setGeneratedAt(event.generated_at as string);
          setStatus(null);
        }
        if (event.type === "error") {
          setError(event.content as string);
          setStatus(null);
        }
        if (event.type === "done") {
          setGenerating(false);
          setStatus(null);
        }
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
      setGenerating(false);
      setStatus(null);
    }
  }

  function handleDownload() {
    if (!content) return;
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${projectName.replace(/\s+/g, "-").toLowerCase()}-documentation.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="docs-panel">
      <div className="docs-toolbar">
        <div className="docs-toolbar-info">
          <h3>Project Documentation</h3>
          <p className="docs-subtitle">
            Auto-generated professional docs from your indexed codebase
            {generatedAt && (
              <span className="docs-generated-at">
                · Last generated {new Date(generatedAt).toLocaleString()}
              </span>
            )}
          </p>
        </div>
        <div className="docs-actions">
          <button type="button" className="btn-secondary" onClick={handleDownload} disabled={!content}>
            Download .md
          </button>
          <button type="button" className="btn-primary" onClick={handleGenerate} disabled={generating}>
            {generating ? "Generating…" : content ? "Regenerate" : "Generate Documentation"}
          </button>
        </div>
      </div>

      {status && <div className="docs-status">{status}</div>}
      {error && <div className="error-banner docs-error">{error}</div>}

      <div className="docs-content">
        {content ? (
          <MarkdownMessage content={content} onCodeRefClick={onCodeRefClick} />
        ) : !generating ? (
          <div className="docs-empty">
            <p>No documentation yet.</p>
            <p className="docs-empty-hint">
              Click <strong>Generate Documentation</strong> to produce a brief, professional README-style
              document using the project template — architecture, setup, API routes, configuration, and more.
            </p>
          </div>
        ) : (
          <div className="docs-streaming">
            {content ? <MarkdownMessage content={content} onCodeRefClick={onCodeRefClick} /> : <p>Starting…</p>}
          </div>
        )}
      </div>
    </div>
  );
}

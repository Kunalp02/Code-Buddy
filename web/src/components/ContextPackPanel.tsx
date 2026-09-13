import { useState } from "react";
import { api } from "../api/client";

interface ContextPackResult {
  mode: string;
  content: string;
  char_count: number;
  estimated_tokens: number;
  max_chars: number;
  files_referenced?: string[];
  keywords?: string[];
  symbols_found?: number;
  routes_found?: number;
  project_name: string;
  task?: string;
}

interface Props {
  projectId: string;
  projectName: string;
}

type PackMode = "project" | "task";
type PackSize = "compact" | "standard" | "large";

export default function ContextPackPanel({ projectId, projectName }: Props) {
  const [mode, setMode] = useState<PackMode>("project");
  const [task, setTask] = useState("");
  const [size, setSize] = useState<PackSize>("standard");
  const [result, setResult] = useState<ContextPackResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleBuild() {
    if (mode === "task" && !task.trim()) {
      setError("Describe your task for a task-specific context pack.");
      return;
    }
    setLoading(true);
    setError(null);
    setCopied(false);
    try {
      const pack = await api.buildContextPack(projectId, {
        mode,
        task: mode === "task" ? task : undefined,
        size,
      });
      setResult(pack);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to build context pack");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleCopy() {
    if (!result?.content) return;
    await navigator.clipboard.writeText(result.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleDownload() {
    if (!result?.content) return;
    const blob = new Blob([result.content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const suffix = result.mode === "task" ? "task-context" : "project-context";
    a.download = `${projectName.replace(/\s+/g, "-").toLowerCase()}-${suffix}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="context-pack-panel">
      <div className="docs-toolbar">
        <div className="docs-toolbar-info">
          <h3>Context Pack Builder</h3>
          <p className="docs-subtitle">
            Build a compact, paste-ready prompt for Claude, Cursor, or any AI assistant — grounded in your indexed codebase.
          </p>
        </div>
        <div className="docs-actions">
          <button type="button" className="btn-secondary" onClick={handleDownload} disabled={!result}>
            Download
          </button>
          <button type="button" className="btn-secondary" onClick={handleCopy} disabled={!result}>
            {copied ? "Copied!" : "Copy to clipboard"}
          </button>
          <button type="button" className="btn-primary" onClick={handleBuild} disabled={loading}>
            {loading ? "Building…" : "Build Context Pack"}
          </button>
        </div>
      </div>

      <div className="context-pack-controls">
        <div className="pack-mode-toggle">
          <button
            type="button"
            className={mode === "project" ? "active" : ""}
            onClick={() => setMode("project")}
          >
            Whole project
          </button>
          <button
            type="button"
            className={mode === "task" ? "active" : ""}
            onClick={() => setMode("task")}
          >
            Task-specific
          </button>
        </div>

        <label className="docs-control">
          <span>Size budget</span>
          <select value={size} onChange={(e) => setSize(e.target.value as PackSize)}>
            <option value="compact">Compact (~2k tokens)</option>
            <option value="standard">Standard (~3.5k tokens)</option>
            <option value="large">Large (~5.5k tokens)</option>
          </select>
        </label>
      </div>

      {mode === "task" && (
        <div className="context-pack-task-input">
          <label>
            <span>Your task</span>
            <textarea
              value={task}
              onChange={(e) => setTask(e.target.value)}
              rows={4}
              placeholder="e.g. Add a POST /api/refunds endpoint that validates payment_id and calls RefundService, matching our existing payment routes..."
            />
          </label>
        </div>
      )}

      {mode === "project" && (
        <div className="context-pack-hint">
          <strong>Whole project mode</strong> — produces a compact overview: architecture, modules, routes, env vars,
          folder tree, README/config excerpts, and AI instructions. Ideal for onboarding or first message to Claude.
        </div>
      )}

      {error && <div className="error-banner docs-error">{error}</div>}

      {result && (
        <div className="context-pack-meta">
          <span>{result.char_count.toLocaleString()} chars</span>
          <span>~{result.estimated_tokens.toLocaleString()} tokens</span>
          {result.files_referenced && result.files_referenced.length > 0 && (
            <span>{result.files_referenced.length} files referenced</span>
          )}
          {result.mode === "task" && result.symbols_found != null && (
            <span>{result.symbols_found} symbols matched</span>
          )}
        </div>
      )}

      <div className="context-pack-preview">
        {result ? (
          <pre className="context-pack-raw">{result.content}</pre>
        ) : (
          <div className="docs-empty">
            <p>No context pack yet.</p>
            <p className="docs-empty-hint">
              Choose <strong>Whole project</strong> for a compact snapshot of the entire codebase, or{" "}
              <strong>Task-specific</strong> to get relevant files, routes, and patterns for one coding task.
              Then click <strong>Build Context Pack</strong> and paste into your AI tool.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

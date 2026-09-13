import { useCallback, useEffect, useState } from "react";
import { api, streamDocumentation } from "../api/client";
import MarkdownMessage from "./MarkdownMessage";

interface DocTemplate {
  id: string;
  name: string;
  filename: string;
  source: "builtin" | "custom";
}

interface Props {
  projectId: string;
  projectName: string;
  onCodeRefClick?: (path: string, line?: number) => void;
}

export default function DocsPanel({ projectId, projectName, onCodeRefClick }: Props) {
  const [content, setContent] = useState("");
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [exportedPath, setExportedPath] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [templates, setTemplates] = useState<DocTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("default");
  const [exportPath, setExportPath] = useState("DOCUMENTATION.md");
  const [showUpload, setShowUpload] = useState(false);
  const [uploadId, setUploadId] = useState("");
  const [uploadName, setUploadName] = useState("");
  const [uploadContent, setUploadContent] = useState("");
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const loadTemplates = useCallback(async () => {
    try {
      const list = await api.getDocTemplates();
      setTemplates(list);
      setSelectedTemplate((current) => (list.find((t) => t.id === current) ? current : list[0]?.id || "default"));
    } catch {
      setTemplates([{ id: "default", name: "Default", filename: "default.md", source: "builtin" }]);
    }
  }, []);

  const loadExisting = useCallback(async () => {
    try {
      const doc = await api.getDocumentation(projectId);
      setContent(doc.content);
      setGeneratedAt(doc.generated_at || null);
      setExportedPath(doc.exported_path || null);
      if (doc.template) setSelectedTemplate(doc.template);
      setError(null);
    } catch {
      setContent("");
      setGeneratedAt(null);
      setExportedPath(null);
    }
  }, [projectId]);

  useEffect(() => {
    loadTemplates();
    loadExisting();
  }, [loadTemplates, loadExisting]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    setStatus("Gathering project context…");
    setContent("");

    try {
      await streamDocumentation(projectId, selectedTemplate, (event) => {
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

  async function handleExport() {
    if (!content) return;
    setExporting(true);
    setError(null);
    try {
      const result = await api.exportDocumentation(projectId, exportPath);
      setExportedPath(result.relative_path);
      setStatus(`Saved to ${result.relative_path}`);
      setTimeout(() => setStatus(null), 4000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function handleUploadTemplate() {
    if (!uploadId.trim() || !uploadContent.trim()) {
      setError("Template id and content are required");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const saved = await api.uploadDocTemplate(uploadId, uploadContent, uploadName || undefined);
      await loadTemplates();
      setSelectedTemplate(saved.id);
      setShowUpload(false);
      setUploadId("");
      setUploadName("");
      setUploadContent("");
      setStatus(`Template "${saved.name}" uploaded`);
      setTimeout(() => setStatus(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteTemplate(templateId: string) {
    if (!confirm(`Delete custom template "${templateId}"?`)) return;
    try {
      await api.deleteDocTemplate(templateId);
      await loadTemplates();
      if (selectedTemplate === templateId) setSelectedTemplate("default");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function loadTemplatePreview(templateId: string) {
    try {
      const t = await api.getDocTemplate(templateId);
      setUploadContent(t.content);
      setUploadId(t.id);
      setUploadName(t.name);
      setShowUpload(true);
    } catch {
      /* ignore */
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

  const selectedMeta = templates.find((t) => t.id === selectedTemplate);

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
            {exportedPath && (
              <span className="docs-exported-at"> · Saved as {exportedPath}</span>
            )}
          </p>
        </div>
        <div className="docs-actions">
          <button type="button" className="btn-secondary" onClick={() => setShowUpload((v) => !v)}>
            {showUpload ? "Close" : "Templates"}
          </button>
          <button type="button" className="btn-secondary" onClick={handleDownload} disabled={!content}>
            Download
          </button>
          <button type="button" className="btn-primary" onClick={handleGenerate} disabled={generating}>
            {generating ? "Generating…" : content ? "Regenerate" : "Generate"}
          </button>
        </div>
      </div>

      <div className="docs-controls">
        <label className="docs-control">
          <span>Template</span>
          <select
            value={selectedTemplate}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            disabled={generating}
          >
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} {t.source === "custom" ? "(custom)" : ""}
              </option>
            ))}
          </select>
        </label>
        {selectedMeta?.source === "custom" && (
          <button
            type="button"
            className="btn-text-danger"
            onClick={() => handleDeleteTemplate(selectedMeta.id)}
          >
            Delete template
          </button>
        )}
        <label className="docs-control docs-export-path">
          <span>Save to project</span>
          <div className="docs-export-row">
            <input
              type="text"
              value={exportPath}
              onChange={(e) => setExportPath(e.target.value)}
              placeholder="DOCUMENTATION.md"
              disabled={exporting}
            />
            <button
              type="button"
              className="btn-secondary"
              onClick={handleExport}
              disabled={!content || exporting}
            >
              {exporting ? "Saving…" : "Save"}
            </button>
          </div>
        </label>
      </div>

      {showUpload && (
        <div className="docs-upload-panel">
          <h4>Upload custom template</h4>
          <p className="docs-upload-hint">
            Provide a Markdown template with section headings. Placeholders like [Project Name] will be
            filled from the indexed codebase.
          </p>
          <div className="docs-upload-fields">
            <label>
              Template ID
              <input
                type="text"
                value={uploadId}
                onChange={(e) => setUploadId(e.target.value)}
                placeholder="api-service"
              />
            </label>
            <label>
              Display name
              <input
                type="text"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                placeholder="API Service"
              />
            </label>
          </div>
          <label className="docs-upload-content-label">
            Template content
            <textarea
              value={uploadContent}
              onChange={(e) => setUploadContent(e.target.value)}
              rows={12}
              placeholder="# [Project Name]&#10;&#10;## Overview&#10;..."
            />
          </label>
          <div className="docs-upload-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => loadTemplatePreview(selectedTemplate)}
            >
              Load selected as starting point
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleUploadTemplate}
              disabled={uploading}
            >
              {uploading ? "Uploading…" : "Upload template"}
            </button>
          </div>
        </div>
      )}

      {status && <div className="docs-status">{status}</div>}
      {error && <div className="error-banner docs-error">{error}</div>}

      <div className="docs-content">
        {content ? (
          <MarkdownMessage content={content} onCodeRefClick={onCodeRefClick} />
        ) : !generating ? (
          <div className="docs-empty">
            <p>No documentation yet.</p>
            <p className="docs-empty-hint">
              Choose a template, then click <strong>Generate</strong> to produce professional documentation
              — architecture, setup, API routes, configuration, and more. Save the result into your project
              repo or download it as Markdown.
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

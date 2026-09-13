import { useCallback, useEffect, useState } from "react";
import { api, DocExportFormat, streamDocumentation } from "../api/client";
import MarkdownMessage from "./MarkdownMessage";

interface DocTemplate {
  id: string;
  name: string;
  filename: string;
  source: "builtin" | "custom";
}

type ContentView = "preview" | "edit";

interface Props {
  projectId: string;
  projectName: string;
  onCodeRefClick?: (path: string, line?: number) => void;
}

export default function DocsPanel({ projectId, onCodeRefClick }: Props) {
  const [content, setContent] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [editedAt, setEditedAt] = useState<string | null>(null);
  const [exportedPath, setExportedPath] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [templates, setTemplates] = useState<DocTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("default");
  const [exportPath, setExportPath] = useState("DOCUMENTATION");
  const [exportFormat, setExportFormat] = useState<DocExportFormat>("md");
  const [showUpload, setShowUpload] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadId, setUploadId] = useState("");
  const [uploadName, setUploadName] = useState("");
  const [uploadContent, setUploadContent] = useState("");
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [contentView, setContentView] = useState<ContentView>("preview");
  const [isDirty, setIsDirty] = useState(false);

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
      setDraftContent(doc.content);
      setGeneratedAt(doc.generated_at || null);
      setEditedAt(doc.edited_at || null);
      setExportedPath(doc.exported_path || null);
      if (doc.template) setSelectedTemplate(doc.template);
      setIsDirty(false);
      setError(null);
    } catch {
      setContent("");
      setDraftContent("");
      setGeneratedAt(null);
      setEditedAt(null);
      setExportedPath(null);
      setIsDirty(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadTemplates();
    loadExisting();
  }, [loadTemplates, loadExisting]);

  async function handleGenerate() {
    if (isDirty && !confirm("Regenerating will replace your current draft. Continue?")) {
      return;
    }
    setGenerating(true);
    setContentView("preview");
    setError(null);
    setStatus("Collecting project context…");
    setContent("");
    setDraftContent("");

    try {
      await streamDocumentation(projectId, selectedTemplate, (event) => {
        if (event.type === "meta") {
          setStatus("Writing documentation…");
        }
        if (event.type === "token") {
          const token = event.content as string;
          setContent((prev) => prev + token);
          setDraftContent((prev) => prev + token);
        }
        if (event.type === "saved") {
          setGeneratedAt(event.generated_at as string);
          setEditedAt(null);
          setStatus(null);
          loadExisting();
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

  function exportPathForFormat(path: string, format: DocExportFormat) {
    const base = path.replace(/\.(md|txt|docx|pdf)$/i, "");
    return `${base}.${format}`;
  }

  async function handleExport() {
    if (!content) return;
    setExporting(true);
    setError(null);
    try {
      const path = exportPathForFormat(exportPath, exportFormat);
      const result = await api.exportDocumentation(projectId, path, exportFormat);
      setExportedPath(result.relative_path);
      setStatus(`Saved to ${result.relative_path}`);
      setTimeout(() => setStatus(null), 4000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function handleSaveEdits() {
    if (!draftContent.trim()) {
      setError("Documentation cannot be empty");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const doc = await api.updateDocumentation(projectId, draftContent);
      setContent(doc.content);
      setDraftContent(doc.content);
      setEditedAt(doc.edited_at || null);
      setIsDirty(false);
      setContentView("preview");
      setStatus("Changes saved");
      setTimeout(() => setStatus(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function handleStartEditing() {
    setDraftContent(content);
    setContentView("edit");
    setIsDirty(false);
  }

  function handleCancelEditing() {
    if (isDirty && !confirm("Discard unsaved changes?")) return;
    setDraftContent(content);
    setIsDirty(false);
    setContentView("preview");
  }

  async function handleUploadTemplate() {
    if (!uploadId.trim()) {
      setError("Template id is required");
      return;
    }
    if (!uploadFile && !uploadContent.trim()) {
      setError("Choose a file or paste template content");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const saved = uploadFile
        ? await api.uploadDocTemplateFile(uploadId, uploadFile, uploadName || undefined)
        : await api.uploadDocTemplate(uploadId, uploadContent, uploadName || undefined);
      await loadTemplates();
      setSelectedTemplate(saved.id);
      setShowUpload(false);
      setUploadId("");
      setUploadName("");
      setUploadContent("");
      setUploadFile(null);
      setStatus(`Template "${saved.name}" saved`);
      setTimeout(() => setStatus(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleExportTemplate(format: DocExportFormat) {
    try {
      const { blob, filename } = await api.exportDocTemplate(selectedTemplate, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Template export failed");
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

  async function handleDownload() {
    if (!content) return;
    try {
      const { blob, filename } = await api.downloadDocumentation(projectId, exportFormat);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  }

  const selectedMeta = templates.find((t) => t.id === selectedTemplate);
  const displayContent = contentView === "edit" ? draftContent : content;
  const lastUpdated = editedAt || generatedAt;

  return (
    <div className="docs-panel">
      <div className="docs-toolbar">
        <div className="docs-toolbar-info">
          <h3>Documentation</h3>
          <p className="docs-subtitle">
            Reference documentation from your indexed codebase
            {lastUpdated && (
              <span className="docs-generated-at">
                · Updated {new Date(lastUpdated).toLocaleString()}
                {editedAt ? " (edited)" : ""}
              </span>
            )}
            {exportedPath && (
              <span className="docs-exported-at"> · Saved as {exportedPath}</span>
            )}
          </p>
        </div>
        <div className="docs-actions">
          <button type="button" className="btn btn-secondary" onClick={() => setShowUpload((v) => !v)}>
            {showUpload ? "Close" : "Templates"}
          </button>
          {content && contentView === "preview" && (
            <>
              <button type="button" className="btn btn-secondary" onClick={handleDownload}>
                Download
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleStartEditing}>
                Edit
              </button>
            </>
          )}
          {contentView === "edit" && (
            <>
              <button type="button" className="btn btn-secondary" onClick={handleCancelEditing} disabled={saving}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSaveEdits}
                disabled={saving || !isDirty}
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </>
          )}
          {contentView !== "edit" && (
            <button type="button" className="btn btn-primary" onClick={handleGenerate} disabled={generating}>
              {generating ? "Generating…" : content ? "Regenerate" : "Generate"}
            </button>
          )}
        </div>
      </div>

      <div className="docs-controls">
        <label className="docs-control">
          <span>Template</span>
          <select
            value={selectedTemplate}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            disabled={generating || contentView === "edit"}
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
            className="btn btn-ghost btn-sm btn-text-danger"
            onClick={() => handleDeleteTemplate(selectedMeta.id)}
          >
            Delete template
          </button>
        )}
        <label className="docs-control">
          <span>Format</span>
          <select
            value={exportFormat}
            onChange={(e) => setExportFormat(e.target.value as DocExportFormat)}
            disabled={generating || contentView === "edit"}
          >
            <option value="md">Markdown</option>
            <option value="txt">Plain text</option>
            <option value="docx">Word</option>
            <option value="pdf">PDF</option>
          </select>
        </label>
        <label className="docs-control docs-export-path">
          <span>Save to project</span>
          <div className="docs-export-row">
            <input
              type="text"
              value={exportPathForFormat(exportPath, exportFormat)}
              onChange={(e) => setExportPath(e.target.value.replace(/\.(md|txt|docx|pdf)$/i, ""))}
              placeholder="DOCUMENTATION.md"
              disabled={exporting || contentView === "edit"}
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleExport}
              disabled={!content || exporting || contentView === "edit"}
            >
              {exporting ? "Saving…" : "Save"}
            </button>
          </div>
        </label>
      </div>

      {showUpload && (
        <div className="docs-upload-panel">
          <h4>Templates</h4>
          <p className="docs-upload-hint">
            Import Markdown, text, Word, or PDF templates. Include{" "}
            <code>{`{{ARCHITECTURE_DIAGRAM}}`}</code> in the Architecture section to insert the system diagram.
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
            Import file
            <input
              type="file"
              accept=".md,.txt,.docx,.pdf,text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
          </label>
          <label className="docs-upload-content-label">
            Or paste Markdown
            <textarea
              value={uploadContent}
              onChange={(e) => setUploadContent(e.target.value)}
              rows={8}
              placeholder="# [Project Name]&#10;&#10;## Overview&#10;..."
            />
          </label>
          <div className="docs-upload-actions">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => loadTemplatePreview(selectedTemplate)}>
              Use selected template
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleExportTemplate("md")}>
              Export MD
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleExportTemplate("docx")}>
              Export DOCX
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleExportTemplate("pdf")}>
              Export PDF
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={handleUploadTemplate} disabled={uploading}>
              {uploading ? "Saving…" : "Save template"}
            </button>
          </div>
        </div>
      )}

      {status && <div className="docs-status">{status}</div>}
      {error && <div className="error-banner docs-error">{error}</div>}

      {content && contentView === "preview" && !generating && (
        <div className="docs-edit-banner">
          <span>Review the generated draft before exporting.</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={handleStartEditing}>
            Make changes
          </button>
        </div>
      )}

      <div className="docs-content">
        {contentView === "edit" ? (
          <div className="docs-editor-wrap">
            <label className="docs-editor-label" htmlFor="docs-editor">
              Edit documentation (Markdown)
            </label>
            <textarea
              id="docs-editor"
              className="docs-editor"
              value={draftContent}
              onChange={(e) => {
                setDraftContent(e.target.value);
                setIsDirty(e.target.value !== content);
              }}
              spellCheck={false}
            />
          </div>
        ) : displayContent ? (
          <MarkdownMessage content={displayContent} onCodeRefClick={onCodeRefClick} />
        ) : !generating ? (
          <div className="docs-empty">
            <p>No documentation yet.</p>
            <p className="docs-empty-hint">
              Select a template and run <strong>Generate</strong>. The Architecture section includes a system
              diagram from your indexed components. Review the draft, edit any section, then export to your
              repository or download in Markdown, Word, PDF, or plain text.
            </p>
          </div>
        ) : (
          <div className="docs-streaming">
            {displayContent ? (
              <MarkdownMessage content={displayContent} onCodeRefClick={onCodeRefClick} />
            ) : (
              <p className="docs-streaming-placeholder">Preparing draft…</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

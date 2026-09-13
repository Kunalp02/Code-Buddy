import { useEffect, useState } from "react";
import { api } from "../api/client";

interface Props {
  projectId: string;
  filePath: string | null;
  startLine?: number;
}

export default function CodeViewer({ projectId, filePath, startLine = 1 }: Props) {
  const [content, setContent] = useState<string>("");
  const [meta, setMeta] = useState<{ start_line: number; end_line: number; total_lines: number } | null>(null);

  useEffect(() => {
    if (!filePath) {
      setContent("");
      setMeta(null);
      return;
    }
    api
      .getSnippet(projectId, filePath, Math.max(1, startLine - 5))
      .then((data) => {
        setContent(data.content);
        setMeta({ start_line: data.start_line, end_line: data.end_line, total_lines: data.total_lines });
      })
      .catch(() => {
        setContent("Unable to load file.");
        setMeta(null);
      });
  }, [projectId, filePath, startLine]);

  if (!filePath) {
    return (
      <div className="code-viewer empty">
        <p>Select a file from the explorer or click a diagram node.</p>
      </div>
    );
  }

  const lines = content.split("\n");

  return (
    <div className="code-viewer">
      <div className="code-header">
        <span className="code-path">{filePath}</span>
        {meta && <span className="code-meta">Lines {meta.start_line}–{meta.end_line} of {meta.total_lines}</span>}
      </div>
      <pre className="code-block">
        {lines.map((line, i) => {
          const lineNo = (meta?.start_line || 1) + i;
          const highlight = lineNo === startLine;
          return (
            <div key={lineNo} className={`code-line ${highlight ? "highlight" : ""}`}>
              <span className="line-no">{lineNo}</span>
              <span className="line-text">{line}</span>
            </div>
          );
        })}
      </pre>
    </div>
  );
}

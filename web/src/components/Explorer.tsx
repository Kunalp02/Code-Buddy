import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

interface Props {
  projectId: string;
  selectedFile: string | null;
  onSelectFile: (path: string, line?: number) => void;
}

type ReferenceHit = {
  ref_kind: string;
  file_path: string;
  line: number;
  from_symbol?: string;
  from_kind?: string;
};

export default function Explorer({ projectId, selectedFile, onSelectFile }: Props) {
  const [files, setFiles] = useState<{ path: string; language: string }[]>([]);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<
    { id: number; name: string; kind: string; file_path: string; start_line: number }[]
  >([]);
  const [symbols, setSymbols] = useState<{ id: number; name: string; kind: string; start_line: number }[]>([]);
  const [activeSymbol, setActiveSymbol] = useState<{ id: number; name: string } | null>(null);
  const [references, setReferences] = useState<ReferenceHit[]>([]);
  const [refsLoading, setRefsLoading] = useState(false);

  useEffect(() => {
    api.getFiles(projectId).then(setFiles).catch(() => setFiles([]));
  }, [projectId]);

  useEffect(() => {
    if (!search.trim()) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      api.search(projectId, search).then(setResults).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [projectId, search]);

  useEffect(() => {
    if (!selectedFile) {
      setSymbols([]);
      setActiveSymbol(null);
      setReferences([]);
      return;
    }
    api.getSymbols(projectId, selectedFile).then(setSymbols).catch(() => setSymbols([]));
    setActiveSymbol(null);
    setReferences([]);
  }, [projectId, selectedFile]);

  async function loadReferences(symbol: { id: number; name: string }) {
    setActiveSymbol(symbol);
    setRefsLoading(true);
    try {
      const data = await api.findReferences(projectId, String(symbol.id));
      setReferences(data.references);
    } catch {
      setReferences([]);
    } finally {
      setRefsLoading(false);
    }
  }

  const tree = useMemo(() => {
    const root: Record<string, unknown> = {};
    for (const file of files) {
      const parts = file.path.split("/");
      let node = root;
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        if (i === parts.length - 1) {
          (node as Record<string, string>)["__file__" + part] = file.path;
        } else {
          if (!node[part]) node[part] = {};
          node = node[part] as Record<string, unknown>;
        }
      }
    }
    return root;
  }, [files]);

  return (
    <aside className="explorer-panel">
      <div className="explorer-search">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search symbols…"
        />
      </div>

      {results.length > 0 && (
        <div className="search-results">
          {results.map((r) => (
            <button
              key={r.id}
              className="search-result"
              onClick={() => onSelectFile(r.file_path, r.start_line)}
            >
              <span className="sym-name">{r.name}</span>
              <span className="sym-kind">{r.kind}</span>
              <span className="sym-path">{r.file_path}:{r.start_line}</span>
            </button>
          ))}
        </div>
      )}

      <div className="file-tree">
        <TreeNode node={tree} path="" selectedFile={selectedFile} onSelectFile={onSelectFile} />
      </div>

      {selectedFile && symbols.length > 0 && (
        <div className="symbol-list">
          <h4>Symbols</h4>
          {symbols.map((s) => (
            <div key={s.id} className="symbol-row">
              <button
                className={`symbol-item ${activeSymbol?.id === s.id ? "active" : ""}`}
                onClick={() => onSelectFile(selectedFile, s.start_line)}
              >
                <span>{s.name}</span>
                <span>{s.kind}</span>
              </button>
              <button
                type="button"
                className="symbol-refs-btn"
                title={`Find references to ${s.name}`}
                onClick={() => loadReferences(s)}
              >
                →
              </button>
            </div>
          ))}
        </div>
      )}

      {activeSymbol && (
        <div className="references-panel">
          <h4>
            References to <code>{activeSymbol.name}</code>
            {refsLoading && <span className="refs-loading"> …</span>}
          </h4>
          {!refsLoading && references.length === 0 && (
            <p className="refs-empty">No references found in index.</p>
          )}
          {references.map((ref, i) => (
            <button
              key={`${ref.file_path}:${ref.line}:${i}`}
              className="search-result ref-hit"
              onClick={() => onSelectFile(ref.file_path, ref.line)}
            >
              <span className="sym-name">{ref.from_symbol || "usage"}</span>
              <span className="sym-kind">{ref.ref_kind}</span>
              <span className="sym-path">{ref.file_path}:{ref.line}</span>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}

function TreeNode({
  node,
  path,
  selectedFile,
  onSelectFile,
}: {
  node: Record<string, unknown>;
  path: string;
  selectedFile: string | null;
  onSelectFile: (path: string) => void;
}) {
  const entries = Object.entries(node).sort(([a], [b]) => {
    const aFile = a.startsWith("__file__");
    const bFile = b.startsWith("__file__");
    if (aFile && !bFile) return 1;
    if (!aFile && bFile) return -1;
    return a.localeCompare(b);
  });

  return (
    <ul className="tree-list">
      {entries.map(([key, value]) => {
        if (key.startsWith("__file__")) {
          const filePath = value as string;
          const name = key.replace("__file__", "");
          return (
            <li key={filePath}>
              <button
                className={`tree-file ${selectedFile === filePath ? "selected" : ""}`}
                onClick={() => onSelectFile(filePath)}
              >
                {name}
              </button>
            </li>
          );
        }
        const childPath = path ? `${path}/${key}` : key;
        return (
          <li key={childPath}>
            <div className="tree-folder">{key}</div>
            <TreeNode
              node={value as Record<string, unknown>}
              path={childPath}
              selectedFile={selectedFile}
              onSelectFile={onSelectFile}
            />
          </li>
        );
      })}
    </ul>
  );
}

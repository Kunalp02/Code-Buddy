import { DiagramNode } from "../../api/client";

interface Props {
  node: DiagramNode | null;
  onOpenCode?: (path: string, line?: number) => void;
}

export default function DiagramInspector({ node, onOpenCode }: Props) {
  if (!node) {
    return (
      <aside className="diagram-inspector empty">
        <h4>Module Inspector</h4>
        <p>Click any node to see details and jump to code.</p>
      </aside>
    );
  }

  const filePath = node.file_path || (node.path && node.id !== "__system__" ? findFileInModule(node.path) : null);

  return (
    <aside className="diagram-inspector">
      <div className="inspector-layer" style={{ color: node.color || "#818cf8" }}>
        {(node.layer || node.type || "module").toUpperCase()}
      </div>
      <h3>{node.label}</h3>
      {node.path && node.id !== "__system__" && <p className="inspector-path">{node.path}</p>}
      {node.description && <p className="inspector-desc">{node.description}</p>}

      <div className="inspector-stats">
        {node.file_count != null && <div><strong>{node.file_count}</strong><span>Files</span></div>}
        {node.symbol_count != null && <div><strong>{node.symbol_count}</strong><span>Symbols</span></div>}
        {node.route_count != null && <div><strong>{node.route_count}</strong><span>Routes</span></div>}
        {node.hub_score != null && node.hub_score > 0 && (
          <div><strong>{node.hub_score}</strong><span>Connections</span></div>
        )}
      </div>

      {node.is_hub && <div className="inspector-tag">Central hub — many dependencies flow through here</div>}

      {filePath && onOpenCode && (
        <button className="inspector-btn" onClick={() => onOpenCode(filePath, node.start_line || node.line || 1)}>
          Open in Explorer →
        </button>
      )}
    </aside>
  );
}

function findFileInModule(modulePath: string): string {
  return modulePath.includes(".") ? modulePath : `${modulePath}/`;
}

import { CSSProperties, memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { DiagramNode } from "../../api/client";

const LAYER_ICONS: Record<string, string> = {
  system: "◈",
  presentation: "▣",
  api: "⬡",
  security: "⬢",
  auth: "🔐",
  core: "◆",
  domain: "◆",
  orm: "⬢",
  shared: "◇",
  data: "▤",
  database: "🗄",
  cache: "⚡",
  queue: "📨",
  storage: "📦",
  search: "🔍",
  config: "⚙",
  test: "✓",
  module: "□",
  external: "◎",
  route: "⇢",
  function: "ƒ",
  container: "🐳",
  proxy: "⇄",
};

type NodeData = {
  node: DiagramNode;
};

function ArchitectureNode({ data, selected }: NodeProps & { data: NodeData }) {
  const n = data.node;
  const layer = n.layer || n.type || "module";
  const icon = LAYER_ICONS[layer] || LAYER_ICONS.module;
  const color = n.color || "#6366f1";

  return (
    <div
      className={`arch-node ${selected ? "selected" : ""} ${n.is_hub ? "hub" : ""}`}
      style={{ "--node-accent": color } as CSSProperties}
    >
      <Handle type="target" position={Position.Top} className="arch-handle" />
      <div className="arch-node-glow" />
      <div className="arch-node-header">
        <span className="arch-node-icon">{icon}</span>
        <span className="arch-node-layer">{layer}</span>
        {n.is_hub && <span className="arch-node-badge hub-badge">hub</span>}
      </div>
      <div className="arch-node-title">{n.label}</div>
      {n.path && n.id !== "__system__" && <div className="arch-node-path">{n.path}</div>}
      <div className="arch-node-stats">
        {n.technology && n.layer !== "module" && <span>{n.technology}</span>}
        {n.file_count != null && n.file_count > 0 && <span>{n.file_count} files</span>}
        {n.symbol_count != null && n.symbol_count > 0 && <span>{n.symbol_count} sym</span>}
        {n.route_count != null && n.route_count > 0 && <span>{n.route_count} routes</span>}
      </div>
      <Handle type="source" position={Position.Bottom} className="arch-handle" />
    </div>
  );
}

export default memo(ArchitectureNode);

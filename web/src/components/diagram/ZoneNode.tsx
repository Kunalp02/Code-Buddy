import { CSSProperties, memo } from "react";
import { type NodeProps } from "@xyflow/react";
import { DiagramNode } from "../../api/client";

type NodeData = {
  node: DiagramNode;
};

function ZoneNode({ data }: NodeProps & { data: NodeData }) {
  const n = data.node;
  const color = n.color || "#6366f1";

  return (
    <div
      className="zone-node"
      style={
        {
          "--zone-accent": color,
          width: n.width || 240,
          height: n.height || 200,
        } as CSSProperties
      }
    >
      <div className="zone-node-label">{n.label}</div>
    </div>
  );
}

export default memo(ZoneNode);

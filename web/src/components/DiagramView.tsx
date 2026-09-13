import { useCallback, useEffect } from "react";
import {
  Background,
  Controls,
  Edge,
  MarkerType,
  MiniMap,
  Node,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { api, DiagramData, DiagramNode } from "../api/client";

interface Props {
  projectId: string;
  diagram: DiagramData | null;
  onRefresh: () => void;
  onNodeClick: (node: DiagramNode) => void;
}

const NODE_WIDTH = 180;
const NODE_HEIGHT = 64;

function layoutDiagram(diagram: DiagramData) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 100 });

  for (const node of diagram.nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of diagram.edges) {
    g.setEdge(edge.source, edge.target);
  }
  dagre.layout(g);

  const nodes: Node[] = diagram.nodes.map((n) => {
    const pos = g.node(n.id);
    const x = pos ? pos.x - NODE_WIDTH / 2 : n.position.x;
    const y = pos ? pos.y - NODE_HEIGHT / 2 : n.position.y;
    return {
      id: n.id,
      position: { x, y },
      data: { label: `${n.label}\n${n.file_count ?? 0} files`, node: n },
      style: {
        width: NODE_WIDTH,
        borderRadius: 12,
        border: "1px solid rgba(99, 102, 241, 0.35)",
        background: n.type === "external" ? "#1e293b" : "#111827",
        color: "#f8fafc",
        fontSize: 12,
        fontWeight: 600,
        padding: 10,
        boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
      },
    };
  });

  const edges: Edge[] = diagram.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label,
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, color: "#818cf8" },
    style: { stroke: "#818cf8", strokeWidth: 2 },
    labelStyle: { fill: "#cbd5e1", fontSize: 10 },
  }));

  return { nodes, edges };
}

export default function DiagramView({ projectId, diagram, onRefresh, onNodeClick }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (!diagram) return;
    const laid = layoutDiagram(diagram);
    setNodes(laid.nodes);
    setEdges(laid.edges);
  }, [diagram, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const data = node.data as { node?: DiagramNode };
      if (data.node) onNodeClick(data.node);
    },
    [onNodeClick]
  );

  async function loadL3() {
    const d = await api.getL3Diagram(projectId);
    const laid = layoutDiagram(d);
    setNodes(laid.nodes);
    setEdges(laid.edges);
  }

  if (!diagram) {
    return <div className="diagram-view loading-state">Loading diagram…</div>;
  }

  return (
    <div className="diagram-view">
      <div className="diagram-toolbar">
        <div>
          <h3>{diagram.level} Architecture Map</h3>
          <p>{diagram.summary}</p>
        </div>
        <div className="diagram-actions">
          <button onClick={onRefresh}>Refresh L1</button>
          <button onClick={loadL3}>Show Route Flow (L3)</button>
        </div>
      </div>
      <div className="diagram-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          fitView
          minZoom={0.2}
          maxZoom={1.5}
        >
          <Background color="#334155" gap={20} />
          <MiniMap nodeColor="#6366f1" maskColor="rgba(15,23,42,0.75)" />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
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
import { api, DiagramData, DiagramNode } from "../api/client";
import ArchitectureNode from "./diagram/ArchitectureNode";
import DiagramInspector from "./diagram/DiagramInspector";
import ZoneNode from "./diagram/ZoneNode";

interface Props {
  projectId: string;
  diagram: DiagramData | null;
  onRefresh: () => void;
  onNodeClick: (node: DiagramNode) => void;
}

const nodeTypes = { architecture: ArchitectureNode, zone: ZoneNode };

const LAYER_RANK: Record<string, number> = {
  external: 0,
  system: 0,
  presentation: 1,
  api: 1,
  route: 2,
  auth: 2,
  security: 2,
  orm: 3,
  service: 3,
  core: 3,
  domain: 3,
  function: 4,
  shared: 4,
  module: 4,
  database: 5,
  data: 5,
  cache: 5,
  queue: 5,
  storage: 5,
  search: 5,
  config: 6,
  test: 7,
};

const NODE_W = 220;
const COL_GAP = 48;
const ROW_GAP = 140;

function layoutSystemFlow(diagram: DiagramData): { nodes: Node[]; edges: Edge[] } {
  const flowNodes: Node[] = diagram.nodes.map((n) => {
    const isZone = n.type === "zone";
    return {
      id: n.id,
      type: isZone ? "zone" : "architecture",
      position: n.position,
      parentId: n.parentId || undefined,
      extent: n.parentId ? ("parent" as const) : undefined,
      draggable: false,
      selectable: !isZone,
      style: isZone ? { width: n.width, height: n.height, zIndex: 0 } : { zIndex: 1 },
      data: { node: n },
    };
  });

  const maxWeight = Math.max(...diagram.edges.map((e) => e.weight || 1), 1);

  const flowEdges: Edge[] = diagram.edges.map((e) => {
    const weight = e.weight || 1;
    const strokeWidth = 1.5 + (weight / maxWeight) * 2.5;
    const isFlow = e.edge_type === "flow";

    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label,
      type: "smoothstep",
      animated: isFlow,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: isFlow ? "#2563eb" : "rgba(100,116,139,0.7)",
        width: 18,
        height: 18,
      },
      style: {
        stroke: isFlow ? "#2563eb" : "rgba(100,116,139,0.55)",
        strokeWidth,
        strokeDasharray: isFlow ? undefined : "6 4",
      },
      labelStyle: { fill: "#475569", fontSize: 11, fontWeight: 600 },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.95 },
      labelBgPadding: [6, 4] as [number, number],
      labelBgBorderRadius: 4,
    };
  });

  return { nodes: flowNodes, edges: flowEdges };
}

function layoutLayered(diagram: DiagramData): { nodes: Node[]; edges: Edge[] } {
  const byLayer = new Map<string, DiagramNode[]>();
  for (const node of diagram.nodes) {
    const layer = node.layer || node.type || "module";
    if (!byLayer.has(layer)) byLayer.set(layer, []);
    byLayer.get(layer)!.push(node);
  }

  const layers = [...byLayer.keys()].sort(
    (a, b) => (LAYER_RANK[a] ?? 4) - (LAYER_RANK[b] ?? 4)
  );

  const flowNodes: Node[] = [];
  layers.forEach((layer, rowIdx) => {
    const row = byLayer.get(layer)!;
    const rowWidth = row.length * NODE_W + (row.length - 1) * COL_GAP;
    const startX = -rowWidth / 2 + NODE_W / 2;

    row.forEach((n, colIdx) => {
      flowNodes.push({
        id: n.id,
        type: "architecture",
        position: {
          x: startX + colIdx * (NODE_W + COL_GAP),
          y: rowIdx * ROW_GAP,
        },
        data: { node: n },
      });
    });
  });

  const maxWeight = Math.max(...diagram.edges.map((e) => e.weight || 1), 1);

  const flowEdges: Edge[] = diagram.edges.map((e) => {
    const weight = e.weight || 1;
    const strokeWidth = 1.5 + (weight / maxWeight) * 3;
    const isFlow = e.edge_type === "flow" || diagram.layout === "flow";
    const isSystem = e.edge_type === "system";

    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label,
      type: isFlow ? "smoothstep" : "default",
      animated: isFlow || weight >= 2,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: isSystem ? "rgba(148,163,184,0.6)" : "#818cf8",
        width: 18,
        height: 18,
      },
      style: {
        stroke: isSystem ? "rgba(148,163,184,0.45)" : `rgba(129, 140, 248, ${0.4 + weight / maxWeight * 0.6})`,
        strokeWidth,
        strokeDasharray: isSystem ? "6 4" : undefined,
      },
      labelStyle: { fill: "#94a3b8", fontSize: 10, fontWeight: 500 },
      labelBgStyle: { fill: "rgba(15,23,42,0.85)", fillOpacity: 0.9 },
      labelBgPadding: [6, 4] as [number, number],
      labelBgBorderRadius: 4,
    };
  });

  return { nodes: flowNodes, edges: flowEdges };
}

export default function DiagramView({ projectId, diagram, onNodeClick }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selected, setSelected] = useState<DiagramNode | null>(null);
  const [viewMode, setViewMode] = useState<"system" | "modules" | "flow">("system");
  const [currentDiagram, setCurrentDiagram] = useState<DiagramData | null>(diagram);
  const [routes, setRoutes] = useState<{ method: string; path: string }[]>([]);
  const [selectedRoute, setSelectedRoute] = useState<string>("");

  useEffect(() => {
    setCurrentDiagram(diagram);
    if (diagram) applyDiagram(diagram);
  }, [diagram]);

  useEffect(() => {
    api.getRoutes(projectId).then((r) => {
      setRoutes(r.map((x) => ({ method: x.method || "GET", path: x.path })));
      if (r[0]) setSelectedRoute(r[0].path);
    }).catch(() => setRoutes([]));
  }, [projectId]);

  function applyDiagram(d: DiagramData) {
    const laid = d.layout === "system-flow" ? layoutSystemFlow(d) : layoutLayered(d);
    setNodes(laid.nodes);
    setEdges(laid.edges);
    setCurrentDiagram(d);
  }

  const legend = useMemo(() => currentDiagram?.legend || [], [currentDiagram]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const data = node.data as { node?: DiagramNode };
      if (data.node) {
        setSelected(data.node);
        if (data.node.file_path || data.node.path) onNodeClick(data.node);
      }
    },
    [onNodeClick]
  );

  async function loadFlow(route?: string) {
    const d = await api.getL3Diagram(projectId, route || selectedRoute);
    applyDiagram(d);
    setViewMode("flow");
  }

  async function loadSystem() {
    const d = await api.getSystemDiagram(projectId);
    applyDiagram(d);
    setViewMode("system");
  }

  async function loadModules() {
    const d = await api.getL1Diagram(projectId);
    applyDiagram(d);
    setViewMode("modules");
  }

  if (!currentDiagram) {
    return <div className="diagram-view loading-state">Loading diagram…</div>;
  }

  return (
    <div className="diagram-view">
      <div className="diagram-toolbar">
        <div>
          <h3>
            {viewMode === "system" ? "System Architecture" : viewMode === "modules" ? "Module Map" : "Request Flow"}
            <span className="diagram-level">{currentDiagram.level}</span>
          </h3>
          <p>{currentDiagram.summary}</p>
        </div>
        <div className="diagram-actions">
          <button type="button" className={`btn btn-secondary btn-sm ${viewMode === "system" ? "active" : ""}`} onClick={loadSystem}>
            System
          </button>
          <button type="button" className={`btn btn-secondary btn-sm ${viewMode === "modules" ? "active" : ""}`} onClick={loadModules}>
            Modules
          </button>
          {routes.length > 0 && (
            <>
              <select
                value={selectedRoute}
                onChange={(e) => setSelectedRoute(e.target.value)}
                className="route-select"
              >
                {routes.map((r) => (
                  <option key={r.path} value={r.path}>{r.method} {r.path}</option>
                ))}
              </select>
              <button type="button" className={`btn btn-secondary btn-sm ${viewMode === "flow" ? "active" : ""}`} onClick={() => loadFlow()}>
                Request flow
              </button>
            </>
          )}
        </div>
      </div>

      {legend.length > 0 && viewMode !== "flow" && (
        <div className="diagram-legend">
          {legend.map((item) => (
            <span key={item.layer} className="legend-item">
              <span className="legend-dot" style={{ background: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      )}

      <div className="diagram-body">
        <div className="diagram-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            onPaneClick={() => setSelected(null)}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.15}
            maxZoom={1.8}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} color="#cbd5e1" gap={20} size={1} />
            <MiniMap
              nodeColor={(n) => (n.data as { node?: DiagramNode })?.node?.color || "#2563eb"}
              maskColor="rgba(248,250,252,0.85)"
              pannable
              zoomable
            />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <DiagramInspector
          node={selected}
          onOpenCode={(path, line) => {
            if (selected) {
              onNodeClick(selected);
            } else {
              onNodeClick({
                id: path,
                label: path.split("/").pop() || path,
                type: "module",
                path,
                file_path: path,
                start_line: line,
                position: { x: 0, y: 0 },
              });
            }
          }}
        />
      </div>
    </div>
  );
}

export interface ProjectMeta {
  id: string;
  path: string;
  name: string;
  status: string;
  framework?: string;
  indexed_at?: string;
  entry_points?: string[];
  stats?: {
    files_total: number;
    files_parsed: number;
    symbols: number;
    modules: number;
    routes: number;
    languages: Record<string, number>;
  };
}

export interface DiagramNode {
  id: string;
  type: string;
  label: string;
  path?: string;
  file_path?: string;
  line?: number;
  start_line?: number;
  file_count?: number;
  position: { x: number; y: number };
}

export interface DiagramEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  weight?: number;
}

export interface DiagramData {
  level: string;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  summary: string;
}

export interface EvidenceItem {
  type: string;
  label: string;
  path: string;
  line?: number;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; has_api_key: boolean; ollama_model: string }>("/api/health"),
  listProjects: () => request<ProjectMeta[]>("/api/projects"),
  createProject: (path: string) =>
    request<ProjectMeta>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    }),
  getProject: (id: string) => request<ProjectMeta & { progress?: unknown }>(`/api/projects/${id}`),
  getFiles: (id: string) => request<{ path: string; language: string; line_count: number }[]>(`/api/projects/${id}/files`),
  search: (id: string, q: string) =>
    request<
      {
        id: number;
        name: string;
        kind: string;
        start_line: number;
        end_line: number;
        file_path: string;
      }[]
    >(`/api/projects/${id}/search?q=${encodeURIComponent(q)}`),
  getSnippet: (id: string, path: string, start = 1) =>
    request<{ path: string; start_line: number; end_line: number; content: string; total_lines: number }>(
      `/api/projects/${id}/snippet?path=${encodeURIComponent(path)}&start=${start}`
    ),
  getSymbols: (id: string, path: string) =>
    request<{ id: number; name: string; kind: string; start_line: number }[]>(
      `/api/projects/${id}/symbols?path=${encodeURIComponent(path)}`
    ),
  getRoutes: (id: string) =>
    request<{ method: string; path: string; file_path: string; line: number }[]>(`/api/projects/${id}/routes`),
  getModules: (id: string) =>
    request<{ modules: { path: string; name: string; file_count: number }[]; dependencies: unknown[] }>(
      `/api/projects/${id}/modules`
    ),
  getL1Diagram: (id: string) => request<DiagramData>(`/api/projects/${id}/diagrams/l1`),
  getL3Diagram: (id: string, route?: string) =>
    request<DiagramData>(`/api/projects/${id}/diagrams/l3${route ? `?route=${encodeURIComponent(route)}` : ""}`),
};

export async function streamChat(
  projectId: string,
  message: string,
  sessionId: string | null,
  onEvent: (event: Record<string, unknown>) => void
) {
  const res = await fetch(`/api/projects/${projectId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(await res.text());
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      onEvent(JSON.parse(line));
    }
  }
}

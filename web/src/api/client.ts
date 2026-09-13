export type ProjectSource = "local" | "github" | "gitlab";

export interface ProjectMeta {
  id: string;
  path: string;
  name: string;
  status: string;
  source?: ProjectSource;
  source_url?: string;
  branch?: string;
  read_mode?: string;
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
  symbol_count?: number;
  route_count?: number;
  fan_in?: number;
  fan_out?: number;
  hub_score?: number;
  is_hub?: boolean;
  layer?: string;
  color?: string;
  description?: string;
  technology?: string;
  parentId?: string | null;
  width?: number;
  height?: number;
  flow_handles?: "lr" | "tb";
  position: { x: number; y: number };
}

export interface DiagramEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  weight?: number;
  edge_type?: string;
}

export interface DiagramCluster {
  id: string;
  label: string;
  layer: string;
  color: string;
  modules: string[];
}

export interface DiagramLegendItem {
  layer: string;
  label: string;
  color: string;
}

export interface DiagramData {
  level: string;
  layout?: string;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  clusters?: DiagramCluster[];
  legend?: DiagramLegendItem[];
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
  listGitHubRepos: (token: string) =>
    request<
      {
        id: number;
        name: string;
        full_name: string;
        owner: string;
        default_branch: string;
        private: boolean;
        html_url: string;
      }[]
    >("/api/integrations/github/repos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }),
  listGitHubBranches: (token: string, owner: string, repo: string) =>
    request<{ name: string; sha: string }[]>("/api/integrations/github/branches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, owner, repo }),
    }),
  listGitLabProjects: (token: string, host = "https://gitlab.com") =>
    request<
      {
        id: number;
        name: string;
        path_with_namespace: string;
        default_branch: string;
        web_url: string;
      }[]
    >("/api/integrations/gitlab/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, host }),
    }),
  listGitLabBranches: (token: string, projectId: number, host = "https://gitlab.com") =>
    request<{ name: string; sha: string }[]>("/api/integrations/gitlab/branches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, project_id: projectId, host }),
    }),
  createProject: (body: {
    source: ProjectSource;
    path?: string;
    url?: string;
    branch?: string;
    token?: string;
    owner?: string;
    repo?: string;
    gitlab_project_id?: number;
    gitlab_host?: string;
  }) =>
    request<ProjectMeta>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
  getSystemDiagram: (id: string) => request<DiagramData>(`/api/projects/${id}/diagrams/system`),
  getL1Diagram: (id: string) => request<DiagramData>(`/api/projects/${id}/diagrams/l1`),
  getL3Diagram: (id: string, route?: string) =>
    request<DiagramData>(`/api/projects/${id}/diagrams/l3${route ? `?route=${encodeURIComponent(route)}` : ""}`),
  getArchitecture: (id: string) => request<Record<string, unknown>>(`/api/projects/${id}/architecture`),
  getDocumentation: (id: string) =>
    request<{
      content: string;
      generated_at?: string;
      edited_at?: string;
      template?: string;
      model?: string;
      exported_path?: string;
      exported_format?: string;
    }>(`/api/projects/${id}/documentation`),
  updateDocumentation: (projectId: string, content: string) =>
    request<{
      content: string;
      generated_at?: string;
      edited_at?: string;
      template?: string;
      model?: string;
      exported_path?: string;
    }>(`/api/projects/${projectId}/documentation`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }),
  getDocTemplates: () =>
    request<{ id: string; name: string; filename: string; source: "builtin" | "custom" }[]>(
      "/api/documentation/templates"
    ),
  getDocTemplate: (id: string) =>
    request<{ id: string; name: string; content: string; source: string }>(`/api/documentation/templates/${id}`),
  uploadDocTemplate: (id: string, content: string, name?: string) =>
    request<{ id: string; name: string; source: string; format?: string }>("/api/documentation/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, content, name }),
    }),
  uploadDocTemplateFile: async (id: string, file: File, name?: string) => {
    const form = new FormData();
    form.append("id", id);
    form.append("file", file);
    if (name) form.append("name", name);
    const res = await fetch("/api/documentation/templates/upload", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text() || res.statusText);
    return res.json() as Promise<{ id: string; name: string; source: string; format?: string }>;
  },
  exportDocTemplate: (id: string, format: string) =>
    fetch(`/api/documentation/templates/${id}/export?format=${encodeURIComponent(format)}`).then(async (res) => {
      if (!res.ok) throw new Error(await res.text() || res.statusText);
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/);
      return { blob, filename: match?.[1] || `${id}.${format}` };
    }),
  deleteDocTemplate: (id: string) =>
    request<{ deleted: string }>(`/api/documentation/templates/${id}`, { method: "DELETE" }),
  buildContextPack: (
    projectId: string,
    body: { mode: "project" | "task"; task?: string; size?: string }
  ) =>
    request<{
      mode: string;
      content: string;
      char_count: number;
      estimated_tokens: number;
      max_chars: number;
      files_referenced?: string[];
      keywords?: string[];
      symbols_found?: number;
      routes_found?: number;
      project_name: string;
      task?: string;
    }>(`/api/projects/${projectId}/context-pack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  exportDocumentation: (projectId: string, path = "DOCUMENTATION.md", format = "md") =>
    request<{ path: string; relative_path: string; bytes: number; format?: string }>(
      `/api/projects/${projectId}/documentation/export`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, format }),
      }
    ),
  downloadDocumentation: (projectId: string, format = "md") =>
    fetch(`/api/projects/${projectId}/documentation/download?format=${encodeURIComponent(format)}`).then(
      async (res) => {
        if (!res.ok) throw new Error(await res.text() || res.statusText);
        const blob = await res.blob();
        const disposition = res.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename="([^"]+)"/);
        return { blob, filename: match?.[1] || `documentation.${format}` };
      }
    ),
};

export type DocExportFormat = "md" | "txt" | "docx" | "pdf";

export async function streamDocumentation(
  projectId: string,
  template: string,
  onEvent: (event: Record<string, unknown>) => void
) {
  const res = await fetch(`/api/projects/${projectId}/documentation/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template }),
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

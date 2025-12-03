const API_BASE = "http://localhost:8000";

export type Project = {
  id?: string;
  project_id?: string;
  name: string;
  description?: string;
  created_at?: string;
  default_branch?: string;
  updated_at?: string;
};

export type ProjectCreatePayload = {
  name: string;
  description?: string;
  active?: boolean;
};

export async function fetchProjects(token: string): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/api/projects`, {
    method: "GET",
    headers: {
      "Authorization": `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    throw new Error(`Fetch projects failed: ${res.status}`);
  }
  return res.json();
}

export async function createProject(token: string, payload: ProjectCreatePayload): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/projects`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Create project failed: ${res.status}`);
  }
  return res.json();
}

export async function deleteProject(token: string, id: string): Promise<{ success: boolean }>{
  const res = await fetch(`${API_BASE}/api/projects/${id}`, {
    method: "DELETE",
    headers: {
      "Authorization": `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    throw new Error(`Delete project failed: ${res.status}`);
  }
  return res.json();
}

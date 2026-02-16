const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export type Project = {
  id?: string;
  project_id?: string;
  name: string;
  description?: string;
  created_at?: string;
  default_branch?: string;
  updated_at?: string;
};

export type Commit = {
  commit_id: string;
  project_id: string;
  branch_id: string;
  parent_commit_id: string | null;
  author_id: string;
  commit_hash: string;
  commit_message: string;
  committed_at: string;
  merge_commit?: boolean;
  merge_parent_id?: string | null;
  author_username?: string;
};

export type ProjectCreatePayload = {
  name: string;
  description?: string;
  active?: boolean;
};

// export type AddProjectMemberPayload = {
//   email: string;
// };

export interface BlenderObject {
  object_id: string;
  object_name: string;
  object_type: string;
  file_path: string;
  commit_id: string;
};

async function handleProjectError(res: Response, context: string) {
  let message = `${context} failed: ${res.status}`;

  try {
    const data = await res.json();
    if (data?.detail) {
      message = Array.isArray(data.detail)
        ? data.detail
          .map((d: any) => d.msg || d.detail || JSON.stringify(d))
          .join(", ")
        : data.detail;
    }
  } catch {
    const text = await res.text().catch(() => "");
    if (text) message = text;
  }

  throw new Error(message);
}

export async function fetchProjects(token: string): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/projects`, {
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

export async function deleteProject(token: string, id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${id}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  // 204 No Content is success
  if (res.status === 204) {
    return;
  }

  // Any other non-2xx status → try to pull an error message,
  // but do NOT call res.json() first (it might be empty).
  if (!res.ok) {
    let message = `Delete project failed: ${res.status}`;

    try {
      const text = await res.text();
      if (text) {
        message = text;
      }
    } catch {
      // ignore
    }

    throw new Error(message);
  }

  // For the rare case the backend returns 200 + JSON, we *could* parse it,
  // but we don't actually need it anywhere, so just ignore.
  return;
}

export async function fetchCommits(
  token: string,
  projectId: string,
  branchName = "main"
): Promise<Commit[]> {
  const res = await fetch(
    `${API_BASE}/api/projects/${projectId}/commits?branch_name=${encodeURIComponent(
      branchName
    )}`,
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!res.ok) {
    await handleProjectError(res, "Fetch commits");
  }

  return res.json();
}

export async function fetchCommitObjects(
  token: string,
  projectId: string,
  commitId: string
): Promise<BlenderObject[]> {
  const res = await fetch(
    `${API_BASE}/api/projects/${projectId}/commits/${commitId}/objects`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
    }
  ); 

  if (!res.ok) {
    throw new Error("Failed to fetch commit objects");
  }

  return res.json();
}

// export async function addProjectMember(
//   token: string,
//   projectId: string,
//   payload: AddProjectMemberPayload
// ): Promise<{ member_id: string; email: string; username: string }>
// {
//   const res = await fetch(`${API_BASE}/api/projects/${projectId}/members`, {
//     method: "POST",
//     headers: {
//       "Content-Type": "application/json",
//       Authorization: `Bearer ${token}`,
//     },
//     body: JSON.stringify(payload),
//   });
//
//   if (!res.ok) {
//     await handleProjectError(res, "Add project member");
//   }
//
//   return res.json();
// }

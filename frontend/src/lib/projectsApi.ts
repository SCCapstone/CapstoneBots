const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL;

export type Project = {
  id?: string;
  project_id?: string;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
};

export type Commit = {
  commit_id: string;
  project_id: string;
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

export type MemberRole = "viewer" | "editor" | "owner";

export type ProjectMember = {
  member_id: string;
  project_id: string;
  user_id: string;
  username: string;
  email: string;
  role: MemberRole;
  added_at: string;
  added_by?: string;
};

export type Invitation = {
  invitation_id: string;
  project_id: string;
  project_name?: string;
  inviter_id: string;
  inviter_username?: string;
  invitee_id?: string;
  invitee_email: string;
  invitee_username?: string;
  role: MemberRole;
  status: "pending" | "accepted" | "declined" | "expired";
  created_at: string;
  expires_at: string;
  responded_at?: string;
};

export type InvitationPayload = {
  email?: string;
  username?: string;
  role?: MemberRole;
};

export type AddProjectMemberPayload = {
  email?: string;
  username?: string;
  role?: MemberRole;
};

export interface BlenderObject {
  object_id: string;
  object_name: string;
  object_type: string;
  file_path: string;
  commit_id: string;
}

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

// ============== Project CRUD ==============

export async function fetchProjects(token: string): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/projects`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
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
      Authorization: `Bearer ${token}`,
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

  if (res.status === 204) return;

  if (!res.ok) {
    let message = `Delete project failed: ${res.status}`;
    try {
      const text = await res.text();
      if (text) message = text;
    } catch { }
    throw new Error(message);
  }
}

// ============== Commits ==============

export async function fetchCommits(
  token: string,
  projectId: string
): Promise<Commit[]> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/commits`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) await handleProjectError(res, "Fetch commits");
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
  if (!res.ok) throw new Error("Failed to fetch commit objects");
  return res.json();
}

// ============== Members ==============

export async function addProjectMember(
  token: string,
  projectId: string,
  payload: AddProjectMemberPayload
): Promise<ProjectMember> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/members`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await handleProjectError(res, "Add project member");
  return res.json();
}

export async function fetchProjectMembers(
  token: string,
  projectId: string
): Promise<ProjectMember[]> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/members`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) await handleProjectError(res, "Fetch project members");
  return res.json();
}

export async function removeProjectMember(
  token: string,
  projectId: string,
  memberId: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/members/${memberId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 204) return;
  if (!res.ok) await handleProjectError(res, "Remove project member");
}

export async function updateMemberRole(
  token: string,
  projectId: string,
  memberId: string,
  role: MemberRole
): Promise<ProjectMember> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/members/${memberId}/role`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) await handleProjectError(res, "Update member role");
  return res.json();
}

// ============== Invitations ==============

export async function sendInvitation(
  token: string,
  projectId: string,
  payload: InvitationPayload
): Promise<Invitation> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/invitations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await handleProjectError(res, "Send invitation");
  return res.json();
}

export async function fetchProjectInvitations(
  token: string,
  projectId: string
): Promise<Invitation[]> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/invitations`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) await handleProjectError(res, "Fetch project invitations");
  return res.json();
}

export async function cancelInvitation(
  token: string,
  projectId: string,
  invitationId: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/invitations/${invitationId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 204) return;
  if (!res.ok) await handleProjectError(res, "Cancel invitation");
}

export async function fetchPendingInvitations(token: string): Promise<Invitation[]> {
  const res = await fetch(`${API_BASE}/api/auth/invitations/pending`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) await handleProjectError(res, "Fetch pending invitations");
  return res.json();
}

export async function acceptInvitation(token: string, invitationId: string): Promise<ProjectMember> {
  const res = await fetch(`${API_BASE}/api/auth/invitations/${invitationId}/accept`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) await handleProjectError(res, "Accept invitation");
  return res.json();
}

export async function declineInvitation(token: string, invitationId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/invitations/${invitationId}/decline`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) await handleProjectError(res, "Decline invitation");
}

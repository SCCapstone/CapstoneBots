/**
 * Unit Tests for projectsApi.ts
 *
 * Tests the project API client functions with mocked fetch.
 * Covers CRUD operations, members, invitations, and error handling.
 */

import {
  fetchProjects,
  createProject,
  deleteProject,
  fetchCommits,
  fetchProjectMembers,
  sendInvitation,
} from "@/lib/projectsApi";

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

// ============== fetchProjects ==============

describe("fetchProjects", () => {
  it("returns list of projects", async () => {
    const projects = [
      { project_id: "1", name: "Project A" },
      { project_id: "2", name: "Project B" },
    ];
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => projects,
    });

    const result = await fetchProjects("token");
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe("Project A");
  });

  it("sends auth header", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });

    await fetchProjects("my-jwt-token");

    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers.Authorization).toBe("Bearer my-jwt-token");
  });

  it("throws on error response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
    });

    await expect(fetchProjects("bad-token")).rejects.toThrow();
  });

  it("returns empty array when no projects", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });

    const result = await fetchProjects("token");
    expect(result).toEqual([]);
  });
});

// ============== createProject ==============

describe("createProject", () => {
  it("sends POST with project payload", async () => {
    const created = { project_id: "new-id", name: "My Project", default_branch: "main" };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => created,
    });

    const result = await createProject("token", { name: "My Project", description: "desc" });
    expect(result.project_id).toBe("new-id");
    expect(result.default_branch).toBe("main");

    const [, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body.name).toBe("My Project");
    expect(body.description).toBe("desc");
  });

  it("throws on failure", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 400 });
    await expect(createProject("token", { name: "" })).rejects.toThrow();
  });
});

// ============== deleteProject ==============

describe("deleteProject", () => {
  it("resolves on 204", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
    await expect(deleteProject("token", "proj-id")).resolves.toBeUndefined();
  });

  it("sends DELETE with auth", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
    await deleteProject("tok", "123");

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/projects/123");
    expect(options.method).toBe("DELETE");
    expect(options.headers.Authorization).toBe("Bearer tok");
  });

  it("throws on 403 forbidden", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      text: async () => "Forbidden",
    });
    await expect(deleteProject("tok", "123")).rejects.toThrow();
  });
});

// ============== fetchCommits ==============

describe("fetchCommits", () => {
  it("fetches commits for default branch", async () => {
    const commits = [
      { commit_id: "c1", commit_hash: "abc123", commit_message: "Initial" },
    ];
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => commits,
    });

    const result = await fetchCommits("token", "proj-1");
    expect(result).toHaveLength(1);
    expect(result[0].commit_message).toBe("Initial");
  });

  it("passes branch name in URL", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });

    await fetchCommits("token", "proj-1", "develop");
    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain("branch_name=develop");
  });
});

// ============== fetchProjectMembers ==============

describe("fetchProjectMembers", () => {
  it("returns members list", async () => {
    const members = [
      { member_id: "m1", username: "alice", role: "owner" },
      { member_id: "m2", username: "bob", role: "editor" },
    ];
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => members,
    });

    const result = await fetchProjectMembers("token", "proj-1");
    expect(result).toHaveLength(2);
    expect(result[0].role).toBe("owner");
  });
});

// ============== sendInvitation ==============

describe("sendInvitation", () => {
  it("sends invitation with email and role", async () => {
    const invitation = {
      invitation_id: "inv-1",
      invitee_email: "bob@example.com",
      role: "editor",
      status: "pending",
    };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => invitation,
    });

    const result = await sendInvitation("token", "proj-1", {
      email: "bob@example.com",
      role: "editor",
    });
    expect(result.invitation_id).toBe("inv-1");
    expect(result.status).toBe("pending");

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.email).toBe("bob@example.com");
    expect(body.role).toBe("editor");
  });

  it("throws on duplicate invitation", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Invitation already sent" }),
      text: async () => "Invitation already sent",
    });

    await expect(
      sendInvitation("token", "proj-1", { email: "dup@test.com" })
    ).rejects.toThrow();
  });
});

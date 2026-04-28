"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter, useSearchParams, usePathname } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import ObjectTypeIcon from "@/components/ObjectTypeIcon";
import BranchSelector from "@/components/BranchSelector";
import type { Commit, Project, ProjectMember, Invitation, MemberRole, BlenderObject, Branch } from "@/lib/projectsApi";
import {
  deleteProject,
  fetchCommits,
  fetchProjects,
  fetchCommitObjects,
  fetchProjectMembers,
  removeProjectMember,
  updateMemberRole,
  sendInvitation,
  fetchProjectInvitations,
  cancelInvitation,
  fetchObjectDownloadUrl,
  fetchBranches,
  fetchObjectContent,
} from "@/lib/projectsApi";
import { downloadGlbFromStoredJson } from "@/lib/downloadGlb";
import { fetchCurrentUser } from "@/lib/authApi";
import { formatApiDateTime } from "@/lib/datetime";

function formatCommitDate(dateString: string): string {
  return formatApiDateTime(dateString);
}

async function loadCommitsWithUsers(
  token: string,
  projectId: string,
  branchName?: string
): Promise<Commit[]> {
  const rawCommits = await fetchCommits(token, projectId, branchName ? { branchName } : undefined);
  const me = await fetchCurrentUser(token);
  return rawCommits.map((c) => ({
    ...c,
    author_username: c.author_id === me.user_id ? me.username : "Unknown User",
  }));
}

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  editor: "bg-sky-500/20 text-sky-300 border-sky-500/30",
  viewer: "bg-slate-500/20 text-slate-300 border-slate-500/30",
};

export default function ProjectPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const branchFromUrl = searchParams.get("branch");
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const { token } = useAuth();

  const [projectName, setProjectName] = useState<string>("");
  const [loadingProject, setLoadingProject] = useState(true);
  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  // Commits (just the latest commit + count are shown on this page now)
  const [commits, setCommits] = useState<Commit[]>([]);
  const commitCount = commits.length;

  // Objects from latest commit
  const [objects, setObjects] = useState<BlenderObject[]>([]);
  const [objectsLoading, setObjectsLoading] = useState(false);

  // Collaborators panel state
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [invitations, setInvitations] = useState<Invitation[]>([]);

  const [inviteInput, setInviteInput] = useState("");
  const [inviteRole, setInviteRole] = useState<MemberRole>("editor");
  const [sendingInvite, setSendingInvite] = useState(false);
  const [inviteMessage, setInviteMessage] = useState("");

  const [currentUserId, setCurrentUserId] = useState("");
  const [isOwner, setIsOwner] = useState(false);

  // Branch state
  const [branches, setBranches] = useState<Branch[]>([]);
  const [currentBranch, setCurrentBranch] = useState<Branch | null>(null);

  // Load project name
  useEffect(() => {
    if (!token || !projectId) return;
    (async () => {
      try {
        const projects = await fetchProjects(token);
        const current = projects.find((p: Project) => p.project_id === projectId);
        setProjectName(current ? current.name : "Unknown Project");
      } catch {
        setProjectName("Unknown Project");
      } finally {
        setLoadingProject(false);
      }
    })();
  }, [token, projectId]);

  // Load current user
  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const me = await fetchCurrentUser(token);
        setCurrentUserId(me.user_id);
      } catch { }
    })();
  }, [token]);

  // Load branches on mount. Prefer the branch from the URL (?branch=foo) if it
  // exists, so reloads and back-navigation keep the selection.
  useEffect(() => {
    if (!token || !projectId) return;
    (async () => {
      try {
        const branchList = await fetchBranches(token, projectId);
        setBranches(branchList);
        const fromUrl = branchFromUrl
          ? branchList.find((b) => b.branch_name === branchFromUrl)
          : null;
        const main = branchList.find((b) => b.branch_name === "main") ?? branchList[0] ?? null;
        setCurrentBranch(fromUrl ?? main);
      } catch { }
    })();
    // Intentionally only on initial load / token change — we don't want to
    // reset the user's selection every time they toggle the URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, projectId]);

  // Keep the URL in sync when the user picks a different branch.
  const handleBranchChange = (b: Branch) => {
    setCurrentBranch(b);
    const qs = new URLSearchParams(searchParams.toString());
    if (b.branch_name === "main") qs.delete("branch");
    else qs.set("branch", b.branch_name);
    const query = qs.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  // Load commits and objects when branch changes
  useEffect(() => {
    if (!token || !projectId || !currentBranch) return;
    const loadAll = async () => {
      setObjectsLoading(true);
      try {
        const data = await loadCommitsWithUsers(token, projectId, currentBranch.branch_name);
        setCommits(data);
        if (data.length > 0) {
          const latest = data[0];
          const objs = await fetchCommitObjects(token, projectId, latest.commit_id);
          setObjects(objs);
        } else {
          setObjects([]);
        }
      } catch {
        setObjects([]);
      } finally {
        setObjectsLoading(false);
      }
    };
    loadAll();
  }, [token, projectId, currentBranch]);

  // Load members and invitations
  useEffect(() => {
    if (!token || !projectId) return;
    const loadCollaborators = async () => {
      setMembersLoading(true);
      try {
        const m = await fetchProjectMembers(token, projectId);
        setMembers(m);
        const ownerMember = m.find((mem) => mem.role === "owner");
        setIsOwner(ownerMember?.user_id === currentUserId);
      } catch { }
      try {
        const inv = await fetchProjectInvitations(token, projectId);
        setInvitations(inv.filter((i) => i.status === "pending"));
      } catch { }
      setMembersLoading(false);
    };
    if (currentUserId) loadCollaborators();
  }, [token, projectId, currentUserId]);

  const displayName = loadingProject ? "Loading…" : projectName || "Untitled Project";

  const handleDelete = async () => {
    if (!token) { setError("You must be logged in."); return; }
    setDeleting(true);
    setError("");
    try {
      await deleteProject(token, projectId);
      setShowConfirm(false);
      router.replace("/projects");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to delete project.";
      setError(message);
      setDeleting(false);
    }
  };

  const handleDownloadGlb = async (obj: BlenderObject) => {
    if (!token) return;
    try {
      // Fetch metadata JSON via backend proxy (avoids S3 CORS)
      const metaRes = await fetchObjectContent(token, projectId, obj.json_data_path);
      const metadataJson = await metaRes.json();

      // Fetch geometry JSON if mesh exists
      let geometryJson = {};
      if (obj.mesh_data_path) {
        const meshRes = await fetchObjectContent(token, projectId, obj.mesh_data_path);
        geometryJson = await meshRes.json();
      }

      downloadGlbFromStoredJson(
        metadataJson,
        geometryJson,
        `${obj.object_name}.glb`
      );
    } catch (err) {
      console.error("GLB download failed:", err);
    }
  };

  const handleDownloadJson = async (obj: BlenderObject) => {
    if (!token) return;
    try {
      const data = await fetchObjectDownloadUrl(token, projectId, obj.json_data_path);
      if (data.url) window.open(data.url, "_blank");
    } catch { }
  };

  const handleSendInvite = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !inviteInput.trim()) return;
    setSendingInvite(true);
    setInviteMessage("");
    try {
      const isEmail = inviteInput.includes("@");
      const result = await sendInvitation(token, projectId, {
        ...(isEmail ? { email: inviteInput.trim() } : { username: inviteInput.trim() }),
        role: inviteRole,
      });
      setInvitations((prev) => [result, ...prev]);
      setInviteInput("");
      setInviteMessage(`Invitation sent to ${result.invitee_email}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to send invitation.";
      setInviteMessage(message);
    } finally {
      setSendingInvite(false);
    }
  };

  const handleCancelInvite = async (invitationId: string) => {
    if (!token) return;
    try {
      await cancelInvitation(token, projectId, invitationId);
      setInvitations((prev) => prev.filter((i) => i.invitation_id !== invitationId));
    } catch { }
  };

  const handleRemoveMember = async (memberId: string) => {
    if (!token) return;
    try {
      await removeProjectMember(token, projectId, memberId);
      setMembers((prev) => prev.filter((m) => m.member_id !== memberId));
    } catch { }
  };

  const handleRoleChange = async (memberId: string, newRole: MemberRole) => {
    if (!token) return;
    try {
      const updated = await updateMemberRole(token, projectId, memberId, newRole);
      setMembers((prev) => prev.map((m) => m.member_id === memberId ? updated : m));
    } catch { }
  };

  return (
    <div className="relative min-h-screen bg-[#0f172a] px-4 py-12">
      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Link
          href="/projects"
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-sky-500 hover:text-sky-200"
        >
          ← Back to Projects
        </Link>
      </div>

      {/* Two-column layout */}
      <div className="mx-auto flex max-w-7xl gap-5 items-start pt-8">
        {/* Left: Main content */}
        <div className="min-w-0 flex-1 space-y-5">
          {/* Header + actions */}
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1 pr-4">
              <p className="mb-1 text-xs text-slate-500">
                Projects / <span className="inline-block max-w-full truncate align-bottom text-slate-300" title={displayName}>{displayName}</span>
              </p>
              <h1 className="truncate text-2xl font-semibold text-white" title={displayName}>{displayName}</h1>
            </div>
            <div className="flex items-center gap-2">
              {token && (
                <BranchSelector
                  token={token}
                  projectId={projectId}
                  branches={branches}
                  currentBranch={currentBranch}
                  onBranchChange={handleBranchChange}
                  onBranchesUpdated={(updated) => setBranches(updated)}
                />
              )}
              <Link
                href={
                  currentBranch && currentBranch.branch_name !== "main"
                    ? `/projects/${projectId}/commits?branch=${encodeURIComponent(currentBranch.branch_name)}`
                    : `/projects/${projectId}/commits`
                }
                className="rounded-lg border border-slate-700 px-3 py-1 text-[11px] text-slate-300 transition hover:border-sky-500 hover:text-sky-200"
              >
                {commitCount} Commits
              </Link>
              <button type="button" onClick={() => setShowConfirm(true)} className="rounded-lg border border-red-500/70 px-3 py-1 text-[11px] text-red-300 transition hover:bg-red-500/10">
                Delete
              </button>
            </div>
          </div>

          {/* Last commit bar */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-200">
                  <span className="h-2 w-2 rounded-full bg-green-500" />
                  <span>{currentBranch?.branch_name ?? "main"}</span>
                </span>
                {commits.length > 0 ? (
                  <p className="text-slate-400">
                    <span className="font-medium text-slate-200">{commits[0].author_username || "Unknown User"}</span>{" "}
                    committed <span className="text-sky-300">&quot;{commits[0].commit_message}&quot;</span>{" "}
                    · {formatCommitDate(commits[0].committed_at)}
                  </p>
                ) : (
                  <p className="text-slate-500">No commits yet</p>
                )}
              </div>
              {objects.length > 0 && (
                <div className="flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-1 text-[10px] text-slate-400">
                  <span>⬡</span>
                  <span>{objects.length} objects</span>
                </div>
              )}
            </div>
          </div>

          {/* Objects table */}
          <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 text-xs">
            <div className="grid grid-cols-[1fr_auto_1fr_auto] border-b border-slate-800 bg-slate-950 px-4 py-2 text-[11px] font-medium text-slate-400">
              <div className="text-left">OBJECT</div>
              <div className="px-4 text-left">TYPE</div>
              <div className="text-left">BLOB HASH</div>
              <div className="text-right">ACTIONS</div>
            </div>
            <div className="divide-y divide-slate-800">
              {objectsLoading ? (
                <div className="px-4 py-3 text-xs text-slate-400">Loading objects...</div>
              ) : objects.length === 0 ? (
                <div className="px-4 py-3 text-xs text-slate-500">No objects yet for this project. Push from Blender to add objects.</div>
              ) : (
                objects.map((obj) => (
                  <div key={obj.object_id} className="grid grid-cols-[1fr_auto_1fr_auto] items-center px-4 py-2 hover:bg-slate-900/80 transition">
                    <div className="flex items-center gap-2 text-slate-100">
                      <span className="truncate font-medium">{obj.object_name}</span>
                    </div>
                    <div className="px-4">
                      <ObjectTypeIcon objectType={obj.object_type} showLabel />
                    </div>
                    <div className="font-mono text-[10px] text-slate-500" title={obj.blob_hash}>
                      {obj.blob_hash.slice(0, 12)}…
                    </div>
                    <div className="flex items-center gap-1 justify-end">
                      {obj.mesh_data_path && (
                        <button
                          type="button"
                          onClick={() => handleDownloadGlb(obj)}
                          className="rounded border border-violet-500/50 px-2 py-0.5 text-[10px] text-violet-300 transition hover:bg-violet-500/10"
                          title="Download as GLB (3D model)"
                        >
                          GLB
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDownloadJson(obj)}
                        className="rounded border border-sky-500/50 px-2 py-0.5 text-[10px] text-sky-300 transition hover:bg-sky-500/10"
                        title="Download JSON metadata"
                      >
                        JSON
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
            {error && <p className="px-4 py-2 text-[11px] text-red-400">{error}</p>}
          </div>
        </div>

        {/* Right: Collaborators panel */}
        <div className="w-80 shrink-0 space-y-4">
          {/* Invite form */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Invite Collaborator
            </h3>
            <form onSubmit={handleSendInvite} className="space-y-2">
              <input
                type="text"
                value={inviteInput}
                onChange={(e) => setInviteInput(e.target.value)}
                placeholder="Email or username"
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-[11px] text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
                required
              />
              <div className="flex gap-2">
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as MemberRole)}
                  className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-[11px] text-slate-200 focus:border-sky-500 focus:outline-none"
                >
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                  <option value="owner">Owner</option>
                </select>
                <button
                  type="submit"
                  disabled={sendingInvite}
                  className="rounded-lg bg-sky-600 px-3 py-2 text-[11px] font-semibold text-white transition hover:bg-sky-500 disabled:opacity-60"
                >
                  {sendingInvite ? "..." : "Send"}
                </button>
              </div>
            </form>
            {inviteMessage && (
              <p className="mt-2 text-[10px] text-slate-300">{inviteMessage}</p>
            )}
          </div>

          {/* Pending invitations */}
          {invitations.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
                Pending Invitations
              </h3>
              <div className="space-y-2">
                {invitations.map((inv) => (
                  <div
                    key={inv.invitation_id}
                    className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2"
                  >
                    <div>
                      <p className="text-[11px] text-slate-200">
                        {inv.invitee_username || inv.invitee_email}
                      </p>
                      <span className={`mt-0.5 inline-block rounded-full border px-1.5 py-0.5 text-[9px] font-medium uppercase ${ROLE_COLORS[inv.role] || ROLE_COLORS.viewer}`}>
                        {inv.role}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleCancelInvite(inv.invitation_id)}
                      className="text-[10px] text-slate-500 hover:text-red-400 transition"
                    >
                      Cancel
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Members list */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Members
            </h3>
            {membersLoading ? (
              <p className="text-[11px] text-slate-400">Loading...</p>
            ) : members.length === 0 ? (
              <p className="text-[11px] text-slate-500">No members yet.</p>
            ) : (
              <div className="space-y-2">
                {members.map((m) => (
                  <div
                    key={m.member_id}
                    className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[11px] font-medium text-slate-200">
                        {m.username}
                      </p>
                      <p className="truncate text-[10px] text-slate-500">{m.email}</p>
                    </div>
                    <div className="ml-2 flex items-center gap-1.5">
                      {isOwner && m.user_id !== currentUserId ? (
                        <>
                          <select
                            value={m.role}
                            onChange={(e) => handleRoleChange(m.member_id, e.target.value as MemberRole)}
                            className="rounded border border-slate-700 bg-slate-950 px-1 py-0.5 text-[10px] text-slate-300 focus:border-sky-500 focus:outline-none"
                          >
                            <option value="viewer">Viewer</option>
                            <option value="editor">Editor</option>
                            <option value="owner">Owner</option>
                          </select>
                          <button
                            type="button"
                            onClick={() => handleRemoveMember(m.member_id)}
                            className="text-[10px] text-slate-500 hover:text-red-400 transition"
                            title="Remove member"
                          >
                            ✕
                          </button>
                        </>
                      ) : (
                        <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-medium uppercase ${ROLE_COLORS[m.role] || ROLE_COLORS.viewer}`}>
                          {m.role}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Confirm Delete Overlay */}
      {showConfirm && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
            <h2 className="mb-2 text-sm font-semibold text-white">Delete project?</h2>
            <p className="mb-4 text-xs text-slate-400">
              This will permanently delete this project and its data. This action cannot be undone.
            </p>
            {error && <p className="mb-3 text-[11px] text-red-400">{error}</p>}
            <div className="mt-2 flex items-center justify-end gap-2">
              <button
                type="button"
                disabled={deleting}
                onClick={() => { if (!deleting) { setShowConfirm(false); setError(""); } }}
                className="rounded-lg border border-slate-700 px-3 py-1 text-[11px] text-slate-300 hover:border-slate-500 disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-lg bg-red-600 px-3 py-1 text-[11px] font-semibold text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {deleting ? "Deleting..." : "Delete Project"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Commits Overlay */}
      {showCommits && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="truncate pr-3 text-sm font-semibold text-white" title={`Commits for ${displayName}`}>Commits for {displayName}</h2>
              <button type="button" onClick={() => { setShowCommits(false); setCommitsError(""); }} className="text-xs text-slate-400 hover:text-slate-100">
                ✕
              </button>
            </div>
            {commitsLoading && <p className="text-xs text-slate-400">Loading commits...</p>}
            {commitsError && <p className="mb-2 text-xs text-red-400">{commitsError}</p>}
            {!commitsLoading && !commitsError && commits.length === 0 && (
              <p className="text-xs text-slate-400">No commits yet for this project.</p>
            )}
            {!commitsLoading && !commitsError && commits.length > 0 && (
              <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {commits.map((c) => (
                  <CommitItem
                    key={c.commit_id}
                    commit={c}
                    projectId={projectId}
                    objectCount={commitObjectCounts[c.commit_id]}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}

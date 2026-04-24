"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import {
    fetchPendingInvitations,
    acceptInvitation,
    declineInvitation,
    type Invitation,
} from "@/lib/projectsApi";

export default function InvitationsPage() {
    const router = useRouter();
    const { token, hydrated, isAuthenticated } = useAuth();

    const [invitations, setInvitations] = useState<Invitation[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [actionLoading, setActionLoading] = useState<string | null>(null);

    useEffect(() => {
        if (!hydrated) return;
        if (!token) {
            if (!isAuthenticated) router.replace("/login");
            return;
        }

        (async () => {
            setLoading(true);
            setError("");
            try {
                const data = await fetchPendingInvitations(token);
                setInvitations(data);
            } catch (err: unknown) {
                setError(err instanceof Error ? err.message : "Failed to load invitations.");
            } finally {
                setLoading(false);
            }
        })();
    }, [hydrated, token, isAuthenticated, router]);

    const handleAccept = async (invitationId: string) => {
        if (!token) return;
        setActionLoading(invitationId);
        try {
            await acceptInvitation(token, invitationId);
            setInvitations((prev) => prev.filter((i) => i.invitation_id !== invitationId));
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Failed to accept invitation.");
        } finally {
            setActionLoading(null);
        }
    };

    const handleDecline = async (invitationId: string) => {
        if (!token) return;
        setActionLoading(invitationId);
        try {
            await declineInvitation(token, invitationId);
            setInvitations((prev) => prev.filter((i) => i.invitation_id !== invitationId));
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Failed to decline invitation.");
        } finally {
            setActionLoading(null);
        }
    };

    const formatDate = (d: string) => {
        const date = new Date(d);
        return isNaN(date.getTime()) ? d : date.toLocaleDateString();
    };

    const ROLE_COLORS: Record<string, string> = {
        owner: "bg-amber-500/20 text-amber-300 border-amber-500/30",
        editor: "bg-sky-500/20 text-sky-300 border-sky-500/30",
        viewer: "bg-slate-500/20 text-slate-300 border-slate-500/30",
    };

    const roleBadge = (role: string) => {
        return ROLE_COLORS[role] || ROLE_COLORS.viewer;
    };

    if (!hydrated || (!token && !isAuthenticated)) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-[#0f172a] text-sm text-slate-400">
                Redirecting to login...
            </div>
        );
    }

    return (
        <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
            <div className="w-full max-w-2xl">
                {/* Header */}
                <div className="mb-6 flex items-center justify-between">
                    <div>
                        <h1 className="text-lg font-semibold text-white">Invitations</h1>
                        <p className="mt-1 text-xs text-slate-400">
                            Pending project invitations for your account.
                        </p>
                    </div>
                    <Link
                        href="/projects"
                        className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
                    >
                        ← Back to Projects
                    </Link>
                </div>

                {error && <p className="mb-3 text-xs text-red-400">{error}</p>}

                {loading && <p className="text-xs text-slate-400">Loading invitations...</p>}

                {!loading && invitations.length === 0 && (
                    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center">
                        <p className="text-sm text-slate-400">No pending invitations.</p>
                        <p className="mt-1 text-xs text-slate-500">
                            When someone invites you to collaborate on a project, it will appear here.
                        </p>
                    </div>
                )}

                {!loading && invitations.length > 0 && (
                    <div className="space-y-3">
                        {invitations.map((inv) => (
                            <div
                                key={inv.invitation_id}
                                className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 transition hover:border-slate-700"
                            >
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex-1">
                                        <h3 className="text-sm font-medium text-white">
                                            {inv.project_name || "Unknown Project"}
                                        </h3>
                                        <p className="mt-1 text-xs text-slate-400">
                                            Invited by{" "}
                                            <span className="text-slate-200">
                                                {inv.inviter_username || "Unknown"}
                                            </span>
                                        </p>

                                        <div className="mt-2 flex items-center gap-2">
                                            <span
                                                className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${roleBadge(inv.role)}`}
                                            >
                                                {inv.role}
                                            </span>
                                            <span className="text-[10px] text-slate-500">
                                                Expires {formatDate(inv.expires_at)}
                                            </span>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-2">
                                        <button
                                            type="button"
                                            disabled={actionLoading === inv.invitation_id}
                                            onClick={() => handleAccept(inv.invitation_id)}
                                            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-60"
                                        >
                                            {actionLoading === inv.invitation_id ? "..." : "Accept"}
                                        </button>
                                        <button
                                            type="button"
                                            disabled={actionLoading === inv.invitation_id}
                                            onClick={() => handleDecline(inv.invitation_id)}
                                            className="rounded-lg border border-slate-700 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-red-500/70 hover:text-red-300 disabled:opacity-60"
                                        >
                                            Decline
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

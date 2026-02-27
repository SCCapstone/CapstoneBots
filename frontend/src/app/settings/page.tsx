/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState, useEffect, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { deleteAccount } from "@/lib/authApi";

export default function SettingsPage() {
    const router = useRouter();
    const { token, isAuthenticated, logout } = useAuth();

    // Delete account modal state
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [password, setPassword] = useState("");
    const [deleting, setDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState("");

    // Redirect if not authenticated
    useEffect(() => {
        if (!token && !isAuthenticated) {
            router.replace("/login");
        }
    }, [token, isAuthenticated, router]);

    if (!token && !isAuthenticated) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-[#0f172a] text-sm text-slate-400">
                Redirecting to login...
            </div>
        );
    }

    const handleDeleteAccount = async (e: FormEvent) => {
        e.preventDefault();
        setDeleteError("");

        if (!token) return;

        if (!password.trim()) {
            setDeleteError("Password is required to confirm deletion.");
            return;
        }

        setDeleting(true);
        try {
            await deleteAccount(token, password);
            logout();
            router.replace("/");
        } catch (err: any) {
            setDeleteError(err?.message || "Failed to delete account.");
        } finally {
            setDeleting(false);
        }
    };

    return (
        <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
            <div className="w-full max-w-lg">
                {/* Header */}
                <div className="mb-8 flex items-center justify-between">
                    <div>
                        <h1 className="text-lg font-semibold text-white">Settings</h1>
                        <p className="mt-1 text-xs text-slate-400">
                            Manage your account preferences.
                        </p>
                    </div>
                    <Link
                        href="/projects"
                        className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
                    >
                        ← Back to Projects
                    </Link>
                </div>

                {/* Danger Zone */}
                <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-6">
                    <h2 className="text-sm font-semibold text-red-400">Danger Zone</h2>
                    <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                        Permanently delete your account and all associated data. Projects
                        you own that have no other members will be deleted. Projects with
                        collaborators will have ownership transferred automatically.
                    </p>
                    <button
                        id="delete-account-btn"
                        onClick={() => {
                            setDeleteError("");
                            setPassword("");
                            setShowDeleteModal(true);
                        }}
                        className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-500 transition"
                    >
                        Delete Account
                    </button>
                </div>
            </div>

            {/* Delete Account Confirmation Modal */}
            {showDeleteModal && (
                <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60">
                    <div className="w-full max-w-sm rounded-2xl border border-red-900/50 bg-slate-900/95 p-6 shadow-xl">
                        <div className="mb-4 flex items-center justify-between">
                            <h2 className="text-sm font-semibold text-red-400">
                                Delete Account
                            </h2>
                            <button
                                type="button"
                                onClick={() => {
                                    if (!deleting) {
                                        setShowDeleteModal(false);
                                        setDeleteError("");
                                    }
                                }}
                                className="text-xs text-slate-400 hover:text-slate-200"
                            >
                                ✕
                            </button>
                        </div>

                        <div className="mb-4 rounded-lg bg-red-950/40 border border-red-900/30 p-3">
                            <p className="text-xs text-red-300 leading-relaxed">
                                <strong>Warning:</strong> This action is permanent and cannot be
                                undone. All your data will be removed. Projects with
                                collaborators will have ownership transferred.
                            </p>
                        </div>

                        <form onSubmit={handleDeleteAccount} className="space-y-4" suppressHydrationWarning>
                            <div className="text-left">
                                <label className="mb-1 block text-[11px] font-medium text-slate-300">
                                    Enter your password to confirm
                                </label>
                                <input
                                    id="delete-password-input"
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100 outline-none focus:border-red-500"
                                    placeholder="Your current password"
                                    required
                                    autoFocus
                                    suppressHydrationWarning
                                />
                            </div>

                            {deleteError && (
                                <p id="delete-error-msg" className="text-[11px] text-red-400">
                                    {deleteError}
                                </p>
                            )}

                            <div className="mt-2 flex items-center justify-end gap-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        if (!deleting) {
                                            setShowDeleteModal(false);
                                            setDeleteError("");
                                        }
                                    }}
                                    className="rounded-lg border border-slate-700 px-3 py-1 text-[11px] text-slate-300 hover:border-slate-500"
                                >
                                    Cancel
                                </button>
                                <button
                                    id="confirm-delete-btn"
                                    type="submit"
                                    disabled={deleting}
                                    className="rounded-lg bg-red-600 px-3 py-1 text-[11px] font-semibold text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                    {deleting ? "Deleting..." : "Delete My Account"}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

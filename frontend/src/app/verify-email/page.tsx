"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { verifyEmailApi } from "@/lib/authApi";

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [loading, setLoading] = useState(true);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      setError("Missing verification token. Please use the link from your email.");
      setLoading(false);
      return;
    }

    (async () => {
      try {
        await verifyEmailApi(token);
        setSuccess(true);
      } catch (err: unknown) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Verification failed. The link may have expired.");
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  if (loading) {
    return (
      <p className="text-sm text-slate-400">Verifying your email…</p>
    );
  }

  if (success) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-emerald-800 bg-emerald-900/30 p-4 text-sm text-emerald-200">
          Your email has been verified successfully!
        </div>
        <Link
          href="/login"
          className="inline-block rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500 transition"
        >
          Log In
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-red-800 bg-red-900/30 p-4 text-sm text-red-200">
        {error}
      </div>
      <Link
        href="/signup"
        className="inline-block rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200 hover:bg-slate-700 transition"
      >
        Back to Sign Up
      </Link>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
      <div className="absolute left-4 top-4">
        <Link
          href="/login"
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
        >
          ← Back to Login
        </Link>
      </div>

      <div className="w-full max-w-sm text-center">
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center gap-2 text-lg font-semibold text-white">
            <div className="h-5 w-5 bg-sky-500 rounded-sm" />
            <span>Blender Collab</span>
          </div>
          <p className="mt-1 text-sm text-slate-400">Email Verification</p>
        </div>

        <Suspense
          fallback={<p className="text-sm text-slate-400">Loading…</p>}
        >
          <VerifyEmailInner />
        </Suspense>
      </div>
    </div>
  );
}


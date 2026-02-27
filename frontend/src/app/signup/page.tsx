"use client";

import Link from "next/link";
import { FormEvent, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { signupApi, SignupPayload } from "@/lib/authApi";


export default function SignupPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      router.replace("/projects");
    }
  }, [isAuthenticated, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      await signupApi({
        username,
        email,
        password,
      });

      setSuccess(true);
    } catch (err: any) {
      setError(err?.message || "Failed to create account.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Link
          href="/"
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
        >
          ← Back to Home
        </Link>
      </div>
      <div className="w-full max-w-sm text-center">
        {/* Logo / Heading */}
        <div className="mb-8 flex flex-col items-center">
          <div className="flex items-center gap-2 text-lg font-semibold text-white">
            <div className="h-5 w-5 rounded-sm bg-sky-500" />
            <span>Blender Collab</span>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Create a new account
          </p>
        </div>

        {/* Messages */}
        {error && (
          <p className="mb-3 text-xs text-red-400">{error}</p>
        )}

        {success ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-emerald-800 bg-emerald-900/30 p-4 text-sm text-emerald-200">
              Account created! Please check your email for a verification link
              to activate your account.
            </div>
            <Link
              href="/login"
              className="inline-block rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500 transition"
            >
              Go to Login
            </Link>
          </div>
        ) : (
          <>
            {/* Form */}
            <form
          onSubmit={handleSubmit}
          className="space-y-4 text-left"
          suppressHydrationWarning
        >
          <div>
            <label className="mb-1 block text-xs text-slate-300">
              Username
            </label>
            <input
              type="text"
              placeholder="Your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-300">
              Email
            </label>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-300">
              Password
            </label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
              required
              suppressHydrationWarning
            />

            {/* Requirement Text */}
            <p
              className={`mt-1 text-[10px] ${
                password.length >= 8 ? "text-emerald-400" : "text-red-400"
              }`}
            >
              Must be at least 8 characters.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-300">
              Confirm Password
            </label>
            <input
              type="password"
              placeholder="••••••••"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
              required
              suppressHydrationWarning
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-sky-600 py-2 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-60"
          >
            {loading ? "Creating account..." : "Sign Up"}
          </button>
        </form>

        <p className="mt-4 text-xs text-slate-500">
          Already have an account?{" "}
          <a
            href="/login"
            className="cursor-pointer text-sky-400 hover:text-sky-300"
          >
            Log in
          </a>
        </p>
          </>
        )}
      </div>
    </div>
  );
}

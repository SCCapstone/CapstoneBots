"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "graduation-popup-seen";

type Piece = {
  left: number;
  delay: number;
  duration: number;
  rotate: number;
  drift: number;
  color: string;
  size: number;
  shape: "square" | "circle" | "rect";
};

const COLORS = [
  "#38bdf8",
  "#6366f1",
  "#a855f7",
  "#ec4899",
  "#f59e0b",
  "#10b981",
  "#facc15",
];

function makePieces(count: number): Piece[] {
  return Array.from({ length: count }, () => ({
    left: Math.random() * 100,
    delay: Math.random() * 2.5,
    duration: 3 + Math.random() * 3,
    rotate: Math.random() * 720 - 360,
    drift: (Math.random() - 0.5) * 200,
    color: COLORS[Math.floor(Math.random() * COLORS.length)],
    size: 6 + Math.random() * 10,
    shape: (["square", "circle", "rect"] as const)[
      Math.floor(Math.random() * 3)
    ],
  }));
}

export function GraduationPopup() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  const close = useCallback(() => {
    setOpen(false);
    try {
      sessionStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);

  // Read external state (sessionStorage isn't available during SSR) and sync
  // to React state in a post-mount effect. This is exactly the SSR hydration
  // pattern used elsewhere in this app, so disable the rule here.
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    setMounted(true);
    try {
      if (!sessionStorage.getItem(STORAGE_KEY)) {
        setOpen(true);
      }
    } catch {
      setOpen(true);
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  // Lock body scroll while open
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Dismiss on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  const pieces = useMemo(() => (open ? makePieces(120) : []), [open]);

  if (!mounted || !open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="grad-popup-title"
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close celebration"
        onClick={close}
        className="absolute inset-0 cursor-default bg-slate-950/70 backdrop-blur-sm animate-grad-fade-in"
      />

      {/* Confetti layer (above backdrop, below modal content but rendered over it visually) */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        {pieces.map((p, i) => (
          <span
            key={i}
            className="absolute top-[-20px] animate-grad-confetti"
            style={{
              left: `${p.left}%`,
              width: p.shape === "rect" ? p.size * 0.4 : p.size,
              height: p.shape === "rect" ? p.size * 1.4 : p.size,
              backgroundColor: p.color,
              borderRadius: p.shape === "circle" ? "9999px" : "2px",
              animationDelay: `${p.delay}s`,
              animationDuration: `${p.duration}s`,
              ["--grad-rotate" as string]: `${p.rotate}deg`,
              ["--grad-drift" as string]: `${p.drift}px`,
            }}
          />
        ))}
      </div>

      {/* Modal */}
      <div
        className="relative z-10 w-full max-w-2xl animate-grad-pop overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900"
      >
        <button
          type="button"
          onClick={close}
          aria-label="Close"
          className="absolute right-3 top-3 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100/90 text-slate-600 transition hover:bg-slate-200 hover:text-slate-900 dark:bg-slate-800/90 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-white"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>

        <div className="relative aspect-[16/10] w-full bg-slate-100 dark:bg-slate-800">
          <Image
            src="/wegraduated.jpg"
            alt="Our team at graduation"
            fill
            sizes="(min-width: 768px) 640px, 100vw"
            className="object-cover"
            priority
          />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-white/95 to-transparent dark:from-slate-900/95" />
        </div>

        <div className="px-6 pb-7 pt-5 text-center sm:px-8">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300">
            <span aria-hidden>🎓</span>
            We graduated!
          </div>

          <h2
            id="grad-popup-title"
            className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl"
          >
            Thank you for being part of the journey
          </h2>

          <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-slate-600 dark:text-slate-300 sm:text-base">
            <strong>WE DID IT!</strong> After four years of hard work, and we're officially <strong>alumni</strong>!
			CSCE 490 and 492 pushed us to grow as engineers and teammates, and 
			<strong> BlenderCollab</strong> has been the journey that brought it all together. 
			Through every late night and breakthrough, 
			we're grateful we walked this road side by side. On to what's next.
          </p>

          <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <button
              type="button"
              onClick={close}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-sky-600/20 transition hover:bg-sky-500"
            >
              <span aria-hidden>🎉</span>
              Let&apos;s go!
            </button>
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes grad-confetti-fall {
          0% {
            transform: translate3d(0, 0, 0) rotate(0deg);
            opacity: 0;
          }
          5% {
            opacity: 1;
          }
          100% {
            transform: translate3d(var(--grad-drift, 0), 105vh, 0)
              rotate(var(--grad-rotate, 360deg));
            opacity: 1;
          }
        }
        @keyframes grad-pop-in {
          0% {
            transform: scale(0.92) translateY(10px);
            opacity: 0;
          }
          60% {
            transform: scale(1.02) translateY(-2px);
            opacity: 1;
          }
          100% {
            transform: scale(1) translateY(0);
            opacity: 1;
          }
        }
        @keyframes grad-fade-in {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
        .animate-grad-confetti {
          animation: grad-confetti-fall linear forwards;
          will-change: transform, opacity;
        }
        .animate-grad-pop {
          animation: grad-pop-in 480ms cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        .animate-grad-fade-in {
          animation: grad-fade-in 240ms ease-out both;
        }
        @media (prefers-reduced-motion: reduce) {
          .animate-grad-confetti,
          .animate-grad-pop,
          .animate-grad-fade-in {
            animation: none !important;
          }
        }
      `}</style>
    </div>
  );
}

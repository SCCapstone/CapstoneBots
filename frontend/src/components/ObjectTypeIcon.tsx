// src/components/ObjectTypeIcon.tsx
"use client";

const TYPE_CONFIG: Record<string, { icon: string; label: string; color: string }> = {
  MESH: { icon: "⬡", label: "Mesh", color: "bg-sky-500/20 text-sky-300 border-sky-500/30" },
  CAMERA: { icon: "📷", label: "Camera", color: "bg-violet-500/20 text-violet-300 border-violet-500/30" },
  LIGHT: { icon: "💡", label: "Light", color: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
  ARMATURE: { icon: "🦴", label: "Armature", color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
  EMPTY: { icon: "◇", label: "Empty", color: "bg-slate-500/20 text-slate-300 border-slate-500/30" },
  CURVE: { icon: "〰", label: "Curve", color: "bg-teal-500/20 text-teal-300 border-teal-500/30" },
  SURFACE: { icon: "◎", label: "Surface", color: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30" },
  FONT: { icon: "T", label: "Text", color: "bg-rose-500/20 text-rose-300 border-rose-500/30" },
  COLLECTION: { icon: "▣", label: "Collection", color: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30" },
  BLEND_FILE: { icon: "📦", label: "Blend", color: "bg-orange-500/20 text-orange-300 border-orange-500/30" },
};

const DEFAULT_CONFIG = { icon: "●", label: "Object", color: "bg-slate-500/20 text-slate-400 border-slate-600/30" };

interface ObjectTypeIconProps {
  objectType: string;
  showLabel?: boolean;
  size?: "sm" | "md";
}

export default function ObjectTypeIcon({ objectType, showLabel = false, size = "sm" }: ObjectTypeIconProps) {
  const config = TYPE_CONFIG[objectType] || DEFAULT_CONFIG;
  const sizeClasses = size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-0.5";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border font-medium ${config.color} ${sizeClasses}`}
      title={config.label}
    >
      <span>{config.icon}</span>
      {showLabel && <span>{config.label}</span>}
    </span>
  );
}

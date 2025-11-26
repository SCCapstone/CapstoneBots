import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "Blender Collab",
};

export default function RootLayout({
                                     children,
                                   }: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
    <body className="min-h-screen bg-[#0f172a] text-slate-100">
    {/* This makes useAuth() work everywhere */}
    <AuthProvider>
      {children}
    </AuthProvider>
    </body>
    </html>
  );
}

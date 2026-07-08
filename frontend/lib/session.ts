"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export type Session = {
  email: string;
  role: string;
  name: string | null;
  interviewer_id: string | null;
};

/** Admin-page guard: no valid session -> redirect to /login; with requireAdmin, non-admins are redirected too */
export function useSession(requireAdmin = false) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/auth/me`)
      .then(async (r) => {
        if (!r.ok) throw new Error("unauthenticated");
        const s: Session = await r.json();
        if (requireAdmin && s.role !== "admin") throw new Error("forbidden");
        setSession(s);
      })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router, requireAdmin]);

  return { session, loading };
}

export async function logout() {
  await fetch(`${API}/api/auth/logout`, { method: "POST" });
  window.location.href = "/login";
}

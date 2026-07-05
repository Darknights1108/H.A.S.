"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

function VerifyInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setError("Missing token.");
      return;
    }
    fetch(`${API}/api/auth/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail ?? "verification failed");
        // 按角色跳转
        router.replace(data.role === "admin" ? "/admin/applications" : "/admin/slots");
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, [params, router]);

  return (
    <main style={{ maxWidth: 480, margin: "10vh auto 0", textAlign: "center" }}>
      {error ? (
        <>
          <h1>Sign-in failed</h1>
          <p style={{ color: "#dc2626" }}>{error}</p>
          <p><a href="/login">Request a new login link</a></p>
        </>
      ) : (
        <h1>Signing you in…</h1>
      )}
    </main>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={<main style={{ textAlign: "center" }}><h1>Loading…</h1></main>}>
      <VerifyInner />
    </Suspense>
  );
}

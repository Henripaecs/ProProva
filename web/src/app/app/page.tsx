"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { setToken } from "@/lib/api";

/**
 * Entrada usada pelo app ProProva: /app#t=<token>&dest=/provas
 * O token vem no fragmento (#), que nunca é enviado ao servidor nem fica em logs.
 */
export default function AppEntry() {
  const router = useRouter();
  useEffect(() => {
    const h = new URLSearchParams(window.location.hash.slice(1));
    const t = h.get("t");
    const dest = h.get("dest") || "/provas";
    if (t) setToken(t);
    window.history.replaceState(null, "", window.location.pathname);   // tira o token da barra
    router.replace(dest.startsWith("/") && !dest.startsWith("//") ? dest : "/provas");
  }, [router]);
  return <p style={{ padding: 24, color: "#5d6673" }}>Abrindo o painel…</p>;
}

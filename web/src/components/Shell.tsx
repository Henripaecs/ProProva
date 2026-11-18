"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { getToken, setToken } from "@/lib/api";
import { appPost, isApp } from "@/lib/app";

const NAV = [
  { href: "/provas", label: "Provas" },
  { href: "/turmas", label: "Turmas" },
  { href: "/corrigir", label: "Corrigir por foto" },
];

/** Moldura das páginas logadas: menu lateral + guarda de autenticação. */
export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [inApp, setInApp] = useState(false);

  useEffect(() => {
    setInApp(isApp());
    if (!getToken()) router.replace("/login");
    else setReady(true);
  }, [router]);

  if (!ready) return null;
  return (
    <div className="shell">
      <nav className="side">
        <div className="brand">
          <span className="dot" /> ProProva
        </div>
        {NAV.map((n) =>
          inApp && n.href === "/corrigir" ? (
            <a key={n.href} href="#" className="nav" onClick={(e) => { e.preventDefault(); appPost({ type: "scan" }); }}>
              Câmera
            </a>
          ) : (
            <Link key={n.href} href={n.href} className={`nav${pathname.startsWith(n.href) ? " on" : ""}`}>
              {n.label}
            </Link>
          ),
        )}
        <div className="grow" />
        <button
          className="btn ghost sm"
          onClick={() => {
            setToken(null);
            router.replace("/login");
          }}
        >
          Sair
        </button>
      </nav>
      <main className="main">{children}</main>
    </div>
  );
}

/** Link "Corrigir por foto": no app abre a câmera nativa; no navegador, a página de envio. */
export function ScanLink({ href, className, children }: { href: string; className?: string; children: ReactNode }) {
  const [inApp, setInApp] = useState(false);
  useEffect(() => setInApp(isApp()), []);
  if (inApp)
    return (
      <a href="#" className={className} onClick={(e) => { e.preventDefault(); appPost({ type: "scan" }); }}>
        {children}
      </a>
    );
  return <Link href={href} className={className}>{children}</Link>;
}

export function PageHead({ title, sub, crumbs, actions }: { title: ReactNode; sub?: ReactNode; crumbs?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="pagehead">
      <div>
        {crumbs && <div className="crumbs">{crumbs}</div>}
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="alert err">{error}</div> : null;
}

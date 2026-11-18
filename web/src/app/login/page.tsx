"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { ErrorBox } from "@/components/Shell";
import { api, setToken } from "@/lib/api";
import { appPost } from "@/lib/app";
import { useAction } from "@/lib/useLoad";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [expired, setExpired] = useState(false);
  const { busy, error, run } = useAction();

  useEffect(() => {
    const exp = new URLSearchParams(window.location.search).has("expirou");
    setExpired(exp);
    appPost({ type: "logout", expired: exp });   // no app: volta para a tela de login nativa
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const res = await run(() =>
      mode === "login"
        ? api.post<{ token: string }>("/auth/login", { email, password })
        : api.post<{ token: string }>("/auth/register", { email, name, password }),
    );
    if (res) {
      setToken(res.token);
      router.replace("/provas");
    }
  }

  return (
    <div className="auth">
      <form className="card stack" onSubmit={submit}>
        <div>
          <h1>{mode === "login" ? "Entrar" : "Criar conta"}</h1>
          <p className="muted small" style={{ margin: 0 }}>
            ProProva · provas impressas por turma e corrigidas por foto.
          </p>
        </div>
        {expired && mode === "login" && <div className="alert info">Sua sessão expirou. Entre de novo.</div>}
        <ErrorBox error={error} />
        {mode === "register" && (
          <label className="f">
            Nome
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} autoComplete="name" />
          </label>
        )}
        <label className="f">
          E-mail
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label className="f">
          Senha
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={mode === "register" ? 8 : 1}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
          {mode === "register" && <span className="small muted" style={{ fontWeight: 400 }}>Mínimo de 8 caracteres.</span>}
        </label>
        <button className="btn primary" disabled={busy} type="submit" style={{ justifyContent: "center" }}>
          {busy ? "Aguarde…" : mode === "login" ? "Entrar" : "Criar conta"}
        </button>
        <button type="button" className="btn ghost" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Ainda não tenho conta" : "Já tenho conta"}
        </button>
      </form>
    </div>
  );
}

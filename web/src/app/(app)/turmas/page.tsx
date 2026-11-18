"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ErrorBox, PageHead } from "@/components/Shell";
import { api, type ClassRow } from "@/lib/api";
import { useAction, useLoad } from "@/lib/useLoad";

export default function Turmas() {
  const { data, error, loading, reload } = useLoad(() => api.get<ClassRow[]>("/classes"));
  const [name, setName] = useState("");
  const act = useAction();

  async function create(e: FormEvent) {
    e.preventDefault();
    if (await act.run(() => api.post("/classes", { name: name.trim() }))) {
      setName("");
      reload();
    }
  }

  return (
    <>
      <PageHead title="Turmas" sub="Cadastre as turmas e os alunos que vão receber a prova." />
      <form className="card row" onSubmit={create} style={{ marginBottom: 16 }}>
        <input type="text" placeholder="Nome da turma (ex.: 9º ano A — 2026)" value={name} onChange={(e) => setName(e.target.value)} required style={{ flex: 1, minWidth: 220 }} />
        <button className="btn primary" disabled={act.busy}>Criar turma</button>
      </form>
      <ErrorBox error={error || act.error} />
      <div className="card">
        {loading && !data ? (
          <p className="muted">Carregando…</p>
        ) : !data?.length ? (
          <div className="empty"><b>Nenhuma turma ainda</b>Crie a primeira turma acima.</div>
        ) : (
          <table className="t">
            <thead><tr><th>Turma</th><th></th></tr></thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td><Link href={`/turmas/${c.id}`}><b>{c.name}</b></Link></td>
                  <td className="r"><Link className="btn sm" href={`/turmas/${c.id}`}>Alunos →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

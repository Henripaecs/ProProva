"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ErrorBox, PageHead } from "@/components/Shell";
import { api, fmtDate, type ExamRow } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

export default function Provas() {
  const router = useRouter();
  const { data, error, loading } = useLoad(() => api.get<ExamRow[]>("/exams"));
  return (
    <>
      <PageHead
        title="Provas"
        sub="Monte a prova, imprima por turma e acompanhe as notas."
        actions={<Link className="btn primary" href="/provas/nova">Nova prova</Link>}
      />
      <ErrorBox error={error} />
      <div className="card">
        {loading && !data ? (
          <p className="muted">Carregando…</p>
        ) : !data?.length ? (
          <div className="empty">
            <b>Nenhuma prova ainda</b>
            Crie a primeira: escreva as questões, marque a alternativa certa e o cartão-resposta sai pronto.
            <div style={{ marginTop: 14 }}><Link className="btn primary" href="/provas/nova">Nova prova</Link></div>
          </div>
        ) : (
          <table className="t">
            <thead>
              <tr><th>Prova</th><th>Questões</th><th>Situação</th><th className="r">Corrigidas</th><th>Criada em</th></tr>
            </thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.id} className="click" onClick={() => router.push(`/provas/${e.id}`)}>
                  <td>
                    <b>{e.title}</b>
                    {!e.has_booklet && <span className="tag" style={{ marginLeft: 8 }}>só cartão</span>}
                  </td>
                  <td className="num">{e.n_questions} × {"ABCDEF".slice(0, e.n_options).split("").join("")}</td>
                  <td>
                    {e.locked ? <span className="tag pen">impressa · v{e.version}</span> : <span className="tag">rascunho{e.version > 1 ? ` · v${e.version}` : ""}</span>}
                  </td>
                  <td className="r num">{e.n_scans}</td>
                  <td className="muted small">{fmtDate(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

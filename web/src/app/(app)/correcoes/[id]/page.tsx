"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import AuthImage from "@/components/AuthImage";
import { ErrorBox, PageHead } from "@/components/Shell";
import { api, fmtDate, fmtScore, type Answer, type Correct, type ResultRow, type ScanDetail } from "@/lib/api";
import { useAction, useLoad } from "@/lib/useLoad";

const STATUS: Record<Answer["status"], string> = {
  multiple: "duas ou mais marcadas",
  ambiguous: "marca fraca (lápis claro ou borracha?)",
  single: "uma marcada",
  blank: "em branco",
};

const keyList = (k: Correct) => (k === null ? [] : Array.isArray(k) ? k : [k]);

export default function Revisao() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: d, setData, error } = useLoad(() => api.get<ScanDetail>(`/scans/${id}`), [id]);
  const [decided, setDecided] = useState<Record<number, string | null>>({});
  const act = useAction();

  async function decide(n: number, answer: string | null) {
    const r = await act.run(() => api.put<{ score: ScanDetail["score"]; review_needed: number[] }>(`/scans/${id}/answers/${n}`, { answer }));
    if (!r || !d) return;
    setDecided({ ...decided, [n]: answer });
    setData({
      ...d,
      score: r.score,
      review_needed: r.review_needed,
      answers: d.answers.map((a) => (a.number === n ? { ...a, answer, needs_review: false, source: "human", status: answer ? "single" : "blank" } : a)),
    });
  }

  async function nextPending() {
    if (!d) return;
    const rows = await act.run(() => api.get<ResultRow[]>(`/exams/${d.exam_id}/results`));
    const next = rows?.find((r) => r.scan_id !== id && r.review_needed.length);
    if (next) router.push(`/correcoes/${next.scan_id}`);
    else router.push(`/provas/${d.exam_id}`);
  }

  if (error) return <ErrorBox error={error} />;
  if (!d) return <p className="muted">Carregando…</p>;

  // questões que pediram revisão nesta correção (inclui as já decididas nesta sessão)
  const toReview = d.answers.filter((a) => a.needs_review || a.number in decided);
  const pending = d.review_needed.length;

  return (
    <>
      <PageHead
        crumbs={<><Link href="/provas">Provas</Link> › <Link href={`/provas/${d.exam_id}`}>{d.exam_title}</Link></>}
        title={d.student_name}
        sub={<>Corrigido em {fmtDate(d.created_at)} · versão {d.version} da prova</>}
      />
      <ErrorBox error={act.error} />

      <div className="review">
        <div>
          <div className="card">
            <h2>{pending ? `Revisar ${pending} questão(ões)` : toReview.length ? "Revisão concluída" : "Nada a revisar"}</h2>
            {!toReview.length ? (
              <p className="muted" style={{ margin: 0 }}>O leitor teve certeza em todas as questões deste cartão.</p>
            ) : (
              <>
                <p className="small muted" style={{ marginTop: -6 }}>
                  O leitor não teve certeza nestas linhas. Veja o recorte da foto e escolha a resposta que vale.
                </p>
                {toReview.map((a) => {
                  const done = a.number in decided;
                  return (
                    <div key={a.number} className={`rq${done ? " done" : ""}`}>
                      <div className="n">{String(a.number).padStart(2, "0")}</div>
                      <div>
                        <AuthImage className="crop" path={`/scans/${id}/answers/${a.number}/crop.png`} alt={`Questão ${a.number}`} />
                        <div className="small muted" style={{ marginBottom: 8 }}>
                          Leitura: {STATUS[a.status]}{a.marked.length ? ` (${a.marked.join(" e ")})` : ""}
                          {done && <> · <b style={{ color: "var(--ok)" }}>decidido: {decided[a.number] ?? "em branco"}</b></>}
                        </div>
                        <div className="bubbles">
                          {d.options.split("").map((L) => (
                            <button key={L} className={`bubble${(done ? decided[a.number] === L : false) ? " on" : ""}`}
                              disabled={act.busy} onClick={() => decide(a.number, L)}>{L}</button>
                          ))}
                          <button className={`bubble blank${done && decided[a.number] === null ? " on" : ""}`} disabled={act.busy}
                            onClick={() => decide(a.number, null)} title="Anula a resposta do aluno nesta questão">Sem resposta</button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </div>

          <div className="card">
            <h2>Todas as respostas</h2>
            <p className="small muted" style={{ marginTop: -6 }}>
              Verde = gabarito. Preto = resposta lida. Vermelho = resposta errada. Clique numa bolha para corrigir a leitura.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "4px 18px" }}>
              {d.answers.map((a) => {
                const key = keyList(d.answer_key[String(a.number)]);
                const annulled = d.answer_key[String(a.number)] === null;
                return (
                  <div key={a.number} className="row" style={{ gap: 6 }}>
                    <span className="num" style={{ width: 24, textAlign: "right", fontWeight: 700 }}>{String(a.number).padStart(2, "0")}</span>
                    <div className="mini">
                      {d.options.split("").map((L) => {
                        const on = a.answer === L || (a.needs_review && a.marked.includes(L));
                        const isKey = key.includes(L);
                        return (
                          <span key={L} style={{ cursor: "pointer" }} title={`Marcar ${L}`}
                            className={[on && "on", isKey && "key", on && !isKey && !annulled && "wrong"].filter(Boolean).join(" ")}
                            onClick={() => a.answer !== L && decide(a.number, L)}>{L}</span>
                        );
                      })}
                    </div>
                    {a.needs_review && <span className="tag warn">?</span>}
                    {annulled && <span className="tag">anulada</span>}
                    {a.source === "human" && <span className="tag pen" title="Decidido pelo professor">prof.</span>}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <aside className="card stack" style={{ position: "sticky", top: 16 }}>
          <div className="small muted">{pending ? "Nota parcial" : "Nota final"}</div>
          <div className="grade">{fmtScore(d.score.points)}<small> / {fmtScore(d.score.max_points)}</small></div>
          <table className="t small">
            <tbody>
              <tr><td>Acertos</td><td className="r num">{d.score.correct}</td></tr>
              <tr><td>Erros</td><td className="r num">{d.score.wrong}</td></tr>
              <tr><td>Em branco</td><td className="r num">{d.score.blank}</td></tr>
              <tr><td>Anuladas</td><td className="r num">{d.score.annulled}</td></tr>
              <tr><td>Aguardando revisão</td><td className="r num" style={{ color: pending ? "var(--warn)" : undefined }}>{pending}</td></tr>
            </tbody>
          </table>
          <button className="btn primary" disabled={act.busy} onClick={nextPending}>
            {pending ? "Pular para o próximo" : "Próximo com revisão →"}
          </button>
          <Link className="btn" href={`/provas/${d.exam_id}`}>Voltar às notas</Link>
        </aside>
      </div>
    </>
  );
}

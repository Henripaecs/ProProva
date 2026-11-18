"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ErrorBox, PageHead, ScanLink } from "@/components/Shell";
import { isApp } from "@/lib/app";
import { api, fmtDate, fmtScore, saveBlob, type ClassDetail, type ClassRow, type ExamFull, type ResultRow } from "@/lib/api";
import { useAction, useLoad } from "@/lib/useLoad";

export default function Prova() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const exam = useLoad(() => api.get<ExamFull>(`/exams/${id}`), [id]);
  const results = useLoad(() => api.get<ResultRow[]>(`/exams/${id}/results`), [id]);
  const classes = useLoad(() => api.get<ClassRow[]>("/classes"));
  const [classId, setClassId] = useState("");
  const [cls, setCls] = useState<ClassDetail | null>(null);
  const [opts, setOpts] = useState({ include_booklet: true, personalize: true, duplex: false, layout: "single" as "single" | "zip" });
  const [printed, setPrinted] = useState<string | null>(null);
  const act = useAction();

  useEffect(() => {
    if (!classId && classes.data?.length) setClassId(classes.data[0].id);
  }, [classes.data, classId]);
  useEffect(() => {
    setCls(null);
    if (classId) api.get<ClassDetail>(`/classes/${classId}`).then(setCls).catch(() => setCls(null));
  }, [classId]);

  const e = exam.data;
  const hasBooklet = !!e?.content;
  const stats = useMemo(() => {
    const r = results.data || [];
    if (!r.length) return null;
    const pct = r.map((x) => (x.score.max_points ? x.score.points / x.score.max_points : 0));
    return {
      n: r.length,
      avg: (pct.reduce((a, b) => a + b, 0) / r.length) * (r[0].score.max_points || 10),
      max: r[0].score.max_points,
      pending: r.filter((x) => x.review_needed.length).length,
    };
  }, [results.data]);
  const missing = useMemo(() => {
    if (!cls || !results.data) return [];
    const done = new Set(results.data.map((r) => r.student_id));
    return cls.students.filter((s) => !done.has(s.id));
  }, [cls, results.data]);

  async function print() {
    const q = new URLSearchParams({
      layout: opts.layout,
      include_booklet: String(hasBooklet && opts.include_booklet),
      personalize: String(opts.personalize),
      duplex: String(opts.duplex),
    });
    const r = await act.run(() => api.blob(`/exams/${id}/classes/${classId}/print?${q}`));
    if (r) {
      saveBlob(r.blob, r.filename || `prova.${opts.layout === "zip" ? "zip" : "pdf"}`);
      setPrinted(`Arquivo gerado (versão ${r.headers.get("X-Exam-Version") ?? e?.version}). Imprima em escala 100% — nunca “ajustar à página”.`);
      exam.reload();
    }
  }

  async function previewPdf() {
    if (isApp()) {                       // WebView não abre abas: entrega o PDF para o celular
      const r = await act.run(() => api.blob(`/exams/${id}/booklet`));
      if (r) saveBlob(r.blob, r.filename || "previa-caderno.pdf");
      return;
    }
    const w = window.open("", "_blank");
    const r = await act.run(() => api.blob(`/exams/${id}/booklet`));
    if (r && w) w.location.href = URL.createObjectURL(r.blob);
    else w?.close();
  }

  async function csv() {
    const r = await act.run(() => api.blob(`/exams/${id}/results.csv`));
    if (r) saveBlob(r.blob, r.filename || "notas.csv");
  }

  async function remove() {
    if (!confirm(`Excluir a prova "${e?.title}" com todas as correções? Não dá para desfazer.`)) return;
    if ((await act.run(() => api.del(`/exams/${id}`))) !== undefined) router.replace("/provas");
  }

  if (exam.error) return <ErrorBox error={exam.error} />;
  if (!e) return <p className="muted">Carregando…</p>;

  return (
    <>
      <PageHead
        crumbs={<Link href="/provas">Provas</Link>}
        title={e.title}
        sub={<>{e.grid_spec.n_questions} questões · alternativas {"ABCDEF".slice(0, e.grid_spec.n_options).split("").join(", ")} · versão {e.version} {e.locked ? "(impressa)" : "(rascunho)"}</>}
        actions={
          <>
            <Link className="btn" href={`/provas/${id}/editar`}>Editar</Link>
            <button className="btn danger" onClick={remove}>Excluir</button>
          </>
        }
      />
      <ErrorBox error={act.error} />

      <div className="grid2">
        <div className="card stack">
          <h2>Imprimir para uma turma</h2>
          {!classes.data?.length ? (
            <p className="muted">Cadastre uma turma primeiro em <Link href="/turmas">Turmas</Link>.</p>
          ) : (
            <>
              <label className="f">Turma
                <select value={classId} onChange={(ev) => setClassId(ev.target.value)}>
                  {classes.data.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              {cls && <span className="small muted">{cls.students.length} aluno(s) — cada um recebe {hasBooklet && opts.include_booklet ? "o caderno e o cartão-resposta dele" : "o cartão-resposta dele"}, com QR Code próprio.</span>}
              {hasBooklet && (
                <>
                  <label className="check"><input type="checkbox" checked={opts.include_booklet} onChange={(ev) => setOpts({ ...opts, include_booklet: ev.target.checked })} /> Incluir o caderno de questões</label>
                  <label className="check"><input type="checkbox" checked={opts.personalize} disabled={!opts.include_booklet} onChange={(ev) => setOpts({ ...opts, personalize: ev.target.checked })} /> Nome do aluno no caderno</label>
                </>
              )}
              <label className="check"><input type="checkbox" checked={opts.duplex} onChange={(ev) => setOpts({ ...opts, duplex: ev.target.checked })} /> Frente e verso (cartão em folha separada)</label>
              <label className="f">Formato
                <select value={opts.layout} onChange={(ev) => setOpts({ ...opts, layout: ev.target.value as "single" | "zip" })}>
                  <option value="single">Um PDF com a turma inteira</option>
                  <option value="zip">ZIP com um PDF por aluno</option>
                </select>
              </label>
              <div className="row">
                <button className="btn primary" disabled={act.busy || !cls?.students.length} onClick={print}>
                  {act.busy ? "Gerando…" : "Baixar provas da turma"}
                </button>
                {hasBooklet && <button className="btn" disabled={act.busy} onClick={previewPdf}>Prévia do caderno</button>}
              </div>
              {cls && !cls.students.length && <span className="small muted">Esta turma não tem alunos.</span>}
              {printed && <div className="alert ok">{printed}</div>}
              {!e.locked && <p className="small muted" style={{ margin: 0 }}>Ao imprimir, esta versão fica travada: mudanças depois disso viram uma versão nova.</p>}
            </>
          )}
        </div>

        <div className="card stack">
          <h2>Resumo</h2>
          {!stats ? (
            <p className="muted" style={{ margin: 0 }}>Nenhum cartão corrigido ainda. Fotografe pelo app ou envie em <ScanLink href="/corrigir">Corrigir por foto</ScanLink>.</p>
          ) : (
            <div className="row" style={{ gap: 28, alignItems: "flex-end" }}>
              <div><div className="grade">{fmtScore(Math.round(stats.avg * 10) / 10)}<small> / {fmtScore(stats.max)}</small></div><div className="small muted">média da prova</div></div>
              <div><div className="num" style={{ fontSize: 26, fontWeight: 700 }}>{stats.n}</div><div className="small muted">corrigidos</div></div>
              <div><div className="num" style={{ fontSize: 26, fontWeight: 700, color: stats.pending ? "var(--warn)" : undefined }}>{stats.pending}</div><div className="small muted">com rasura p/ revisar</div></div>
            </div>
          )}
          {cls && results.data && cls.students.length > 0 && (
            <p className="small" style={{ margin: 0 }}>
              <b>{cls.name}:</b> {cls.students.length - missing.length} de {cls.students.length} corrigidos.
              {missing.length > 0 && <span className="muted"> Faltam: {missing.slice(0, 8).map((s) => s.name).join(", ")}{missing.length > 8 ? ` e mais ${missing.length - 8}` : ""}.</span>}
            </p>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="row between" style={{ marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Notas</h2>
          <div className="row">
            <ScanLink className="btn" href={`/corrigir?prova=${id}`}>Corrigir por foto</ScanLink>
            <button className="btn" onClick={csv} disabled={!results.data?.length}>Exportar CSV</button>
          </div>
        </div>
        <ErrorBox error={results.error} />
        {!results.data?.length ? (
          <div className="empty"><b>Sem notas ainda</b>As notas aparecem aqui assim que os cartões forem fotografados.</div>
        ) : (
          <table className="t">
            <thead>
              <tr><th>Aluno</th><th className="r">Nota</th><th className="r">Acertos</th><th className="r">Erros</th><th className="r">Brancos</th><th>Situação</th><th>Corrigido em</th></tr>
            </thead>
            <tbody>
              {results.data.map((r) => (
                <tr key={r.scan_id} className="click" onClick={() => router.push(`/correcoes/${r.scan_id}`)}>
                  <td><b>{r.student_name}</b></td>
                  <td className="r num"><b>{fmtScore(r.score.points)}</b> <span className="muted">/ {fmtScore(r.score.max_points)}</span></td>
                  <td className="r num">{r.score.correct}</td>
                  <td className="r num">{r.score.wrong}</td>
                  <td className="r num">{r.score.blank}</td>
                  <td>{r.review_needed.length ? <span className="tag warn">revisar {r.review_needed.length} questão(ões)</span> : <span className="tag ok">final</span>}</td>
                  <td className="small muted">{fmtDate(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

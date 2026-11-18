"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ErrorBox, PageHead } from "@/components/Shell";
import { api, type ClassDetail } from "@/lib/api";
import { useAction, useLoad } from "@/lib/useLoad";

/** "Nome;Matrícula" (ou tab, vindo do Excel) por linha → lista de alunos. */
function parseList(text: string) {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const [name, enrollment] = l.split(/\t|;/).map((x) => x.trim());
      return { name, enrollment: enrollment || null };
    })
    .filter((s) => s.name);
}

export default function Turma() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data, error, reload } = useLoad(() => api.get<ClassDetail>(`/classes/${id}`), [id]);
  const [name, setName] = useState("");
  const [enr, setEnr] = useState("");
  const [bulk, setBulk] = useState("");
  const [showBulk, setShowBulk] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const act = useAction();

  async function addOne(e: FormEvent) {
    e.preventDefault();
    if (await act.run(() => api.post(`/classes/${id}/students`, { name: name.trim(), enrollment: enr.trim() || null }))) {
      setName("");
      setEnr("");
      reload();
    }
  }

  async function addBulk() {
    const students = parseList(bulk);
    if (!students.length) return;
    const r = await act.run(() => api.post<{ created: string[]; skipped: string[] }>(`/classes/${id}/students/bulk`, { students }));
    if (r) {
      setMsg(`${r.created.length} aluno(s) cadastrado(s).` + (r.skipped.length ? ` Matrícula repetida, pulados: ${r.skipped.join(", ")}.` : ""));
      setBulk("");
      setShowBulk(false);
      reload();
    }
  }

  async function remove(sid: string, sname: string) {
    if (!confirm(`Excluir ${sname}? As correções deste aluno também serão apagadas.`)) return;
    if ((await act.run(() => api.del(`/students/${sid}`))) !== undefined) reload();
  }

  async function rename() {
    const n = prompt("Novo nome da turma:", data?.name);
    if (n && n.trim()) (await act.run(() => api.patch(`/classes/${id}`, { name: n.trim() }))) && reload();
  }

  async function removeClass() {
    if (!confirm(`Excluir a turma "${data?.name}" com todos os alunos e correções? Não dá para desfazer.`)) return;
    if ((await act.run(() => api.del(`/classes/${id}`))) !== undefined) router.replace("/turmas");
  }

  return (
    <>
      <PageHead
        crumbs={<Link href="/turmas">Turmas</Link>}
        title={data?.name ?? "…"}
        sub={data ? `${data.students.length} aluno(s)` : undefined}
        actions={
          <>
            <button className="btn" onClick={rename}>Renomear</button>
            <button className="btn danger" onClick={removeClass}>Excluir turma</button>
          </>
        }
      />
      <ErrorBox error={error || act.error} />
      {msg && <div className="alert ok" style={{ marginBottom: 12 }}>{msg}</div>}

      <div className="card">
        <form className="row" onSubmit={addOne}>
          <input type="text" placeholder="Nome do aluno" value={name} onChange={(e) => setName(e.target.value)} required style={{ flex: 2, minWidth: 200 }} />
          <input type="text" placeholder="Matrícula (opcional)" value={enr} onChange={(e) => setEnr(e.target.value)} style={{ flex: 1, minWidth: 140 }} />
          <button className="btn primary" disabled={act.busy}>Adicionar</button>
          <button type="button" className="btn ghost" onClick={() => setShowBulk(!showBulk)}>Colar lista…</button>
        </form>
        {showBulk && (
          <div className="stack" style={{ marginTop: 12 }}>
            <label className="f">
              Um aluno por linha. Matrícula opcional depois de “;” (ou cole direto duas colunas do Excel).
              <textarea rows={8} value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder={"Ana Souza;2026001\nBruno Lima;2026002\nCássia Ribeiro"} />
            </label>
            <div className="row">
              <button className="btn primary" onClick={addBulk} disabled={act.busy || !parseList(bulk).length}>
                Cadastrar {parseList(bulk).length || ""} aluno(s)
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        {!data ? (
          <p className="muted">Carregando…</p>
        ) : !data.students.length ? (
          <div className="empty"><b>Turma sem alunos</b>Adicione um por um ou cole a lista da chamada.</div>
        ) : (
          <table className="t">
            <thead><tr><th>#</th><th>Aluno</th><th>Matrícula</th><th></th></tr></thead>
            <tbody>
              {data.students.map((s, i) => (
                <tr key={s.id}>
                  <td className="num muted">{String(i + 1).padStart(2, "0")}</td>
                  <td>{s.name}</td>
                  <td className="num muted">{s.enrollment ?? "—"}</td>
                  <td className="r"><button className="btn sm danger ghost" onClick={() => remove(s.id, s.name)}>Excluir</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

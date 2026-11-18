"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { PageHead } from "@/components/Shell";
import { api, ApiError, fmtScore, type ScanDetail, type ScanResponse } from "@/lib/api";

type Item = {
  key: string;
  name: string;
  state: "fila" | "enviando" | "ok" | "erro";
  result?: ScanResponse & { student_name?: string; exam_title?: string };
  error?: string;
};

/**
 * Correção pelo navegador: arraste fotos dos cartões (tiradas com qualquer câmera).
 * O QR Code de cada cartão já diz de que prova e de que aluno ele é.
 */
export default function Corrigir() {
  const [items, setItems] = useState<Item[]>([]);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const running = useRef(false);
  const queue = useRef<{ key: string; file: File }[]>([]);

  const patch = (key: string, p: Partial<Item>) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...p } : x)));

  async function pump() {
    if (running.current) return;
    running.current = true;
    while (queue.current.length) {
      const { key, file } = queue.current.shift()!;
      patch(key, { state: "enviando" });
      try {
        const r = await api.upload<ScanResponse>("/scan", file, file.name);
        let extra: Partial<ScanDetail> = {};
        try {
          extra = await api.get<ScanDetail>(`/scans/${r.scan_id}`);
        } catch {
          /* nome do aluno é só cosmético */
        }
        patch(key, { state: "ok", result: { ...r, student_name: extra.student_name, exam_title: extra.exam_title } });
      } catch (e) {
        patch(key, { state: "erro", error: e instanceof ApiError ? e.message : String(e) });
      }
    }
    running.current = false;
  }

  function add(files: FileList | null) {
    if (!files) return;
    const fresh = Array.from(files)
      .filter((f) => f.type.startsWith("image/"))
      .map((file) => ({ key: `${file.name}-${file.size}-${Math.random()}`, file }));
    setItems((xs) => [...fresh.map((f) => ({ key: f.key, name: f.file.name, state: "fila" as const })), ...xs]);
    queue.current.push(...fresh);
    pump();
  }

  return (
    <>
      <PageHead
        title="Corrigir por foto"
        sub="Envie fotos dos cartões-resposta. Cada cartão é identificado pelo QR Code: pode misturar alunos e provas."
      />
      <div
        className={`drop${over ? " over" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}
      >
        <b style={{ display: "block", fontSize: 16, color: "var(--ink)" }}>Arraste as fotos aqui</b>
        ou clique para escolher (JPEG/PNG, até 15 MB cada)
        <input ref={input} type="file" accept="image/*" multiple hidden onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      </div>
      <p className="small muted">
        Dicas: folha inteira no quadro com os 4 quadrados pretos visíveis, sem reflexo sobre o QR Code, celular paralelo à folha.
      </p>

      {items.length > 0 && (
        <div className="card">
          <table className="t">
            <thead><tr><th>Foto</th><th>Aluno / prova</th><th className="r">Nota</th><th>Situação</th><th></th></tr></thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.key}>
                  <td className="small" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.name}</td>
                  <td>
                    {it.result ? (<><b>{it.result.student_name ?? "—"}</b><div className="small muted">{it.result.exam_title}</div></>)
                      : it.error ? <span className="small" style={{ color: "var(--stamp)" }}>{it.error}</span> : <span className="muted small">—</span>}
                  </td>
                  <td className="r num">{it.result ? <>{fmtScore(it.result.score.points)} <span className="muted">/ {fmtScore(it.result.score.max_points)}</span></> : ""}</td>
                  <td>
                    {it.state === "fila" && <span className="tag">na fila</span>}
                    {it.state === "enviando" && <span className="tag pen">lendo…</span>}
                    {it.state === "erro" && <span className="tag stamp">refotografar</span>}
                    {it.state === "ok" && (it.result!.review_needed.length
                      ? <span className="tag warn">revisar {it.result!.review_needed.join(", ")}</span>
                      : <span className="tag ok">nota final</span>)}
                  </td>
                  <td className="r">{it.result && <Link className="btn sm" href={`/correcoes/${it.result.scan_id}`}>{it.result.review_needed.length ? "Revisar" : "Ver"}</Link>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

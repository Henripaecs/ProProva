"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import AuthImage from "@/components/AuthImage";
import { ErrorBox, PageHead } from "@/components/Shell";
import {
  api,
  DEFAULT_HEADER,
  DEFAULT_STYLE,
  LETTERS,
  newQuestion,
  normalizeQuestion,
  type Correct,
  type ExamFull,
  type Header,
  type Question,
  type Style,
} from "@/lib/api";
import { useAction } from "@/lib/useLoad";

type Mode = "editor" | "cartao";

const correctList = (c: Correct): string[] => (c === null ? [] : Array.isArray(c) ? c : [c]);

/** Envolve a seleção do textarea com a marcação (**negrito**, *itálico*…). */
function wrapSelection(el: HTMLTextAreaElement | null, value: string, mark: string, onChange: (v: string) => void) {
  if (!el) return;
  const [a, b] = [el.selectionStart, el.selectionEnd];
  const sel = value.slice(a, b) || "texto";
  const next = value.slice(0, a) + mark + sel + mark + value.slice(b);
  onChange(next);
  requestAnimationFrame(() => {
    el.focus();
    el.setSelectionRange(a + mark.length, a + mark.length + sel.length);
  });
}

function RichArea({ value, onChange, rows = 3, placeholder }: { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const tools: [string, string, string][] = [
    ["**", "N", "Negrito"],
    ["*", "I", "Itálico"],
    ["__", "S", "Sublinhado"],
    ["^", "x²", "Sobrescrito"],
    ["~", "x₂", "Subscrito"],
  ];
  return (
    <div>
      <div className="toolbar">
        {tools.map(([m, label, title]) => (
          <button key={m} type="button" title={title} onClick={() => wrapSelection(ref.current, value, m, onChange)}
            style={label === "N" ? { fontWeight: 800 } : label === "I" ? { fontStyle: "italic" } : label === "S" ? { textDecoration: "underline" } : undefined}>
            {label}
          </button>
        ))}
      </div>
      <textarea ref={ref} rows={rows} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function QuestionCard({
  q, index, total, examId, onChange, onMove, onDuplicate, onRemove,
}: {
  q: Question; index: number; total: number; examId?: string;
  onChange: (q: Question) => void; onMove: (d: -1 | 1) => void; onDuplicate: () => void; onRemove: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const up = useAction();
  const multi = Array.isArray(q.correct);
  const annulled = q.correct === null;
  const chosen = correctList(q.correct);

  function pick(letter: string) {
    if (annulled) return;
    if (!multi) return onChange({ ...q, correct: letter });
    const set = new Set(chosen);
    set.has(letter) ? set.delete(letter) : set.add(letter);
    const arr = LETTERS.split("").filter((l) => set.has(l));
    onChange({ ...q, correct: arr.length ? arr : [letter] });
  }

  function setOptions(options: string[], option_images: (string | null)[] = q.option_images) {
    const valid = LETTERS.slice(0, options.length);
    const kept = chosen.filter((l) => valid.includes(l));
    const correct: Correct = annulled ? null : multi ? (kept.length ? kept : ["A"]) : kept[0] ?? "A";
    onChange({ ...q, options, option_images: options.map((_, i) => option_images[i] ?? null), correct });
  }

  async function sendImage(file: File): Promise<string | null> {
    if (!examId) return null;
    const r = await up.run(() => api.upload<{ id: string }>(`/exams/${examId}/assets`, file, file.name));
    return r ? r.id : null;
  }

  async function upload(file: File) {
    const id = await sendImage(file);
    if (id) onChange({ ...q, image: id });
  }

  const optFileRef = useRef<HTMLInputElement>(null);
  const [optTarget, setOptTarget] = useState(0);
  async function uploadOption(file: File) {
    const id = await sendImage(file);
    if (id) onChange({ ...q, option_images: q.option_images.map((x, j) => (j === optTarget ? id : x)) });
  }
  const hasOptionImages = q.option_images.some(Boolean);
  const [sectionToggled, setShowSection] = useState(false);
  const showSection = sectionToggled || !!(q.section || q.section_text);   // seção preenchida sempre aparece

  return (
    <div className={`q${annulled ? " annulled" : ""}`}>
      <div className="qhead">
        <div className="row">
          <span className="qnum">{index + 1}.</span>
          {annulled && <span className="tag stamp">anulada</span>}
          {q.weight !== 1 && <span className="tag pen">peso {q.weight}</span>}
        </div>
        <div className="row" style={{ gap: 2 }}>
          <button type="button" className="btn ghost sm" disabled={index === 0} onClick={() => onMove(-1)} title="Subir">↑</button>
          <button type="button" className="btn ghost sm" disabled={index === total - 1} onClick={() => onMove(1)} title="Descer">↓</button>
          <button type="button" className="btn ghost sm" onClick={onDuplicate}>Duplicar</button>
          <button type="button" className="btn ghost sm danger" disabled={total === 1} onClick={onRemove}>Excluir</button>
        </div>
      </div>

      {showSection ? (
        <div className="section-box">
          <div className="row between">
            <span className="small" style={{ fontWeight: 600, color: "var(--muted)" }}>Título de seção (aparece antes desta questão)</span>
            <button type="button" className="btn ghost sm danger"
              onClick={() => { setShowSection(false); onChange({ ...q, section: "", section_text: "" }); }}>Remover seção</button>
          </div>
          <input type="text" value={q.section} placeholder="Ex.: Matemática" maxLength={200}
            onChange={(e) => onChange({ ...q, section: e.target.value })} />
          <RichArea rows={2} value={q.section_text} onChange={(section_text) => onChange({ ...q, section_text })}
            placeholder="Texto de apoio (opcional). Ex.: Leia o texto abaixo para responder às questões 11 a 15." />
        </div>
      ) : (
        <button type="button" className="btn ghost sm" style={{ marginBottom: 6 }} onClick={() => setShowSection(true)}>
          + Título de seção antes desta questão
        </button>
      )}

      <RichArea value={q.stem} onChange={(stem) => onChange({ ...q, stem })} placeholder="Enunciado da questão" />

      <div className="qimg">
        {q.image && examId ? (
          <>
            <AuthImage path={`/exams/${examId}/assets/${q.image}`} />
            <label className="f" style={{ flex: 1, maxWidth: 220 }}>
              Largura na coluna: {q.image_width}%
              <input type="range" min={15} max={100} step={5} value={q.image_width} onChange={(e) => onChange({ ...q, image_width: +e.target.value })} />
            </label>
            <button type="button" className="btn sm ghost danger" onClick={() => onChange({ ...q, image: null })}>Remover imagem</button>
          </>
        ) : (
          <>
            <button type="button" className="btn sm" disabled={!examId || up.busy} onClick={() => fileRef.current?.click()}
              title={examId ? "" : "Salve a prova uma vez para poder anexar imagens"}>
              {up.busy ? "Enviando…" : "Anexar imagem"}
            </button>
            {!examId && <span className="small muted">Salve a prova uma vez para anexar imagens.</span>}
          </>
        )}
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
      </div>
      <ErrorBox error={up.error} />

      <div style={{ marginTop: 10 }}>
        {q.options.map((opt, i) => {
          const L = LETTERS[i];
          return (
            <div className="opt" key={i}>
              <button type="button" className={`pick${chosen.includes(L) ? " on" : ""}`} onClick={() => pick(L)}
                title={annulled ? "Questão anulada" : "Marcar como correta"}>{L}</button>
              <div className="opt-body">
                <input type="text" value={opt} placeholder={q.option_images[i] ? `Legenda (opcional)` : `Alternativa ${L}`}
                  onChange={(e) => setOptions(q.options.map((o, j) => (j === i ? e.target.value : o)))} />
                {q.option_images[i] && examId && (
                  <div className="opt-img">
                    <AuthImage path={`/exams/${examId}/assets/${q.option_images[i]}`} alt={`Imagem da alternativa ${L}`} />
                    <button type="button" className="btn ghost sm danger"
                      onClick={() => onChange({ ...q, option_images: q.option_images.map((x, j) => (j === i ? null : x)) })}>
                      Remover imagem
                    </button>
                  </div>
                )}
              </div>
              <button type="button" className="btn ghost sm" disabled={!examId || up.busy}
                title={examId ? (q.option_images[i] ? "Trocar imagem" : "Imagem nesta alternativa") : "Salve a prova uma vez para anexar imagens"}
                onClick={() => { setOptTarget(i); optFileRef.current?.click(); }}>🖼</button>
              <button type="button" className="btn ghost sm" disabled={q.options.length <= 2} title="Remover alternativa"
                onClick={() => setOptions(q.options.filter((_, j) => j !== i), q.option_images.filter((_, j) => j !== i))}>×</button>
            </div>
          );
        })}
        <input ref={optFileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadOption(f); e.target.value = ""; }} />
        {hasOptionImages && (
          <label className="f" style={{ maxWidth: 280, marginTop: 8 }}>
            Altura das imagens das alternativas: {q.option_image_height} mm
            <input type="range" min={10} max={80} step={2} value={q.option_image_height}
              onChange={(e) => onChange({ ...q, option_image_height: +e.target.value })} />
          </label>
        )}
      </div>

      <div className="row small" style={{ marginTop: 10, gap: 16 }}>
        <button type="button" className="btn sm" disabled={q.options.length >= 6} onClick={() => setOptions([...q.options, ""], [...q.option_images, null])}>+ Alternativa</button>
        <label className="check">
          <input type="checkbox" checked={multi} disabled={annulled}
            onChange={(e) => onChange({ ...q, correct: e.target.checked ? chosen.length ? chosen : ["A"] : chosen[0] ?? "A" })} />
          Aceitar mais de uma
        </label>
        <label className="check">
          <input type="checkbox" checked={annulled} onChange={(e) => onChange({ ...q, correct: e.target.checked ? null : "A" })} />
          Anular (ponto para todos)
        </label>
        <label className="check">
          Peso
          <input type="number" min={0.25} max={100} step={0.25} value={q.weight} style={{ width: 76 }}
            onChange={(e) => onChange({ ...q, weight: Math.max(0.25, +e.target.value || 1) })} />
        </label>
      </div>
    </div>
  );
}

function LogoField({ examId, header, onChange }: { examId?: string; header: Header; onChange: (h: Header) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const up = useAction();
  async function send(file: File) {
    if (!examId) return;
    const r = await up.run(() => api.upload<{ id: string }>(`/exams/${examId}/assets`, file, file.name));
    if (r) onChange({ ...header, logo: r.id, show_logo: true });
  }
  return (
    <div className="stack" style={{ gap: 6 }}>
      <span className="small" style={{ fontWeight: 600, color: "var(--muted)" }}>Logo da escola</span>
      {header.logo && examId ? (
        <div className="row" style={{ gap: 10 }}>
          <AuthImage path={`/exams/${examId}/assets/${header.logo}`} alt="Logo" className="logo-thumb" />
          <div className="stack" style={{ gap: 4 }}>
            <label className="check">
              <input type="checkbox" checked={header.show_logo} onChange={(e) => onChange({ ...header, show_logo: e.target.checked })} />
              Mostrar no caderno
            </label>
            <div className="row" style={{ gap: 4 }}>
              <button type="button" className="btn ghost sm" onClick={() => ref.current?.click()} disabled={up.busy}>Trocar</button>
              <button type="button" className="btn ghost sm danger" onClick={() => onChange({ ...header, logo: null })}>Remover</button>
            </div>
          </div>
        </div>
      ) : (
        <button type="button" className="btn sm" disabled={!examId || up.busy} onClick={() => ref.current?.click()}
          title={examId ? "" : "Salve a prova uma vez para enviar a logo"}>
          {up.busy ? "Enviando…" : "Enviar logo (opcional)"}
        </button>
      )}
      {!examId && <span className="small muted">Salve a prova uma vez para enviar a logo.</span>}
      <ErrorBox error={up.error} />
      <input ref={ref} type="file" accept="image/png,image/jpeg,image/webp" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) send(f); e.target.value = ""; }} />
    </div>
  );
}

function KeyOnly({ n, setN, opts, setOpts, keyArr, setKey }: {
  n: number; setN: (n: number) => void; opts: number; setOpts: (n: number) => void; keyArr: Correct[]; setKey: (k: Correct[]) => void;
}) {
  return (
    <div className="card">
      <h2>Gabarito</h2>
      <p className="muted small" style={{ marginTop: -6 }}>
        Use quando a prova já está pronta em outro lugar (Word, livro…). O sistema gera só os cartões-resposta.
      </p>
      <div className="row" style={{ marginBottom: 14 }}>
        <label className="f">Questões
          <input type="number" min={1} max={116} value={n} style={{ width: 90 }} onChange={(e) => setN(Math.min(116, Math.max(1, +e.target.value || 1)))} />
        </label>
        <label className="f">Alternativas
          <select value={opts} onChange={(e) => setOpts(+e.target.value)} style={{ width: 120 }}>
            {[2, 3, 4, 5, 6].map((k) => <option key={k} value={k}>{LETTERS.slice(0, k).split("").join(", ")}</option>)}
          </select>
        </label>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: "6px 18px" }}>
        {Array.from({ length: n }, (_, i) => (
          <div key={i} className="row" style={{ gap: 6 }}>
            <span className="num" style={{ width: 26, textAlign: "right", fontWeight: 700 }}>{String(i + 1).padStart(2, "0")}</span>
            <div className="mini">
              {LETTERS.slice(0, opts).split("").map((L) => (
                <span key={L} className={keyArr[i] === L ? "on key" : ""} style={{ cursor: "pointer" }}
                  onClick={() => setKey(keyArr.map((k, j) => (j === i ? L : k)))}>{L}</span>
              ))}
            </div>
            <button type="button" className={`btn ghost sm${keyArr[i] === null ? " danger" : ""}`} title="Anular questão"
              onClick={() => setKey(keyArr.map((k, j) => (j === i ? (k === null ? "A" : null) : k)))}>
              {keyArr[i] === null ? "anulada" : "anular"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ExamEditor({ examId }: { examId?: string }) {
  const router = useRouter();
  const [loaded, setLoaded] = useState(!examId);
  const [mode, setMode] = useState<Mode>("editor");
  const [title, setTitle] = useState("");
  const [header, setHeader] = useState<Header>(DEFAULT_HEADER);
  const [style, setStyle] = useState<Style>(DEFAULT_STYLE);
  const [questions, setQuestions] = useState<Question[]>([newQuestion(), newQuestion()]);
  const [sheetCols, setSheetCols] = useState(4);
  const [nQ, setNQ] = useState(20);
  const [nOpt, setNOpt] = useState(5);
  const [keyArr, setKeyArr] = useState<Correct[]>(Array(20).fill("A"));
  const [locked, setLocked] = useState(false);
  const [version, setVersion] = useState(1);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<"questoes" | "preview">("questoes");
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const save = useAction();

  useEffect(() => {
    if (!examId) return;
    api.get<ExamFull>(`/exams/${examId}`).then((e) => {
      setTitle(e.title);
      setLocked(e.locked);
      setVersion(e.version);
      setSheetCols(e.grid_spec.columns);
      if (e.content) {
        setMode("editor");
        setHeader({ ...DEFAULT_HEADER, ...e.content.header });
        setStyle({ ...DEFAULT_STYLE, ...(e.style || {}) });
        setQuestions(e.content.questions.map(normalizeQuestion));
      } else {
        setMode("cartao");
        setNQ(e.grid_spec.n_questions);
        setNOpt(e.grid_spec.n_options);
        setKeyArr(Array.from({ length: e.grid_spec.n_questions }, (_, i) => e.answer_key[String(i + 1)] ?? null));
      }
      setLoaded(true);
    }).catch((err) => setLoadError(err.message));
  }, [examId]);

  // aviso ao sair com alterações não salvas
  useEffect(() => {
    const h = (ev: BeforeUnloadEvent) => { if (dirty) { ev.preventDefault(); ev.returnValue = ""; } };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  const touch = <T,>(setter: (v: T) => void) => (v: T) => { setter(v); setDirty(true); };
  const setQs = touch(setQuestions);
  const updateQ = (i: number, q: Question) => setQs(questions.map((x, j) => (j === i ? q : x)));

  function body() {
    if (mode === "cartao") {
      const answer_key = Object.fromEntries(keyArr.slice(0, nQ).map((k, i) => [String(i + 1), k]));
      return { title: title.trim(), columns: sheetCols, n_questions: nQ, n_options: nOpt, answer_key };
    }
    return { title: title.trim(), columns: sheetCols, content: { header, questions }, style };
  }

  function validate(): string | null {
    if (!title.trim()) return "Dê um título à prova.";
    if (mode === "editor") {
      const empty = questions.findIndex((q) => !q.stem.trim() && !q.image);
      if (empty >= 0) return `A questão ${empty + 1} está sem enunciado.`;
      const noOpt = questions.findIndex((q) => q.options.some((o, i) => !o.trim() && !q.option_images[i]));
      if (noOpt >= 0) return `A questão ${noOpt + 1} tem alternativa vazia (coloque texto ou imagem).`;
    }
    return null;
  }

  async function doSave(thenPreview = false) {
    const problem = validate();
    if (problem) return save.setError(problem);
    setNotice(null);
    const res = await save.run(async () => {
      if (!examId) return { created: await api.post<{ id: string }>("/exams", body()) };
      return { updated: await api.put<{ version: number; new_version: boolean }>(`/exams/${examId}`, body()) };
    });
    if (!res) return;
    setDirty(false);
    if ("created" in res && res.created) {
      router.replace(`/provas/${res.created.id}/editar`);
      return;
    }
    if ("updated" in res && res.updated) {
      setVersion(res.updated.version);
      if (res.updated.new_version) {
        setLocked(false);
        setNotice(`Salvo como versão ${res.updated.version}. Os cartões já impressos continuam sendo corrigidos pela versão anterior.`);
      } else setNotice("Prova salva.");
    }
    if (thenPreview && examId && mode === "editor") {
      setTab("preview");
      setPreviewHtml(null);
      const html = await save.run(() => api.text(`/exams/${examId}/booklet?format=html`));
      if (html) setPreviewHtml(html);
    }
  }

  if (loadError) return <ErrorBox error={loadError} />;
  if (!loaded) return <p className="muted">Carregando…</p>;

  return (
    <>
      <PageHead
        crumbs={<><Link href="/provas">Provas</Link>{examId && <> › <Link href={`/provas/${examId}`}>{title || "prova"}</Link></>}</>}
        title={examId ? "Editar prova" : "Nova prova"}
        sub={examId ? `Versão ${version}${dirty ? " · alterações não salvas" : ""}` : "Escreva as questões e marque a alternativa correta de cada uma."}
        actions={examId && <Link className="btn" href={`/provas/${examId}`}>Imprimir e notas →</Link>}
      />

      {locked && (
        <div className="alert info" style={{ marginBottom: 14 }}>
          Esta versão já foi impressa. Se você salvar mudanças, será criada a <b>versão {version + 1}</b>; os cartões
          já impressos continuam sendo corrigidos pelo gabarito da versão {version}.
        </div>
      )}
      {notice && <div className="alert ok" style={{ marginBottom: 14 }}>{notice}</div>}
      <ErrorBox error={save.error} />

      {!examId && (
        <div className="tabs">
          <button className={mode === "editor" ? "on" : ""} onClick={() => setMode("editor")}>Prova completa (caderno + cartão)</button>
          <button className={mode === "cartao" ? "on" : ""} onClick={() => setMode("cartao")}>Só cartão-resposta</button>
        </div>
      )}

      <div className="editor">
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <label className="f">Título da prova
              <input type="text" value={title} onChange={(e) => touch(setTitle)(e.target.value)} placeholder="Ex.: Avaliação de Matemática — 2º bimestre" />
            </label>
          </div>

          {mode === "cartao" ? (
            <KeyOnly n={nQ} opts={nOpt} keyArr={keyArr}
              setN={(n) => { setNQ(n); setKeyArr(Array.from({ length: n }, (_, i) => keyArr[i] === undefined ? "A" : keyArr[i])); setDirty(true); }}
              setOpts={(k) => { setNOpt(k); setKeyArr(keyArr.map((x) => (x && LETTERS.indexOf(x as string) >= k ? "A" : x))); setDirty(true); }}
              setKey={touch(setKeyArr)} />
          ) : (
            <>
              <div className="tabs">
                <button className={tab === "questoes" ? "on" : ""} onClick={() => setTab("questoes")}>Questões ({questions.length})</button>
                <button className={tab === "preview" ? "on" : ""} disabled={!examId}
                  title={examId ? "" : "Salve a prova primeiro"} onClick={() => doSave(true)}>Pré-visualizar</button>
              </div>
              {tab === "questoes" ? (
                <>
                  {questions.map((q, i) => (
                    <QuestionCard key={i} q={q} index={i} total={questions.length} examId={examId}
                      onChange={(nq) => updateQ(i, nq)}
                      onMove={(d) => { const a = [...questions]; [a[i], a[i + d]] = [a[i + d], a[i]]; setQs(a); }}
                      onDuplicate={() => setQs([...questions.slice(0, i + 1), { ...q, options: [...q.options] }, ...questions.slice(i + 1)])}
                      onRemove={() => setQs(questions.filter((_, j) => j !== i))} />
                  ))}
                  <div className="row" style={{ marginTop: 12 }}>
                    <button className="btn" disabled={questions.length >= 116}
                      onClick={() => setQs([...questions, newQuestion(questions[questions.length - 1]?.options.length || 5)])}>
                      + Nova questão
                    </button>
                  </div>
                </>
              ) : previewHtml ? (
                <iframe className="preview" srcDoc={previewHtml} title="Pré-visualização do caderno" sandbox="" />
              ) : (
                <p className="muted">Gerando pré-visualização…</p>
              )}
            </>
          )}
          <div className="savebar row">
            <button className="btn primary" disabled={save.busy} onClick={() => doSave(false)}>
              {save.busy ? "Salvando…" : examId ? "Salvar" : "Criar prova"}
            </button>
            {dirty && <span className="small muted">Alterações não salvas</span>}
          </div>
        </div>

        <aside>
          {mode === "editor" && (
            <>
              <div className="card stack">
                <h3>Cabeçalho</h3>
                <LogoField examId={examId} header={header} onChange={touch(setHeader)} />
                <label className="f">Escola
                  <input type="text" value={header.school} onChange={(e) => touch(setHeader)({ ...header, school: e.target.value })} />
                </label>
                <label className="f">Subtítulo
                  <input type="text" value={header.subtitle} placeholder="Disciplina, professor, bimestre" onChange={(e) => touch(setHeader)({ ...header, subtitle: e.target.value })} />
                </label>
                <label className="f">Instruções
                  <RichArea rows={3} value={header.instructions} onChange={(v) => touch(setHeader)({ ...header, instructions: v })} placeholder="Ex.: Use caneta azul ou preta." />
                </label>
                <label className="check"><input type="checkbox" checked={header.show_grade_box} onChange={(e) => touch(setHeader)({ ...header, show_grade_box: e.target.checked })} /> Quadro de nota</label>
              </div>
              <div className="card stack">
                <h3>Aparência do caderno</h3>
                <label className="f">Fonte
                  <select value={style.font_family} onChange={(e) => touch(setStyle)({ ...style, font_family: e.target.value as Style["font_family"] })}>
                    <option value="serif">Serifada (Times)</option>
                    <option value="sans">Sem serifa (Arial)</option>
                    <option value="mono">Monoespaçada</option>
                  </select>
                </label>
                <div className="row" style={{ gap: 8 }}>
                  <label className="f" style={{ flex: 1 }}>Tamanho
                    <select value={style.font_size_pt} onChange={(e) => touch(setStyle)({ ...style, font_size_pt: +e.target.value })}>
                      {[9, 10, 11, 12, 13, 14].map((s) => <option key={s} value={s}>{s} pt</option>)}
                    </select>
                  </label>
                  <label className="f" style={{ flex: 1 }}>Colunas
                    <select value={style.columns} onChange={(e) => touch(setStyle)({ ...style, columns: +e.target.value as 1 | 2 })}>
                      <option value={1}>1</option>
                      <option value={2}>2</option>
                    </select>
                  </label>
                </div>
                <label className="f">Espaçamento entre linhas
                  <select value={style.line_height} onChange={(e) => touch(setStyle)({ ...style, line_height: +e.target.value })}>
                    {[1.15, 1.35, 1.5, 1.75].map((s) => <option key={s} value={s}>{s.toLocaleString("pt-BR")}</option>)}
                  </select>
                </label>
                <label className="f">Alternativas
                  <select value={style.option_layout} onChange={(e) => touch(setStyle)({ ...style, option_layout: e.target.value as Style["option_layout"] })}>
                    <option value="vertical">Uma por linha</option>
                    <option value="horizontal">Lado a lado</option>
                  </select>
                </label>
                <label className="check"><input type="checkbox" checked={style.show_points} onChange={(e) => touch(setStyle)({ ...style, show_points: e.target.checked })} /> Mostrar pontos por questão</label>
                <label className="check"><input type="checkbox" checked={style.column_rule} onChange={(e) => touch(setStyle)({ ...style, column_rule: e.target.checked })} /> Linha entre colunas</label>
              </div>
            </>
          )}
          <div className="card stack">
            <h3>Cartão-resposta</h3>
            <label className="f">Colunas de bolhas
              <select value={sheetCols} onChange={(e) => touch(setSheetCols)(+e.target.value)}>
                {[1, 2, 3, 4, 5].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <p className="small muted" style={{ margin: 0 }}>
              Se não couber, o sistema escolhe outro número de colunas automaticamente.
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}

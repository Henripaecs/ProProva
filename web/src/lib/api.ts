// Cliente da API FastAPI. Token fica no localStorage; 401 manda de volta para o login.
import { appDownload, isApp } from "@/lib/app";

// "/" (ou "") = mesma origem do painel: em produção o próprio painel/Caddy repassa /v1 para a API.
// Ausente = API local de desenvolvimento (npm run dev).
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const TOKEN_KEY = "omr.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* navegador sem storage: segue só na memória da aba */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.hint === "string" && b.hint) return `${b.message ?? ""} ${b.hint}`.trim();
    if (typeof b.detail === "string") return b.detail;
    if (Array.isArray(b.detail)) {
      // erros de validação do Pydantic → primeira mensagem legível
      const first = b.detail[0] as { msg?: string; loc?: unknown[] } | undefined;
      if (first?.msg) {
        const where = (first.loc || []).filter((x) => x !== "body").join(" › ");
        return `${first.msg.replace(/^Value error, /, "")}${where ? ` (${where})` : ""}`;
      }
    }
  }
  if (status === 0) return "Sem conexão com a API. Ela está rodando?";
  return `Erro ${status}`;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, errorMessage(0, null));
  }
  if (res.status === 401 && !path.startsWith("/auth/")) {
    setToken(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login?expirou=1";
    }
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* sem corpo JSON */
    }
    throw new ApiError(res.status, errorMessage(res.status, body), body);
  }
  return res;
}

export const api = {
  async get<T>(path: string): Promise<T> {
    return (await request(path)).json();
  },
  async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await request(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
    return res.status === 204 ? (undefined as T) : res.json();
  },
  async put<T>(path: string, body: unknown): Promise<T> {
    return (await request(path, { method: "PUT", body: JSON.stringify(body) })).json();
  },
  async patch<T>(path: string, body: unknown): Promise<T> {
    return (await request(path, { method: "PATCH", body: JSON.stringify(body) })).json();
  },
  async del(path: string): Promise<void> {
    await request(path, { method: "DELETE" });
  },
  async upload<T>(path: string, file: Blob, filename = "arquivo"): Promise<T> {
    const fd = new FormData();
    fd.append("file", file, filename);
    return (await request(path, { method: "POST", body: fd })).json();
  },
  async text(path: string): Promise<string> {
    return (await request(path)).text();
  },
  /** Baixa um arquivo autenticado (PDF, ZIP, CSV) e devolve o blob + nome sugerido. */
  async blob(path: string): Promise<{ blob: Blob; filename: string | null; headers: Headers }> {
    const res = await request(path);
    const cd = res.headers.get("Content-Disposition") || "";
    const m = /filename="?([^";]+)"?/.exec(cd);
    return { blob: await res.blob(), filename: m ? m[1] : null, headers: res.headers };
  },
};

export function saveBlob(blob: Blob, filename: string) {
  if (isApp()) {
    void appDownload(blob, filename);
    return;
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

// ── tipos da API ────────────────────────────────────────────────────────────
export type ClassRow = { id: string; name: string };
export type Student = { id: string; name: string; enrollment: string | null };
export type ClassDetail = ClassRow & { students: Student[] };

export type Correct = string | string[] | null;
export type Question = {
  stem: string;
  image: string | null;
  image_width: number;
  options: string[];
  option_images: (string | null)[];   // imagem por alternativa (mesmo tamanho de options)
  option_image_height: number;        // mm
  section: string;                    // título de seção antes desta questão (ex.: "Matemática")
  section_text: string;               // texto de apoio da seção
  correct: Correct;
  weight: number;
};
export type Header = {
  school: string;
  subtitle: string;
  instructions: string;
  show_grade_box: boolean;
  logo: string | null;
  show_logo: boolean;
};
export type Style = {
  font_family: "serif" | "sans" | "mono";
  font_size_pt: number;
  columns: 1 | 2;
  line_height: number;
  option_layout: "vertical" | "horizontal";
  show_points: boolean;
  column_rule: boolean;
};
export type Content = { header: Header; questions: Question[] };

export type ExamRow = {
  id: string;
  title: string;
  created_at: string;
  version: number;
  n_questions: number;
  n_options: number;
  locked: boolean;
  has_booklet: boolean;
  n_scans: number;
};
export type ExamFull = {
  id: string;
  title: string;
  version: number;
  locked: boolean;
  content: Content | null;
  style: Style | null;
  grid_spec: { n_questions: number; n_options: number; columns: number };
  answer_key: Record<string, Correct>;
  weights: Record<string, number> | null;
};

export type Score = {
  points: number;
  max_points: number;
  correct: number;
  wrong: number;
  blank: number;
  annulled: number;
  pending: number;
  detail: Record<string, string>;
};
export type ResultRow = {
  scan_id: string;
  student_id: string;
  student_name: string;
  created_at: string;
  score: Score;
  review_needed: number[];
};
export type Answer = {
  number: number;
  status: "blank" | "single" | "multiple" | "ambiguous";
  fills: number[];
  marked: string[];
  answer: string | null;
  confidence: number;
  needs_review: boolean;
  source: "omr" | "human";
};
export type ScanDetail = {
  id: string;
  created_at: string;
  student_id: string;
  student_name: string;
  exam_id: string;
  exam_title: string;
  version: number;
  options: string;
  answer_key: Record<string, Correct>;
  score: Score;
  answers: Answer[];
  review_needed: number[];
};
export type ScanResponse = {
  scan_id: string;
  exam_id: string;
  student_id: string;
  review_needed: number[];
  score: Score;
};

export const DEFAULT_STYLE: Style = {
  font_family: "serif",
  font_size_pt: 11,
  columns: 2,
  line_height: 1.35,
  option_layout: "vertical",
  show_points: false,
  column_rule: true,
};
export const DEFAULT_HEADER: Header = {
  school: "", subtitle: "", instructions: "", show_grade_box: true, logo: null, show_logo: true,
};
export const LETTERS = "ABCDEF";

export function newQuestion(nOptions = 5): Question {
  return {
    stem: "", image: null, image_width: 60, options: Array(nOptions).fill(""), option_images: Array(nOptions).fill(null),
    option_image_height: 28, section: "", section_text: "", correct: "A", weight: 1,
  };
}

/** Completa questões salvas em versões anteriores (sem imagens nas alternativas / seção). */
export function normalizeQuestion(q: Partial<Question> & { options: string[] }): Question {
  const n = q.options.length;
  return {
    ...newQuestion(n),
    ...q,
    option_images: Array.from({ length: n }, (_, i) => q.option_images?.[i] ?? null),
  } as Question;
}

export function fmtScore(n: number): string {
  return n.toLocaleString("pt-BR", { minimumFractionDigits: n % 1 ? 1 : 0, maximumFractionDigits: 2 });
}

export function fmtDate(iso: string): string {
  const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  return isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** <img> para rotas protegidas por token (o navegador não manda o header Authorization em <img src>). */
export default function AuthImage({ path, alt = "", className, style }: { path: string; alt?: string; className?: string; style?: React.CSSProperties }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    let objectUrl: string | null = null;
    setFailed(false);
    api
      .blob(path)
      .then(({ blob }) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (failed) return <span className="small muted">imagem indisponível</span>;
  if (!url) return <span className="small muted">carregando…</span>;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={alt} className={className} style={style} />;
}

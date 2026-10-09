// An evidence crop, fetched with the signed-in user's Authorization header (api.cropUrl) and shown from memory:
// a token in an <img> URL would end up in browser history, proxy logs and screenshots.
import { useEffect, useState } from "react";
import { cropUrl } from "../api";

export default function CropImg({ path, className, alt = "", onError }: {
  path: string; className?: string; alt?: string; onError?: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setSrc(null);
    cropUrl(path).then((u) => { if (live) setSrc(u); }, () => { if (live) onError?.(); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
  return src ? <img className={className} src={src} alt={alt} onError={onError} /> : null;
}

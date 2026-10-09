import { CaptureQuality, reasonLabel } from "../api";

/** A capture's grade, with what held it back in the tooltip. Shows nothing until the crop is graded. */
export default function QualityBadge({ q }: { q: CaptureQuality | null | undefined }) {
  if (!q) return null;
  const why = q.reasons.map(reasonLabel).join(", ");
  return <span className={`q q-${q.quality}`} title={`Capture ${q.quality}${why ? `: ${why}` : ""}`}>{q.quality}</span>;
}

import { Copy, ExternalLink } from "lucide-react";
export function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
export function Score({ n }: { n: number }) {
  return (
    <span className={n >= 85 ? "score hot" : n >= 75 ? "score warm" : "score"}>
      {Math.round(n || 0)}
    </span>
  );
}
export function Pill({ value }: { value: string }) {
  return <span className={`pill ${value}`}>{label(value)}</span>;
}
export function Card({ title, children }: { title: string; children: any }) {
  return (
    <div className="card">
      <h4>{title}</h4>
      {children}
    </div>
  );
}
export function Block({ title, text }: { title: string; text?: string }) {
  return (
    <div className="summaryBlock">
      <h3>{title}</h3>
      <p>{text || "-"}</p>
    </div>
  );
}
export function CopyBlock({ title, text }: { title: string; text?: string }) {
  return (
    <Card title={title}>
      <pre>{text || "-"}</pre>
      <button onClick={() => navigator.clipboard.writeText(text || "")}>
        <Copy size={15} />
        Copy
      </button>
    </Card>
  );
}
export function SourceLink({ url, label }: { url?: string; label?: string }) {
  if (!url) return <>-</>;
  return (
    <a className="sourceLink" href={url} target="_blank">
      <span>{label || url}</span>
      <ExternalLink size={14} />
    </a>
  );
}
export function label(v: string) {
  return (v || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}
export function date(v?: string) {
  return v ? new Date(v).toLocaleDateString() : "-";
}

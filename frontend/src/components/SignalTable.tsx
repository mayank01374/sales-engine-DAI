import type { DiscoveredSignal } from "../types";
import { Score, Pill, SourceLink, date, label } from "./ui";
export function SignalTable({
  items,
  onSelect,
}: {
  items: DiscoveredSignal[];
  onSelect: (s: DiscoveredSignal) => void;
  compact?: boolean;
}) {
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Final Score</th>
            <th>Matter</th>
            <th>Parties</th>
            <th>Matter Type</th>
            <th>Trigger</th>
            <th>Source</th>
            <th>Freshness</th>
            <th>Discovery Pain</th>
            <th>DecoverAI Fit</th>
            <th>Persona</th>
            <th>Sales Angle</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id} onClick={() => onSelect(s)}>
              <td>
                <Score n={s.final_trigger_score} />
              </td>
              <td>
                <b>{s.title}</b>
              </td>
              <td>{s.parties?.join(", ") || "-"}</td>
              <td>{s.matter_type || s.case_type}</td>
              <td>{label(s.trigger_category || s.trigger_type)}</td>
              <td>
                <SourceLink
                  url={s.source_url}
                  label={`${label(s.source_tier || "")} · ${s.publisher || s.source_domain}`}
                />
              </td>
              <td>
                <Pill value={s.freshness_status} />
                <small>
                  {date(s.signal_date || s.published_at)}
                  {s.signal_age_days != null ? ` · ${s.signal_age_days}d` : ""}
                </small>
              </td>
              <td>{Math.round(s.discovery_pain_score)}</td>
              <td>{Math.round(s.dcover_fit_score)}</td>
              <td>{s.recommended_personas?.[0] || "-"}</td>
              <td>{s.sales_angle_one_liner}</td>
              <td>
                <Pill value={s.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import { useEffect, useState } from "react";
import { api } from "../api";
import type { Opportunity } from "../types";
import { OpportunityDrawer } from "../components/OpportunityDrawer";
import { Score, SourceLink } from "../components/ui";
export function Opportunities() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const load = async () =>
    setItems(
      (
        await api.opportunities({
          page_size: 50,
          sort_by: "final_trigger_score",
        })
      ).items,
    );
  useEffect(() => {
    load();
  }, []);
  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Opportunities</h1>
          <p>Qualified or converted matters sales is actively working.</p>
        </div>
        <button onClick={api.exportCsv}>Export CSV</button>
      </header>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Score</th>
              <th>Matter</th>
              <th>Status</th>
              <th>Parties</th>
              <th>Persona</th>
              <th>Sales Angle</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.id} onClick={() => setSelected(o)}>
                <td>
                  <Score n={o.final_trigger_score || o.score} />
                </td>
                <td>
                  <b>{o.case_name}</b>
                  <small>{o.matter_type || o.case_type}</small>
                </td>
                <td>{o.status}</td>
                <td>{o.parties?.join(", ") || "-"}</td>
                <td>{o.recommended_persona}</td>
                <td>{o.sales_angle_one_liner || o.pitch_angle}</td>
                <td>
                  <SourceLink
                    url={o.evidence?.[0]?.source_url}
                    label={o.evidence?.[0]?.publisher}
                  />
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">
                  No opportunities yet. Convert a passing signal from Discovery
                  Runs.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {selected && (
        <OpportunityDrawer
          opp={selected}
          onClose={() => {
            setSelected(null);
            load();
          }}
        />
      )}
    </div>
  );
}

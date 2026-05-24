import { useEffect, useState } from "react";
import { Download, RefreshCw, Search } from "lucide-react";
import { api } from "../api";
import type { AppSettings, DiscoveredSignal, QualitySummary } from "../types";
import type { Page } from "../navigation";
import { SignalTable } from "../components/SignalTable";
import { SignalDrawer } from "../components/SignalDrawer";
import { label } from "../components/ui";

const salesStatuses = ["new", "qualified", "contacted", "needs_more_research", "rejected"];
export function DailyTriggers({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const [items, setItems] = useState<DiscoveredSignal[]>([]);
  const [selected, setSelected] = useState<DiscoveredSignal | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [summary, setSummary] = useState<QualitySummary | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [filters, setFilters] = useState({
    matter_type: "",
    trigger_category: "",
    min_source_quality: "",
    min_score: "",
    status: "",
    date_from: "",
    date_to: "",
  });

  const load = async () => {
    setLoading(true);
    setErr("");
    try {
      const nextSettings = await api.settings();
      setSettings(nextSettings);
      const res = await api.dailyTriggers({
        ...filters,
        page_size: nextSettings.max_daily_triggers || 50,
      });
      setItems(res.items);
      setSummary(await api.qualitySummary());
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, []);

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Daily Triggers</h1>
          <p>
            Fresh litigation matters from the last 90 days where DecoverAI may
            help with discovery, review, privilege, redaction, or production.
          </p>
        </div>
        <div className="actions">
          <button onClick={() => api.exportDailyTriggers(filters)}>
            <Download size={16} />
            Export Excel
          </button>
          <button onClick={load}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </header>
      <div className="warning">
        Only signals passing the DecoverAI quality gate appear here. Verify
        source evidence before outreach.
      </div>
      <section className="filters">
        <div className="search">
          <Search size={16} />
          <input
            placeholder="Matter type"
            value={filters.matter_type}
            onChange={(e) =>
              setFilters({ ...filters, matter_type: e.target.value })
            }
          />
        </div>
        <input
          placeholder="Trigger category"
          value={filters.trigger_category}
          onChange={(e) =>
            setFilters({ ...filters, trigger_category: e.target.value })
          }
        />
        <input
          type="number"
          placeholder="Min score"
          value={filters.min_score}
          onChange={(e) =>
            setFilters({ ...filters, min_score: e.target.value })
          }
        />
        <input
          type="number"
          placeholder="Min source quality"
          value={filters.min_source_quality}
          onChange={(e) =>
            setFilters({ ...filters, min_source_quality: e.target.value })
          }
        />
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">All statuses</option>
          {salesStatuses.map((s) => (
            <option key={s} value={s}>
              {label(s)}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={filters.date_from}
          onChange={(e) =>
            setFilters({ ...filters, date_from: e.target.value })
          }
        />
        <input
          type="date"
          value={filters.date_to}
          onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
        />
        <button onClick={load}>Apply</button>
      </section>
      {err && <div className="error">{err}</div>}
      {loading && (
        <div className="empty">Loading high-confidence triggers...</div>
      )}
      <SignalTable items={items} onSelect={setSelected} compact={false} />
      {!loading && items.length === 0 && (
        <div className="emptyState">
          <h3>No high-confidence triggers yet</h3>
          <p>
            No high-confidence triggers yet. Run Discovery using court/docket
            and trusted legal-news sources.
          </p>
          <div className="actions">
            <button onClick={() => onNavigate("runs")}>Run Discovery</button>
            <button onClick={() => onNavigate("runs")}>View Failed Signals</button>
            <button onClick={() => onNavigate("settings")}>Open Settings</button>
          </div>
          {summary && (
            <div className="summaryStats">
              <span>
                Last run: <b>{summary.last_run_status || "none"}</b>
              </span>
              <span>
                Raw: <b>{summary.total_raw_signals}</b>
              </span>
              <span>
                Passed: <b>{summary.passed_gate}</b>
              </span>
              <span>
                Failed: <b>{summary.failed_gate}</b>
              </span>
              <span>
                Top failures:{" "}
                <b>
                  {summary.top_failure_reasons
                    .map((r) => `${label(r.reason)} (${r.count})`)
                    .join(", ") || "-"}
                </b>
              </span>
            </div>
          )}
        </div>
      )}
      {selected && (
        <SignalDrawer
          signal={selected}
          onClose={() => {
            setSelected(null);
            load();
          }}
        />
      )}
    </div>
  );
}

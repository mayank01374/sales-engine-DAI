import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Ban,
  CheckCircle,
  Copy,
  Database,
  Download,
  ExternalLink,
  Eye,
  FileSearch,
  Globe,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  X,
} from "lucide-react";
import { api } from "./api";
import type {
  AppSettings,
  DiscoveredSignal,
  LLMStatus,
  Opportunity,
  QualitySummary,
  WebDiscoveryRun,
} from "./types";
import "./styles.css";

const salesStatuses = [
  "new",
  "qualified",
  "contacted",
  "needs_more_research",
  "rejected",
];

function App() {
  const [page, setPage] = useState<
    "daily" | "runs" | "opportunities" | "settings"
  >("daily");
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img className="logo" src="/download.png" alt="DecoverAI logo" />
          <div className="brandText">
            <span>Sales Engine</span>
          </div>
        </div>
        <button
          className={page === "daily" ? "active" : ""}
          onClick={() => setPage("daily")}
        >
          <FileSearch size={18} />
          <span>Daily Triggers</span>
        </button>
        <button
          className={page === "runs" ? "active" : ""}
          onClick={() => setPage("runs")}
        >
          <Globe size={18} />
          <span>Discovery Runs</span>
        </button>
        <button
          className={page === "opportunities" ? "active" : ""}
          onClick={() => setPage("opportunities")}
        >
          <Database size={18} />
          <span>Opportunities</span>
        </button>
        <button
          className={page === "settings" ? "active" : ""}
          onClick={() => setPage("settings")}
        >
          <SettingsIcon size={18} />
          <span>Settings</span>
        </button>
      </aside>
      <main>
        {page === "daily" && <DailyTriggers />}
        {page === "runs" && <DiscoveryRuns />}
        {page === "opportunities" && <Opportunities />}
        {page === "settings" && <Settings />}
      </main>
    </div>
  );
}

function DailyTriggers() {
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
            <button>Run Discovery</button>
            <button>View Failed Signals</button>
            <button>Open Settings</button>
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

function DiscoveryRuns() {
  const [runs, setRuns] = useState<WebDiscoveryRun[]>([]);
  const [signals, setSignals] = useState<DiscoveredSignal[]>([]);
  const [selectedRun, setSelectedRun] = useState<number | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<DiscoveredSignal | null>(
    null,
  );
  const [tab, setTab] = useState("all");
  const [err, setErr] = useState("");
  const [toast, setToast] = useState("");
  const [running, setRunning] = useState(false);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [maxResults, setMaxResults] = useState(40);
  const latestRun = runs[0];

  const loadRuns = async () => {
    const cfg = await api.settings();
    if (!settings) setMaxResults(cfg.default_max_results || 40);
    setSettings(cfg);
    const data = await api.webDiscoveryRuns();
    setRuns(data);
    if (!selectedRun && data[0]) setSelectedRun(data[0].id);
  };
  const loadSignals = async (runId = selectedRun, nextTab = tab) => {
    if (!runId) return setSignals([]);
    setSignals(await api.webDiscoverySignals(runId, nextTab));
  };
  useEffect(() => {
    loadRuns().catch((e) => setErr(e.message));
  }, []);
  useEffect(() => {
    loadSignals().catch((e) => setErr(e.message));
  }, [selectedRun, tab]);
  useEffect(() => {
    if (!runs.some((r) => r.status === "pending" || r.status === "running"))
      return;
    const timer = window.setInterval(async () => {
      await loadRuns();
      await loadSignals();
    }, 3500);
    return () => window.clearInterval(timer);
  }, [runs, selectedRun, tab]);

  const runDiscovery = async () => {
    setErr("");
    setToast("");
    setRunning(true);
    try {
      const run = await api.createWebDiscoveryRun({
        trigger_type: "all",
        max_results: maxResults || settings?.default_max_results || 40,
        time_range: settings?.default_time_range || "week",
      });
      setSelectedRun(run.id);
      setToast("Discovery run queued across all DecoverAI trigger categories.");
      await loadRuns();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setRunning(false);
    }
  };
  const convert = async (signal: DiscoveredSignal) => {
    try {
      await api.convertDiscoveredSignal(signal.id);
      setToast("Converted to opportunity with source evidence.");
      await Promise.all([loadRuns(), loadSignals()]);
    } catch (e: any) {
      setErr(e.message);
    }
  };
  const reject = async (signal: DiscoveredSignal) => {
    await api.discoveredSignalStatus(
      signal.id,
      "rejected",
      "Rejected in Discovery Runs review.",
    );
    await loadSignals();
  };

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Discovery Runs</h1>
          <p>
            Find and review fresh litigation signals before they enter the sales
            queue.
          </p>
        </div>
      </header>
      <div className="warning">
        Public sources only. Robots, paywalls, logins, CAPTCHAs, and access
        controls are respected.
      </div>
      {err && <div className="error">{err}</div>}
      {toast && <div className="okBanner">{toast}</div>}
      <section className="filters discoveryStart">
        <div>
          <h3>Find litigation triggers</h3>
          <p>
            Runs a US-focused search across court/docket and trusted legal-news
            sources. Failed, stale, unknown-date, and low-confidence results
            stay in review.
          </p>
        </div>
        <label className="field compact">
          <span>Max results</span>
          <input
            type="number"
            min={1}
            max={100}
            value={maxResults}
            onChange={(e) => setMaxResults(Number(e.target.value))}
          />
        </label>
        <button onClick={runDiscovery} disabled={running}>
          <RefreshCw size={16} />
          {running ? "Starting..." : "Run Discovery"}
        </button>
      </section>
      {latestRun && (
        <section className="runSummary">
          <button
            className={selectedRun === latestRun.id ? "active" : ""}
            onClick={() => setSelectedRun(latestRun.id)}
          >
            Latest run
          </button>
          <span>{date(latestRun.created_at)}</span>
          <Pill value={latestRun.status} />
          <span>
            Scope: <b>All</b>
          </span>
          <span>
            Raw results: <b>{latestRun.total_results}</b>
          </span>
          <span>
            Converted: <b>{latestRun.converted_count}</b>
          </span>
          {latestRun.error_message && (
            <span className="runError">Error: {latestRun.error_message}</span>
          )}
        </section>
      )}
      <section>
        <h3>Raw Signals</h3>
        <nav className="tabs slim">
          {[
            "all",
            "needs_review",
            "passed_gate",
            "failed_gate",
            "duplicates",
            "rejected",
            "converted",
          ].map((t) => (
            <button
              key={t}
              className={tab === t ? "active" : ""}
              onClick={() => setTab(t)}
            >
              {label(t)}
            </button>
          ))}
        </nav>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Score</th>
                <th>Gate</th>
                <th>Matter</th>
                <th>Parties</th>
                <th>Source</th>
                <th>Freshness</th>
                <th>Trigger</th>
                <th>Discovery Pain</th>
                <th>DecoverAI Fit</th>
                <th>Failure Reason</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Score n={s.final_trigger_score} />
                  </td>
                  <td>
                    {s.gate_passed ? (
                      <Pill value="passed" />
                    ) : (
                      <Pill value="failed" />
                    )}
                  </td>
                  <td>
                    <b>{s.title}</b>
                  </td>
                  <td>{s.parties?.join(", ") || "-"}</td>
                  <td>
                    <SourceLink
                      url={s.source_url}
                      label={`${label(s.source_tier || "")} · ${s.source_domain}`}
                    />
                  </td>
                  <td>
                    <Pill value={s.freshness_status} />
                    <small>
                      {s.signal_age_days != null
                        ? `${s.signal_age_days}d`
                        : s.freshness_reason}
                    </small>
                  </td>
                  <td>{label(s.trigger_category || s.trigger_type)}</td>
                  <td>{Math.round(s.discovery_pain_score || 0)}</td>
                  <td>{Math.round(s.dcover_fit_score || 0)}</td>
                  <td>
                    {(s.gate_failure_reasons || []).join(", ") ||
                      s.rejection_reason ||
                      s.duplicate_reason ||
                      s.gate_reason ||
                      "-"}
                  </td>
                  <td className="rowActions">
                    <button title="View" onClick={() => setSelectedSignal(s)}>
                      <Eye size={15} />
                    </button>
                    <button
                      title="Convert"
                      disabled={!s.gate_passed || s.status === "converted"}
                      onClick={() => convert(s)}
                    >
                      <CheckCircle size={15} />
                    </button>
                    <button title="Reject" onClick={() => reject(s)}>
                      <Ban size={15} />
                    </button>
                  </td>
                </tr>
              ))}
              {signals.length === 0 && (
                <tr>
                  <td colSpan={11} className="empty">
                    No raw signals in this tab.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      {selectedSignal && (
        <SignalDrawer
          signal={selectedSignal}
          onClose={() => {
            setSelectedSignal(null);
            loadSignals();
          }}
        />
      )}
    </div>
  );
}

function Opportunities() {
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

function Settings() {
  const [cfg, setCfg] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState("");
  const [llm, setLlm] = useState<LLMStatus | null>(null);
  const load = async () => {
    setLoading(true);
    setErr("");
    try {
      setCfg(await api.settings());
      setLlm(await api.llmStatus(false));
    } catch (e: any) {
      setErr(e.message || "Settings could not be loaded.");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, []);
  if (loading) return <div className="page">Loading settings...</div>;
  if (err || !cfg)
    return (
      <div className="page">
        <div className="error">Settings could not be loaded.</div>
        <button onClick={load}>Retry</button>
      </div>
    );
  const keys = [
    "final_trigger_score_min",
    "confidence_score_min",
    "source_quality_score_min",
    "discovery_pain_score_min",
    "dcover_fit_score_min",
    "max_daily_triggers",
  ] as const;
  return (
    <div className="page narrow">
      <header className="top">
        <div>
          <h1>Settings</h1>
          <p>
            Control trigger freshness, source packs, trusted domains, blocked
            domains, and quality thresholds.
          </p>
        </div>
      </header>
      <Card title="Daily Trigger Gate">
        {keys.map((k) => (
          <label className="field" key={k}>
            <span>{label(k)}</span>
            <input
              type="number"
              value={cfg[k] as number}
              onChange={(e) => setCfg({ ...cfg, [k]: Number(e.target.value) })}
            />
          </label>
        ))}
        <label className="field">
          <span>Max Signal Age Days</span>
          <input
            type="number"
            value={cfg.max_signal_age_days}
            onChange={(e) =>
              setCfg({ ...cfg, max_signal_age_days: Number(e.target.value) })
            }
          />
        </label>
        <label className="field checkbox">
          <input
            type="checkbox"
            checked={cfg.allow_unknown_signal_date}
            onChange={(e) =>
              setCfg({ ...cfg, allow_unknown_signal_date: e.target.checked })
            }
          />
          <span>Allow Unknown Signal Date</span>
        </label>
        <button
          onClick={async () => {
            setCfg(await api.updateSettings(cfg));
            setSaved("Saved settings");
          }}
        >
          Save
        </button>
        {saved && <p className="ok">{saved}</p>}
      </Card>
      <Card title="Ranking Diversity">
        <label className="field">
          <span>Max Per Source Domain</span>
          <input
            type="number"
            value={cfg.max_per_source_domain}
            onChange={(e) =>
              setCfg({ ...cfg, max_per_source_domain: Number(e.target.value) })
            }
          />
        </label>
        <label className="field">
          <span>Max Per Trigger Category</span>
          <input
            type="number"
            value={cfg.max_per_trigger_category}
            onChange={(e) =>
              setCfg({
                ...cfg,
                max_per_trigger_category: Number(e.target.value),
              })
            }
          />
        </label>
        <label className="field">
          <span>Max Per Same Party</span>
          <input
            type="number"
            value={cfg.max_per_same_party}
            onChange={(e) =>
              setCfg({ ...cfg, max_per_same_party: Number(e.target.value) })
            }
          />
        </label>
      </Card>
      <Card title="Source Quality">
        <label className="field wide">
          <span>Trusted domains</span>
          <textarea
            value={cfg.trusted_domains || ""}
            onChange={(e) =>
              setCfg({ ...cfg, trusted_domains: e.target.value })
            }
          />
        </label>
        <label className="field wide">
          <span>Blocked domains</span>
          <textarea
            value={cfg.blocked_domains || ""}
            onChange={(e) =>
              setCfg({ ...cfg, blocked_domains: e.target.value })
            }
          />
        </label>
      </Card>
      <Card title="Source Packs">
        {cfg.source_packs.map((pack, i) => (
          <label className="field checkbox" key={pack.key || i}>
            <input
              type="checkbox"
              checked={!!pack.enabled}
              onChange={(e) => {
                const next = [...cfg.source_packs];
                next[i] = { ...pack, enabled: e.target.checked };
                setCfg({ ...cfg, source_packs: next });
              }}
            />
            <span>{pack.label || label(pack.key)}</span>
          </label>
        ))}
      </Card>
      <Card title="Discovery Defaults">
        <label className="field">
          <span>Time range</span>
          <select
            value={cfg.default_time_range}
            onChange={(e) =>
              setCfg({ ...cfg, default_time_range: e.target.value })
            }
          >
            {["day", "week", "month", "year"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Max results</span>
          <input
            type="number"
            value={cfg.default_max_results}
            onChange={(e) =>
              setCfg({ ...cfg, default_max_results: Number(e.target.value) })
            }
          />
        </label>
        <button
          onClick={async () => {
            setCfg(await api.updateSettings(cfg));
            setSaved("Saved settings");
          }}
        >
          Save
        </button>
      </Card>
      <Card title="Demo Mode">
        <p>
          ENABLE_DEMO_DATA is <b>{String(cfg.enable_demo_data)}</b>. Configure
          keys in `backend/.env`: `TAVILY_API_KEY`, `FIRECRAWL_API_KEY`,
          `OPENAI_API_KEY`.
        </p>
      </Card>
      <Card title="Gemini Judge">
        <p>
          Gemini is used as the final pursue / do-not-pursue judge when
          `GEMINI_API_KEY` is configured.
        </p>
        <p>
          <b>Status:</b>{" "}
          {llm
            ? `${llm.configured ? "Configured" : "Not configured"} · ${llm.message}`
            : "Unknown"}
        </p>
        <button onClick={async () => setLlm(await api.llmStatus(true))}>
          Check Gemini Response
        </button>
      </Card>
    </div>
  );
}

function SignalTable({
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
                  {s.signal_age_days != null ? `${s.signal_age_days}d` : "-"}
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

function SignalDrawer({
  signal,
  onClose,
}: {
  signal: DiscoveredSignal;
  onClose: () => void;
}) {
  const [tab, setTab] = useState("brief");
  const [full, setFull] = useState<DiscoveredSignal>(signal);
  const [notes, setNotes] = useState("");
  useEffect(() => {
    api
      .discoveredSignal(signal.id)
      .then(setFull)
      .catch(() => setFull(signal));
  }, [signal.id]);
  const updateStatus = async (
    status: "qualified" | "contacted" | "rejected" | "needs_more_research",
  ) => {
    await api.discoveredSignalStatus(
      signal.id,
      status,
      status === "rejected" ? "Rejected from Daily Triggers." : "",
    );
    onClose();
  };
  const review = async (
    review_status: "useful" | "not_useful" | "needs_research",
    reason: string,
  ) => {
    await api.salesReview(signal.id, review_status, reason);
    setFull(await api.discoveredSignal(signal.id));
  };
  const plan = full.sales_action_plan || {};
  return (
    <div className="drawer">
      <div className="drawerCard">
        <div className="drawerHead">
          <div>
            <h2>{full.title}</h2>
            <p>
              {full.matter_type || full.case_type} · final score{" "}
              {Math.round(full.final_trigger_score)}
            </p>
          </div>
          <button className="iconButton" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <div className="actions">
          <button onClick={() => updateStatus("qualified")}>Qualified</button>
          <button onClick={() => updateStatus("contacted")}>Contacted</button>
          <button onClick={() => updateStatus("needs_more_research")}>
            Needs More Research
          </button>
          <button onClick={() => updateStatus("rejected")}>Rejected</button>
        </div>
        <nav className="tabs">
          {["brief", "evidence", "sales playbook", "scores", "review"].map(
            (t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ),
          )}
        </nav>
        {tab === "brief" && (
          <section>
            <Block title="Summary" text={full.summary} />
            <Block title="Why now" text={full.why_now} />
            <Block title="Discovery pain" text={full.discovery_pain_summary} />
            <Block
              title="Why DecoverAI"
              text={full.why_decoverai || full.why_relevant_to_decoverAI}
            />
            <Card title="Matter Facts">
              <p>
                <b>Parties:</b> {full.parties?.join(", ") || "-"}
              </p>
              <p>
                <b>Law firms:</b> {full.law_firms?.join(", ") || "-"}
              </p>
              <p>
                <b>Court/regulator:</b>{" "}
                {full.court_or_regulator ||
                  full.courts?.join(", ") ||
                  full.regulators?.join(", ") ||
                  "-"}
              </p>
            </Card>
          </section>
        )}
        {tab === "evidence" && (
          <section>
            <Card title="Source Evidence">
              <p>
                <SourceLink url={full.source_url} label={full.source_url} />
              </p>
              <p>
                <b>Publisher/domain:</b> {full.publisher || full.source_domain}
              </p>
              <p>
                <b>Source tier:</b> {label(full.source_tier)} ·{" "}
                {full.source_reason}
              </p>
              <p>
                <b>Signal date:</b>{" "}
                {date(full.signal_date || full.published_at)} ·{" "}
                {label(full.freshness_status)}{" "}
                {full.signal_age_days != null
                  ? `(${full.signal_age_days} days)`
                  : ""}
              </p>
              <p>
                <b>Source quality:</b> {Math.round(full.source_quality_score)}
              </p>
              <p>{full.raw_snippet}</p>
              <pre>
                {full.scraped_text ||
                  full.scraped_text_preview ||
                  "No scraped text stored."}
              </pre>
            </Card>
          </section>
        )}
        {tab === "sales playbook" && (
          <section>
            <Card title="Who to target">
              <p>
                <b>{plan.recommended_account || full.parties?.[0] || "-"}</b>
              </p>
              <p>
                {plan.recommended_contact_titles?.join(", ") ||
                  full.recommended_personas?.join(", ") ||
                  "-"}
              </p>
              <p>{plan.why_this_persona || "-"}</p>
            </Card>
            <Block title="Why now" text={full.why_now} />
            <Block
              title="What pain to lead with"
              text={
                plan.discovery_pain_hypothesis || full.discovery_pain_summary
              }
            />
            <Block
              title="Capability to mention"
              text={
                (plan.proof_points_to_use || []).join(", ") ||
                full.why_decoverai
              }
            />
            <CopyBlock
              title="Suggested first email"
              text={plan.suggested_first_email || full.email_body}
            />
            <CopyBlock
              title="Suggested LinkedIn message"
              text={plan.suggested_linkedin_message || full.linkedin_message}
            />
            <CopyBlock
              title="Call opener"
              text={plan.call_opener || full.call_opener}
            />
            <Card title="Discovery questions">
              {(plan.questions_to_ask_on_call || []).map((q: string) => (
                <p key={q}>{q}</p>
              ))}
            </Card>
            <Card title="Objection handling">
              {(plan.likely_objections || []).map((q: string, i: number) => (
                <p key={q}>
                  <b>{q}</b>
                  <br />
                  {plan.objection_responses?.[i]}
                </p>
              ))}
            </Card>
            <Block title="Next best action" text={plan.next_best_action} />
          </section>
        )}
        {tab === "scores" && (
          <section>
            {!full.is_litigation_trigger && (
              <div className="error">
                This does not appear to be an actionable litigation trigger.
              </div>
            )}
            <div className="scoresGrid">
              <Metric
                label="Confidence"
                value={Math.round(full.confidence_score || 0)}
              />
              <Metric
                label="Source"
                value={Math.round(full.source_quality_score || 0)}
              />
              <Metric
                label="Discovery pain"
                value={Math.round(full.discovery_pain_score || 0)}
              />
              <Metric
                label="DecoverAI fit"
                value={Math.round(full.dcover_fit_score || 0)}
              />
              <Metric
                label="Actionability"
                value={Math.round(full.sales_actionability_score || 0)}
              />
              <Metric
                label="Final"
                value={Math.round(full.final_trigger_score || 0)}
              />
            </div>
            <Card title="Gate">
              <p>
                <b>
                  {label(
                    full.gate_status ||
                      (full.gate_passed ? "passed" : "failed"),
                  )}
                </b>
              </p>
              <p>
                {(full.gate_failure_reasons || []).join(", ") ||
                  full.gate_reason}
              </p>
            </Card>
            <Card title="Relevance">
              <p>
                {full.trigger_relevance_reason || full.rejection_reason || "-"}
              </p>
            </Card>
            <Card title="Warnings / Missing Fields">
              <p>{full.extraction_warnings?.join(", ") || "No warnings."}</p>
              <p>{full.missing_fields?.join(", ") || "No missing fields."}</p>
            </Card>
          </section>
        )}
        {tab === "review" && (
          <section>
            <Card title="Sales Usefulness">
              <div className="actions">
                <button onClick={() => review("useful", "good_trigger")}>
                  Useful
                </button>
                <button
                  onClick={() => review("not_useful", "weak_discovery_pain")}
                >
                  Not Useful
                </button>
                <button
                  onClick={() => review("needs_research", "unclear_party")}
                >
                  Needs Research
                </button>
              </div>
              <p>
                <b>Current:</b>{" "}
                {label(full.sales_review_status || "not reviewed")}{" "}
                {full.sales_review_reason
                  ? `· ${label(full.sales_review_reason)}`
                  : ""}
              </p>
            </Card>
            <Card title="Internal Notes">
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Notes stay local in this review panel for now."
              />
            </Card>
          </section>
        )}
      </div>
    </div>
  );
}

function OpportunityDrawer({
  opp,
  onClose,
}: {
  opp: Opportunity;
  onClose: () => void;
}) {
  return (
    <div className="drawer">
      <div className="drawerCard">
        <div className="drawerHead">
          <div>
            <h2>{opp.case_name}</h2>
            <p>
              {opp.matter_type || opp.case_type} · {opp.status}
            </p>
          </div>
          <button className="iconButton" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <Block
          title="Sales angle"
          text={opp.sales_angle_one_liner || opp.pitch_angle}
        />
        <Block title="Why DecoverAI" text={opp.why_decoverai} />
        <Block title="Email" text={opp.email_body || opp.generated_email} />
        <Card title="Evidence">
          {opp.evidence?.map((e) => (
            <p key={e.id}>
              <SourceLink
                url={e.source_url}
                label={e.source_title || e.publisher}
              />
            </p>
          ))}
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
function Score({ n }: { n: number }) {
  return (
    <span className={n >= 85 ? "score hot" : n >= 75 ? "score warm" : "score"}>
      {Math.round(n || 0)}
    </span>
  );
}
function Pill({ value }: { value: string }) {
  return <span className={`pill ${value}`}>{label(value)}</span>;
}
function Card({ title, children }: { title: string; children: any }) {
  return (
    <div className="card">
      <h4>{title}</h4>
      {children}
    </div>
  );
}
function Block({ title, text }: { title: string; text?: string }) {
  return (
    <div className="summaryBlock">
      <h3>{title}</h3>
      <p>{text || "-"}</p>
    </div>
  );
}
function CopyBlock({ title, text }: { title: string; text?: string }) {
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
function SourceLink({ url, label }: { url?: string; label?: string }) {
  if (!url) return <>-</>;
  return (
    <a className="sourceLink" href={url} target="_blank">
      <span>{label || url}</span>
      <ExternalLink size={14} />
    </a>
  );
}
function label(v: string) {
  return (v || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}
function date(v?: string) {
  return v ? new Date(v).toLocaleDateString() : "-";
}

createRoot(document.getElementById("root")!).render(<App />);

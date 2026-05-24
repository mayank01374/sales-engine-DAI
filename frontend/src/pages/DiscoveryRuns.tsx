import { useCallback, useEffect, useRef, useState } from "react";
import { Ban, CheckCircle, Eye, RefreshCw } from "lucide-react";
import { api } from "../api";
import type { AppSettings, DiscoveredSignal, WebDiscoveryRun } from "../types";
import { SignalDrawer } from "../components/SignalDrawer";
import { Pill, Score, SourceLink, date, label } from "../components/ui";
export function DiscoveryRuns() {
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
  const selectedRunRef = useRef<number | null>(null);
  const tabRef = useRef(tab);
  const initializedSettingsRef = useRef(false);
  const latestRun = runs[0];
  const isPolling = runs.some((r) => r.status === "pending" || r.status === "running");

  useEffect(() => {
    selectedRunRef.current = selectedRun;
  }, [selectedRun]);
  useEffect(() => {
    tabRef.current = tab;
  }, [tab]);

  const loadRuns = useCallback(async () => {
    const cfg = await api.settings();
    if (!initializedSettingsRef.current) {
      setMaxResults(cfg.default_max_results || 40);
      initializedSettingsRef.current = true;
    }
    setSettings(cfg);
    const data = await api.webDiscoveryRuns();
    setRuns(data);
    if (!selectedRunRef.current && data[0]) setSelectedRun(data[0].id);
  }, []);
  const loadSignals = useCallback(async (runId = selectedRunRef.current, nextTab = tabRef.current) => {
    if (!runId) return setSignals([]);
    setSignals(await api.webDiscoverySignals(runId, nextTab));
  }, []);
  useEffect(() => {
    loadRuns().catch((e) => setErr(e.message));
  }, [loadRuns]);
  useEffect(() => {
    loadSignals(selectedRun, tab).catch((e) => setErr(e.message));
  }, [loadSignals, selectedRun, tab]);
  useEffect(() => {
    if (!isPolling) return;
    const timer = window.setInterval(async () => {
      await loadRuns();
      await loadSignals();
    }, 3500);
    return () => window.clearInterval(timer);
  }, [isPolling, loadRuns, loadSignals]);

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
                      {date(s.signal_date || s.published_at)}
                      {s.signal_age_days != null ? ` · ${s.signal_age_days}d` : ""}
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

import { useEffect, useState } from "react";
import { api } from "../api";
import type { AppSettings, LLMStatus } from "../types";
import { Card, label } from "../components/ui";
export function Settings() {
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

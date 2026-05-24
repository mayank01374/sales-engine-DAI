import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "../api";
import type { DiscoveredSignal } from "../types";
import { Block, Card, CopyBlock, Metric, SourceLink, date, label } from "./ui";
export function SignalDrawer({
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

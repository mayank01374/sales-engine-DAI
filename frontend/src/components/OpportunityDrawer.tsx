import { X } from "lucide-react";
import type { Opportunity } from "../types";
import { Block, Card, SourceLink } from "./ui";
export function OpportunityDrawer({
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

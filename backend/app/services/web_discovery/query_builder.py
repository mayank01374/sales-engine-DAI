from __future__ import annotations

TRIGGER_QUERIES = {
    "data_breach": ["data breach class action complaint filed company", "data breach lawsuit filed company", "cyber incident litigation complaint company", "privacy class action complaint data breach", "breach notification lawsuit company", "data breach lawsuit", "privacy lawsuit", "cybersecurity class action", "breach class action"],
    "securities": ["securities class action complaint filed public company", "shareholder lawsuit filed securities fraud", "investor lawsuit filed public company", "securities fraud complaint filed company", "securities lawsuit", "shareholder class action", "investor lawsuit", "class action filed"],
    "antitrust": ["antitrust lawsuit filed company", "DOJ sues company antitrust", "FTC sues company antitrust", "monopoly lawsuit filed company", "price fixing litigation company", "antitrust lawsuit", "FTC investigation", "DOJ antitrust investigation", "competition lawsuit"],
    "trade_secret": ["trade secret lawsuit filed company", "misappropriation complaint competitor lawsuit", "source code trade secret litigation", "employee trade secret lawsuit filed", "trade secret lawsuit", "misappropriation lawsuit", "source code lawsuit", "confidential information lawsuit"],
    "patent_ip": ["patent infringement lawsuit filed", "copyright lawsuit filed company", "IP misappropriation complaint competitor lawsuit", "patent litigation complaint company", "patent lawsuit", "IP lawsuit", "copyright lawsuit", "infringement complaint"],
    "regulatory_investigation": ["DOJ investigation company subpoena documents", "FTC investigation company consent order", "SEC charges company securities fraud complaint", "regulator probes company subpoena investigation", "subpoena issued to company investigation", "FTC investigation", "SEC investigation", "DOJ investigation", "regulatory action"],
    "healthcare_fraud_white_collar": ["DOJ charges healthcare fraud company", "False Claims Act settlement healthcare company", "anti-kickback investigation healthcare company", "whistleblower lawsuit healthcare fraud", "government subpoena healthcare company", "healthcare fraud lawsuit", "False Claims Act lawsuit", "DOJ healthcare investigation", "whistleblower lawsuit"],
    "commercial_litigation": ["breach of contract lawsuit filed company", "commercial dispute lawsuit filed company", "enterprise litigation filed supplier dispute", "supplier dispute lawsuit company", "commercial lawsuit", "contract dispute", "business litigation", "lawsuit filed"],
    "construction_defect": ["construction defect lawsuit filed", "multi-party construction litigation filed", "defect claims filed construction", "construction arbitration dispute lawsuit", "construction lawsuit", "defect lawsuit", "construction litigation", "construction dispute"],
    "employment_class_action": ["employment class action filed company", "wage hour class action lawsuit filed", "discrimination class action complaint company", "employment class action", "wage lawsuit", "discrimination lawsuit", "class action filed"],
    "ma_dispute": ["M&A dispute lawsuit filed company", "merger acquisition litigation complaint", "earnout dispute lawsuit filed", "M&A lawsuit", "merger lawsuit", "acquisition dispute", "earnout lawsuit"],
    "contract_dispute": ["breach of contract lawsuit filed company", "commercial dispute lawsuit filed", "supplier dispute lawsuit company", "breach of contract", "contract lawsuit", "supplier lawsuit", "contract dispute"],
    "mass_tort": ["mass tort lawsuit filed company", "product liability multidistrict litigation complaint", "consumer mass tort litigation filed", "mass tort lawsuit", "product liability lawsuit", "MDL complaint", "class action filed"],
}

def _pack_matches_trigger(pack: dict, trigger: str) -> bool:
    categories = [str(item).strip().lower() for item in pack.get("trigger_categories") or []]
    return trigger in {"", "all", "all_triggers", "daily"} or "all" in categories or trigger in categories

def _site_query(domain: str, template: str) -> str:
    template = " ".join(str(template or "").split())
    domain = str(domain or "").strip()
    if not domain or template.startswith("site:"):
        return template
    return f"site:{domain} {template}"

def build_discovery_queries(trigger_type: str, geography: str = "US", industry: str = "", source_packs: list[dict] | None = None) -> list[str]:
    trigger = (trigger_type or "").strip().lower()
    queries = []
    if source_packs is not None:
        for pack in source_packs:
            if not pack.get("enabled", True) or not _pack_matches_trigger(pack, trigger):
                continue
            templates = pack.get("query_templates") or []
            included_domains = pack.get("included_domains") or []
            for template in templates:
                if included_domains:
                    queries.extend(_site_query(domain, template) for domain in included_domains)
                else:
                    queries.append(" ".join(str(template).split()))
    if trigger in {"", "all", "all_triggers", "daily"}:
        templates = [template for group in TRIGGER_QUERIES.values() for template in group]
    else:
        templates = TRIGGER_QUERIES.get(trigger, TRIGGER_QUERIES["data_breach"])
    for template in templates:
        queries.append(" ".join(template.split()))
    return list(dict.fromkeys(queries))

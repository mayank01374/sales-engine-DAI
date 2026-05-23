from __future__ import annotations

DEFAULT_SOURCE_PACKS = [
    {
        "key": "us_court_dockets",
        "label": "US court dockets",
        "enabled": True,
        "source_tier": "tier_1_court_docket",
        "included_domains": ["courtlistener.com", "recap.email", "pacer.uscourts.gov", "dockets.justia.com"],
        "excluded_domains": [],
        "trigger_categories": ["all"],
        "query_templates": [
            "site:courtlistener.com complaint filed lawsuit",
            "site:courtlistener.com \"class action\" \"complaint\"",
        ],
    },
    {
        "key": "us_legal_news",
        "label": "US legal news",
        "enabled": True,
        "source_tier": "tier_2_legal_news",
        "included_domains": ["reuters.com/legal", "law.com", "law360.com", "bloomberglaw.com", "jdsupra.com", "natlawreview.com"],
        "excluded_domains": [],
        "trigger_categories": ["all"],
        "query_templates": ["lawsuit filed complaint company legal news", "class action complaint filed legal news"],
    },
    {
        "key": "us_regulators",
        "label": "US regulators",
        "enabled": False,
        "source_tier": "tier_3_regulator",
        "included_domains": ["sec.gov", "justice.gov", "ftc.gov", "hhs.gov", "oig.hhs.gov"],
        "excluded_domains": [],
        "trigger_categories": ["regulatory_investigation", "healthcare_fraud_white_collar", "securities"],
        "query_templates": ["enforcement action complaint charges settlement company subpoena investigation"],
    },
    {
        "key": "law_firm_alerts",
        "label": "Law firm alerts",
        "enabled": True,
        "source_tier": "tier_2_law_firm",
        "included_domains": [],
        "excluded_domains": [],
        "trigger_categories": ["all"],
        "query_templates": ["law firm alert lawsuit filed complaint discovery production"],
    },
    {"key": "india_legal_news", "label": "India legal news", "enabled": False, "source_tier": "tier_2_legal_news", "included_domains": ["barandbench.com", "livelaw.in"], "excluded_domains": [], "trigger_categories": ["all"], "query_templates": ["litigation complaint filed company"]},
    {"key": "healthcare_enforcement", "label": "Healthcare enforcement", "enabled": False, "source_tier": "tier_3_regulator", "included_domains": ["justice.gov", "oig.hhs.gov", "hhs.gov"], "excluded_domains": [], "trigger_categories": ["healthcare_fraud_white_collar"], "query_templates": ["False Claims Act settlement healthcare company subpoena"]},
    {"key": "data_breach_litigation", "label": "Data breach litigation", "enabled": True, "source_tier": "tier_2_legal_news", "included_domains": [], "excluded_domains": [], "trigger_categories": ["data_breach"], "query_templates": ["data breach class action complaint filed company"]},
    {"key": "securities_litigation", "label": "Securities litigation", "enabled": True, "source_tier": "tier_2_legal_news", "included_domains": [], "excluded_domains": [], "trigger_categories": ["securities"], "query_templates": ["securities class action complaint filed public company"]},
    {"key": "patent_ip_litigation", "label": "Patent/IP litigation", "enabled": True, "source_tier": "tier_1_litigation_alert", "included_domains": ["courtlistener.com"], "excluded_domains": [], "trigger_categories": ["patent_ip", "trade_secret"], "query_templates": ["patent infringement complaint filed", "trade secret complaint filed"]},
]

def default_source_packs() -> list[dict]:
    return [dict(pack) for pack in DEFAULT_SOURCE_PACKS]

def enabled_source_packs(packs: list[dict] | None = None) -> list[dict]:
    return [pack for pack in (packs or default_source_packs()) if pack.get("enabled")]

# Product Diagnosis

## Current Broken Flows

- **Daily Triggers is empty** because the quality gate is brittle and there is no actionable empty state explaining failed gate reasons.
- **Discovery Runs fail** with `'< ' not supported between instances of 'float' and 'NoneType'`, caused by score calculations and threshold comparisons that allow `None` to reach numeric comparisons.
- **Raw Signals include irrelevant results**, such as generic SEC policy/guidance content showing under data breach discovery.
- **Settings gets stuck loading** because the frontend depends on the scoring-config endpoint shape and has no resilient error/retry state.
- **Opportunities remains empty** because conversion is only available after a signal passes a gate that can fail for accidental technical reasons.

## Current Backend Errors

- Scores are not normalized consistently across extraction, scoring, gate checks, API responses, and conversion.
- Missing settings/config rows are not exposed through a product-level `/api/settings` contract.
- Discovery relevance is keyword-light and allows generic legal/news pages into the same path as actionable litigation triggers.
- Gate failure reasons are stored as a text string instead of structured reasons a sales user can understand.

## Current Frontend Issues

- The UI still feels like a technical discovery dashboard rather than a sales command center.
- Settings has an infinite loading failure mode.
- Daily Triggers empty state does not tell the user what to do next.
- Discovery Runs does not clearly explain why a signal failed or whether it is actionable.
- Conversion affordance is unclear when no signals pass the gate.

## Current Product Gaps

- The app does not reliably answer: “What are the 10-15 litigation matters DecoverAI should act on today, and why?”
- Relevance filtering does not distinguish litigation triggers from generic policy, guidance, and commentary.
- Source quality and domain policy are too shallow.
- Sales angles can be generic instead of mapping to DecoverAI capabilities.

## Root Causes

- Score normalization was added incrementally and not centralized.
- The quality gate is doing too much with nullable fields.
- Discovery queries are too broad for precision-oriented sales use.
- Settings are coupled to old scoring config instead of a dedicated product settings API.
- Raw discovery and daily trigger workflows are not separated sharply enough.

## Exact Plan

1. Add a central `safe_score(value, default=0)` helper and use it for all scoring and gate comparisons.
2. Add product settings endpoints that always return defaults and can update thresholds/source/query settings.
3. Add litigation relevance classification with positive and negative keyword rules.
4. Store `is_litigation_trigger`, relevance reason, gate status, and structured gate failure reasons.
5. Tighten query templates by trigger category and downrank/reject generic policy/guidance content.
6. Update Daily Triggers to use the structured gate and expose quality summary when empty.
7. Update Discovery Runs to show gate failure reasons clearly and only enable conversion for passed signals.
8. Keep dummy data disabled unless `ENABLE_DEMO_DATA=true`.
9. Add tests for score normalization, relevance, settings, gate behavior, conversion, and demo-data behavior.

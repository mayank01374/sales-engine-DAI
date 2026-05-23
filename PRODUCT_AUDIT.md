# DecoverAI Product Audit

## Current Feature Inventory

- Backend opportunity store with evidence, scoring, statuses, notes, CSV import/export, activity log, enrichment accounts, research tasks, campaigns, and saved views.
- Legacy ingestion routes for CourtListener plus hardcoded legal-source scraping.
- New Web Discovery pipeline with search providers, scraping providers, robots checks, extraction, dedupe, run history, raw discovered signals, and conversion.
- Frontend pages for Signal Workspace, Web Discovery, Campaigns, and Scoring.
- Detail drawers contain overlapping evidence, enrichment, research, activity, generated pitch, and scoring sections.
- Seed startup currently creates scoring config, campaign buckets, saved views, and performs cleanup of old demo/low-quality rows.
- Tests cover core normalization, Web Discovery query building, fallback extraction, dedupe, conversion, robots mocking, and API validation.

## What To Keep

- Web Discovery as the controlled intake pipeline.
- Source evidence tracking.
- Opportunity conversion for high-confidence signals.
- Activity log and notes.
- Explainable scoring, but renamed and narrowed to DecoverAI Trigger Quality.
- Provider-based search/scraping with Tavily, Firecrawl, raw HTTP, optional Playwright, robots checks, and rate limits.
- CSV export/import can remain as an API utility, but should not dominate the UI.

## What To Remove Or Hide From Default UI

- Campaigns as a primary page. Campaigns are generic Clay-like grouping and not required for daily signal precision.
- Saved Views as a primary workflow. The product needs one opinionated default view: high-confidence Daily Triggers.
- Generic enrichment page/tabs. Broad account enrichment distracts from trigger validation and sales actionability.
- Generic AI Research task launcher. The product should ship grounded email, LinkedIn, and call angles directly on each trigger.
- The old “Find” button on the main workspace, because discovery should happen in Discovery Runs with raw signal review.
- Default seeded campaigns/saved views/demo opportunities. Production startup should not create fake sales data.

## What To Merge

- Signal Workspace and converted Web Discovery signals should become `Opportunities`: qualified/converted matters sales is working.
- Scoring settings should merge old weight tuning with quality gate thresholds.
- Evidence tabs should be unified around source evidence, source quality, snippet, and scraped text preview.
- Research output should merge into DecoverAI-specific sales assets on the signal/opportunity: persona, one-line angle, email, LinkedIn, and call opener.

## What To Rename

- “Signal Workspace” -> “Daily Triggers” for the default high-confidence queue.
- “Web Discovery” -> “Discovery Runs” in navigation.
- “Scoring Model” -> “Settings”.
- Generic `score` -> `final_trigger_score`.
- Generic `decoverAI_fit_score` / `decover_fit_score` -> `dcover_fit_score` in the DecoverAI trigger quality model, while keeping compatibility fields where needed.

## Blocking Sales Usefulness

- Too many primary pages make the product feel like a generic Clay clone.
- Main view shows opportunities broadly instead of the top 10-15 daily triggers.
- Generic enrichment/research tasks add work instead of giving a ready sales angle.
- Low-confidence and raw discovery items can sit beside actionable items.
- Old scoring is weighted around broad opportunity quality, not DecoverAI discovery pain and actionability.
- Demo/fallback examples use `example.com`, which is useful for tests but should not appear in production runtime unless explicitly enabled.
- List APIs return too much raw scraped content for normal table views.

## Final Target Workflow

1. Sales user opens **Daily Triggers**.
2. The page shows only top high-confidence triggers that pass the DecoverAI quality gate.
3. The user scans parties, matter type, source, confidence, discovery pain, DecoverAI fit, persona, and one-line sales angle.
4. The user opens the detail drawer for source evidence, why now, discovery pain, DecoverAI fit, buyer personas, and ready outreach.
5. The user marks the trigger Qualified, Contacted, Rejected, or Needs More Research.
6. Raw, rejected, duplicate, and low-confidence items stay in **Discovery Runs**, not the main queue.
7. Passing raw signals can be converted into **Opportunities** with source evidence and score breakdown preserved.
8. **Settings** controls quality thresholds, source allow/block lists, query settings, and documents API-key configuration.

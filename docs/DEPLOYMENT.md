# Deployment and operation

## Already provisioned

- GitHub: `kedmahamelberg-ai/european-information-integrity-monitor`
- Dedicated Supabase project: `european-information-integrity-monitor`, reference `jnzibjjejmfochertwco`, Frankfurt (`eu-central-1`). Creation quote: $0/month.
- Research schema: `eiim`; no browser/anonymous access. Five narrowly scoped `public.eiim_*` RPCs grant execution only to `service_role`. The pre-existing Observatory project is separate.
- Public hosting: GitHub Pages via `.github/workflows/site.yml`.

The frontend requires no Supabase key. It consumes a de-identified export embedded in the Pages deployment.

## Connect real collection

1. In the new repository, open **Settings → Secrets and variables → Actions**.
2. Add repository secrets `SUPABASE_URL` (the new project's URL), `SUPABASE_SECRET_KEY` (new project's server-side secret), `YOUTUBE_API_KEY` (YouTube Data API v3 enabled), and `OPENAI_API_KEY`. Do not paste keys into issues, code, browser console, or README. Do not reuse another project's key accidentally.
3. Review `config/models.json` pricing and weekly ceiling, YouTube quota and comment settings in `config/sampling.json`, and retention policy. The default search costs approximately 5,200 quota units plus metadata/comments, under the 9,000 configured ceiling.
4. Add repository variable `EIIM_ENABLE_LIVE=true` when collection is ready. This enables collection, not publication of unvalidated findings.
5. Run **Actions → Sunday research collection → Run workflow**. Inspect the job summary. Missing keys yield `not_configured` without fake data or paid calls. Quota/budget exhaustion yields `pending_budget`; source data remain checkpointed.
6. Complete the human-review protocol. Re-run the same week to evaluate the publication gate. The public site receives only published snapshots.

Scheduled collection is Sunday 05:17 UTC: safely after Amsterdam midnight in both CET and CEST. A daily 04:43 UTC retention job purges expired raw material and redeploys current permitted output. GitHub may delay scheduled jobs; window calculation does not depend on exact cron execution time.

## Local collection

The CLI reads environment variables directly. A `.env` file is not auto-loaded. Use your shell's secret manager or export values without placing them in tracked files.

```bash
pip install -e '.[live]'
python -m eiim.cli preflight
python -m eiim.cli run
# Reproduce a particular completed observation window:
python -m eiim.cli run --at 2026-10-11T07:00:00+02:00
```

Only the recorded batch configuration can resume an existing batch. To correct classifications, bump the relevant model/prompt/taxonomy versions and run `python -m eiim.cli run --at 2026-10-11T07:00:00+02:00 --revision correction-1`. This clones the retained source/sample/comment frame into a new correction batch, reruns classification and analytics, and requires validation for the new classifier version. Original snapshots remain unchanged. A published correction supersedes its original in the public export; both remain private research records. Budget accounting includes all corrections for the same observation week. The CLI refuses changed configurations against the original batch ID.

## Database portability and security

Apply `sql/001_eiim_schema.sql` and subsequent `sql/` migrations in order, followed by `supabase/migrations/` in timestamp order in a fresh Supabase project. Tables are separated by research entity, with relational batch/video identifiers, indexed foreign keys, typed generated measurement columns and versioned JSON payloads. JSON stores evolving observation details without duplicating large source texts. Embeddings are stored as private vector arrays with model metadata; comparisons run locally. pgvector is unnecessary at this beta's bounded scale and can be added later without changing IDs.

The bulk writer validates and inserts each table as a set in one atomic stage transaction. Its bounded 45-second timeout accommodates JSON conversion for full discovery requests on the free database; ordinary reads keep their default timeout. `tests/sql/bulk_stage_writes.sql` exercises idempotency, conflict rollback, and permissions with 6,000 rows, then rolls back all test data.

Service-only security-definer wrappers have fixed empty search paths, explicit schema references, a table allowlist and revoked public execution. The schema does not need to be added to Supabase's exposed schemas. RLS is enabled without public policies by design (deny-all); Supabase's informational “RLS enabled, no policy” notice is expected.

Never run two live local collectors simultaneously. GitHub collection and retention share a concurrency group. Database stage transactions lock the weekly batch, but external paid calls use a single-run ledger and should not run concurrently from independent machines.

## Failure recovery

Discovery requests and successful model responses are cached in Supabase. Sample membership is immutable after sampling. Individual video comment/classification checkpoints precede stage completion. Rerun the same week after a transient failure; no need to delete records. Malformed outputs are recorded as errors and not accepted as absent framing. Permanent source removal may make a partial batch impossible to complete; record a correction/retraction rather than publishing a misleading subset.

Raw source-bearing tables expire after 30 days by default. After expiry, batch headers and tombstones remain, but full historical reprocessing is no longer possible. Do not advertise permanent raw archival storage without an authorized retention basis. Failed retention or publication jobs need prompt attention because public copies must also be updated.

Collection progress is exported as aggregate counts through the service-only `eiim_progress` RPC. Before validated findings are available, the map shows candidate coverage with neutral markers. Counts are dated deployment snapshots, not a continuously updating feed. No candidate titles, source identifiers or scores are exposed through this status export.

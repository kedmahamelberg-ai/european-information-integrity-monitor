# Activate automatic caption retrieval

1. Create an account at https://dash.supadata.ai/ and start with the free plan. This connection is prepared but is inactive until a key is supplied.
2. Copy your API key into GitHub → european-information-integrity-monitor → Settings → Secrets and variables → Actions → New repository secret. Name it `SUPADATA_API_KEY`. Do not paste the key into chat or commit it.
3. Leave the Actions variable `EIIM_CAPTION_MONTHLY_REQUEST_LIMIT` at its default of 100 for the initial trial. Keep Auto Recharge off at the provider. No paid account action is performed by the repository.
4. Run **Transcript-based conflict classification** from the Actions tab, selecting the retained batch `2026-W40`. This reuses existing videos and comments; it does not discover a new sample.
5. The job saves retrieved English captions, runs the existing calibrated AI classifier, and triggers the public website rebuild. Human confirmation is not required. The private review sample remains 30 for initial calibration, then 3% per batch with a minimum of five.

The native endpoint costs one provider credit per request, including some unavailable-transcript responses. The free plan's 100 monthly requests do not cover 305 pending videos or ongoing weekly collection. The provider currently advertises 3,000 monthly credits for $17/month; this requires a separate purchase decision and a corresponding repository limit increase. Check current prices: https://supadata.ai/pricing.

Only successfully returned English transcript segments are accepted. The provider may return another language even when English was requested; those responses are rejected, not mislabeled. This connection does not call audio transcription or provider translation services. No promise is made that all 305 videos have retrievable English captions.

Provider attempts are reserved before sending a request and are not charged twice by repository retries in the same calendar month. A timeout may still have been billed externally. The shared `eiim-research` workflow concurrency is required to serialize monthly accounting. Existing AI token spending remains subject to the separate $5 batch ledger.

Reports show full-sample coverage alongside eligible-video classification. `awaiting_transcripts` means the acquisition pipeline is incomplete; it does not mean the reviewer must classify those videos manually.

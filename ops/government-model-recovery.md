# Government model-output recovery

The 29 October 2026 afternoon run (40887147761) discovered 38 new links and
restored a queue of 196 items. It stopped on Bosnia and Herzegovina item
`0fb04d970565de9e890d`, while translating a 11,996-character chunk. Five identical
requests returned unparseable JSON; the final parse error was at character 13,866.
The old log did not record response completion status, so it cannot establish
whether the malformed output was truncated. The uncaught RuntimeError stopped
dashboard publication. The workflow successfully saved its checkpoint.

Translations now use at most 6,000 source characters per initial request, an
explicit output budget, and completion/refusal checks before parsing. Malformed
or token-limited translations split into smaller pieces with a bounded depth.
Source text is not truncated. Refusals and content-filter failures are deferred,
not retried through smaller pieces. Completed pieces are cached in the private
item checkpoint under a hash of the source chunk, model and translation version.
An item-level model failure remains pending and is reported in Actions and the
source diagnostic artifact while other items continue. A rate/quota limit stops
further model calls for the run. Authentication/request configuration errors
still fail visibly. Translation checkpoints are excluded from public JSON,
including the dashboard builder's fallback path.

The same run's Czech source warning came from a dated archive entry in the
official `/cz/urad-vlady/akce/` section. This verified section is accepted alongside
`/cz/media-centrum/aktualne/`; other hosts/paths remain rejected. Transient network
failures such as Azerbaijan's connection reset receive at most three source
fetch attempts; access denials remain visible. Both sources passed a live check
after the fix.

To recover, dispatch `Daily government communications` on the corrected `main`
branch. Do not rerun the old job: it checks out the old commit. The normal cache
restore retains completed classifications and retries pending items. Use the
original cutoff with `daily_phase=retry` to finish that pass incrementally, or
`classify_only=true` to process saved items without revisiting archives. Inspect
`model_failures` and pending counts even when publication succeeds.

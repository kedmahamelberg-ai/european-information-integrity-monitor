# English transcript validation and local model trial

On 25 October 2026, a paired local trial used seven previously failed W43 videos
and two previously successful controls. Each source audio was downloaded once;
both multilingual Whisper models used that same audio, CPU int8, two threads,
English translation mode, and the same repaired validation. No source evidence
was sent to Supabase or a paid transcription API during the comparison.

| Previously recorded result | Tested | Small accepted | Medium accepted |
| --- | ---: | ---: | ---: |
| Incomplete transcript | 3 | 3 | 3 |
| Uncertain language | 2 | 0 | 0 |
| No usable speech | 2 | 0 | 0 |
| Successful controls | 2 | 2 | 2 |
| Total | 9 | 5 | 5 |

The recovered examples included Russian (104 seconds), Bulgarian (170 seconds)
and English (472 seconds). Controls included English and Spanish. Medium took
148 seconds on the longer English source, within the existing 900-second worker
limit. Its median runtime on accepted cases was approximately 2.6 times small's.
An uncertain-language 91-minute source remained rejected; language uncertainty
now stops decoding before spending the whole worker budget on ineligible text.

This small, deliberately selected trial demonstrates successful local operation
and no eligibility regression on these cases, not a measured semantic-accuracy
advantage or a population-wide recovery rate. Both models recovered the same
three failed sources after validation repair. At the researcher's request,
`medium` is now the single default audio model. There is no small-to-medium
second pass. Human review remains necessary for automatic translations.

## Required evidence checks

- Full downloaded audio duration must agree with the source duration, allowing
  only metadata/encoding precision (0.75 to 2 seconds depending on duration).
- Translation must run in `translate` mode with English output provenance.
- Detected source-language confidence must remain at least 0.6.
- Every detected speech interval must be covered by accepted timestamped text,
  allowing 250 ms segment timestamp precision. Missing beginnings, middles and
  endings remain ineligible.
- Low-confidence or repetitive speech is unresolved evidence, not silence.
  Silence is ignored only when VAD and Whisper's joint silence/confidence
  evidence agree. Confident words at quiet boundaries are retained.
- Short complete utterances no longer need an arbitrary 20 words. Empty,
  degenerate repetitive, or implausibly sparse output still cannot qualify.
- A decoder error, partial download, uncertain language, rejected speech segment
  or uncovered speech span cannot produce an eligible full transcript.

The evidence includes validation diagnostics and the actual model used.
`transcript_complete=false` still blocks classification and publication. Existing
human corrections and already stored evidence are not rewritten by this change.

## Operational bounds

The 900-second per-worker limit, four-hour recovery session, access cooldowns,
process lock, PID-bound stay-awake guard and five-record import groups remain.
Model files are cached locally. Test audio and cookie copies are removed after
the comparison; complete accepted evidence follows the existing private
30-day retained-batch policy. Install Mac runtime changes only with the recovery
lock free. The local test does not start a collection, classification or database
import job.

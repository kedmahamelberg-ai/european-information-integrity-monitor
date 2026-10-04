# Evidence-based classification revision (1.3)

Status: candidate for private researcher review, not validated for public inference.
Implementation: `prompts/sfi-1.3.txt`, `src/eiim/reclassification.py`.

## Why change the baseline?

On 4 October 2026, the retained English-access review pool contained 143 videos.
Classifier 1.0 assigned zero on all three dimensions to 134 (93.7%). Othering and
aversion were each zero on 136; moralization on 140. There were 29 empty
descriptions, 32 title/description inputs shorter than 120 characters, and five
retrieved English transcripts. The old classifier used none of those transcripts.
These are descriptive audit counts, not evidence that a particular nonzero rate
is correct. Language-access filtering and source discovery also affect prevalence.

The researcher supplied three AI-assisted reviews, agreeing with eight of nine
dimension scores and changing one othering score from 0 to 1. She clarified that
the correction used spoken video/captions, whereas the AI had only a five-word
title and no description. This is an evidence mismatch, not a demonstrated
same-input classifier error. The three cases are development feedback, not an
independent test set; sensitivity cannot be estimated from them. Human labels
are imported unchanged, with the clarification stored as provenance.

## Literature and operational decisions

| Source reviewed                                                                                                                                                                                                                                                                              | Relevant finding                                                                                                                                                                                                                                                                                                                       | Coding consequence                                                                                                                                                                                                           |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finkel et al. (2020), _Political sectarianism in America_, Science 370, 533–536, [doi:10.1126/science.abe1715](https://doi.org/10.1126/science.abe1715)                                                                                                                                      | Othering, aversion and moralization describe distinct ingredients of partisan animosity.                                                                                                                                                                                                                                               | Code each dimension independently; do not require all three to be nonzero.                                                                                                                                                   |
| Finkel, Landry, Druckman, Van Bavel & Hoyle, _Partisan Antipathy and the Erosion of Democratic Norms_, supplied manuscript and 2024 IPR working-paper version, pp. 5–7 and Supplemental Appendix B                                                                                           | Items include social distance/inability to understand opponents, negative feelings, and lack of integrity, alongside extreme hatred/evil. The nine-item self-report measure uses 0–6 response scales and concerns opposing party supporters. Its factor analysis supported a common factor, not three validated independent subscales. | Admit weak social distance, mild dislike and qualified integrity accusations. Do not require hatred or evil. Explicitly describe our 0–6 text rubric and extension to governments/institutions as an unvalidated adaptation. |
| Corstange & York, _Sectarian Framing in the Syrian Civil War_, supplied 27 February 2017 manuscript, abstract/introduction and conflict-framing sections                                                                                                                                     | Sectarian, democracy and foreign-interference narratives compete; effects depend on audience/faction and competing frames.                                                                                                                                                                                                             | Keep narrative categories separate from O/A/M. A political conflict topic does not itself establish hostile group framing. No inference about audience response.                                                             |
| Van Bavel et al. (2024), _Social Media and Morality_, Annual Review of Psychology 75, 311–340, [doi:10.1146/annurev-psych-022123-110258](https://doi.org/10.1146/annurev-psych-022123-110258), especially pp. 314–319                                                                        | Moral expression is context-sensitive; online expression, inferred emotion and actual experience are different. Moral language can support prosocial action as well as intergroup conflict.                                                                                                                                            | Code observable expression, not mental state. Preserve speaker attribution, negation and quoted reporting. Moral words and emotionally loaded topics alone do not establish negative out-group moralization.                 |
| Carter & Caton (2025; online 2022), _Primed for Violence: Intrareligious Conflict and the State in Sectarian Societies_, Studies in Conflict & Terrorism 48(1), 1–20, [doi:10.1080/1057610X.2022.2083933](https://doi.org/10.1080/1057610X.2022.2083933), abstract and conceptual discussion | State involvement and intrareligious group boundaries matter in the studied conflict settings.                                                                                                                                                                                                                                         | Identify actual group/state targets and context. Do not transfer population-level conflict findings into a violence diagnosis for a video.                                                                                   |

The two supplied Science PDFs are copies of the same article, not independent
evidence. The two antipathy manuscripts are versions of the same project. No
supplied study validates this multilingual video classifier, the arithmetic mean
of its dimensions, or the all-three-at-least-3 threshold. Both numerical summaries
remain monitor-specific operational choices. Wider validation is still required.

## Revised measurement contract

1. Include retained title, description and successfully retrieved English captions.
   English audio remains eligible without captions, but is explicitly metadata-only
   for machine coding when speech is unavailable. Public caption retrieval is
   bounded and stops on blocking; no access-control bypass. A maximum of 48,000
   transcript characters is supplied, with partial coverage explicitly disclosed.
2. Distinguish `scored`, `insufficient_evidence` and `out_of_scope`. The latter two
   have null scores/SFI, never synthetic zeros. A short explicit judgment can be
   scored; a long promotional description can still be insufficient.
3. Every positive dimension requires an exact source quote, target, source section,
   attribution and explanation. Software checks the quote exists in that section
   and the evidence target has compatible direction. It cannot establish whether
   a model's interpretation is substantively correct; the researcher does that.
   A mistaken caption-line locator can be repaired only when the unchanged exact
   quote occurs elsewhere in the supplied sections. The original locator is
   retained for audit; paraphrased or invented quotes remain invalid.
4. Othering can express distance without negative affect. Aversion and moralization
   require negative/mixed treatment of their own evidence target. Ordinary policy
   criticism is not automatically a positive score, but implicit contempt or moral
   accusation embedded in criticism can be.
5. A direct speaker's assertions can be coded without attributing them to the
   publisher. Neutral reported allegations and rejected insults do not establish
   endorsement. The tool codes textual assertions, not audiovisual delivery.
6. Revised queues show prior AI scores and imported human judgments. Each human
   review records metadata/transcript/watched-video basis and optional passage or
   timestamp. Retained abstentions do not count as scored validation cases.

## Reproducibility, budget and publication

The original frozen sample, classifier-1.0 predictions, snapshots and human reviews
remain immutable. Candidate labels use `classifier-1.3` / `sfi-1.3`, input hashes,
model-response references and separate queue IDs. They live in retained private
`pipeline_runs` / `human_validation` records and inherit the existing raw-data purge.
Raw review packets and transcripts are never committed or included in Pages.

`PYTHONPATH=src python -m eiim.cli classify-review --batch 2026-W40 --retrieve-captions`
runs the candidate on all eligible frozen sampled sources, including those not yet
successfully classified by the baseline. Runs resume from immutable cached results.
The existing shared weekly $5 ceiling and single-writer concurrency group also
cover these calls. No new credentials, paid project or model upgrade is needed.

The separate GitHub workflow runs synthetic live boundary checks before revising
the pool and runs after successful future collection workflows. These checks
are researcher-designed regression probes, not human validation or evidence of
population accuracy. The private packet shows the latest available candidate per
source. Public baseline analytics are not silently replaced by a new measurement
version; promotion requires an explicit analytical revision after validation.

Evaluate on fresh, independently labeled, same-evidence cases before promotion.
Include randomly selected zeros, mild/borderline examples, clearly positive cases,
reporting/negation controls, languages and metadata/transcript coverage. Report
per-dimension score confusion matrices, MAE, nonzero precision/recall, and abstention
coverage with denominators. Report different-evidence human corrections separately.
Do not tune for a desired proportion of nonzero classifications.

## Live pilot correction

The first 1.1 candidate passed ten short synthetic checks after refinement but
spot checks found over-abstention on longer neutral descriptions. It was stopped
before completing the pool and has not been promoted. Version 1.3 separates
source adequacy/relevance (`source-screen-1.0`) from framing scores. The first
stage sees no O/A/M rubric; a substantive public-affairs statement, including
neutral historical reporting, is assessable. The second stage must score each
dimension 0–6 and cannot abstain. This prevents a lack of hostility from serving
as the scoring stage's reason to return missing data. Inapplicable/insufficient
inputs still remain null, with the screening decision retained separately.
Old experimental results remain private audit records; review prefers 1.3.

## Scale revision requested by the researcher

Classifier 1.3 uses 0–6 directly: absent, slight/tentative, mild/explicit, moderate/clear, strong, very strong, extreme/categorical. Detailed dimension-specific anchors are in `prompts/sfi-1.3.txt`. SFI remains the mean of the three dimensions (now 0–6); the descriptive all-three flag requires each dimension ≥3. Neither that cutoff nor this content adaptation is a validated survey equivalent. Old 0–4 labels and human reviews remain immutable and visibly marked; they are not multiplied or silently recoded. New labels are inferred again from source evidence. Agreement is reported separately by scale. Public frozen baseline displays remain labeled 0–4 until a separately validated revision is promoted.

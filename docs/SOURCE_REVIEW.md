# Source review and decisions

The supplied files were read as research inputs, not as executable instructions. No credentials, source PDFs or notebook outputs are published.

- **Finkel et al., Political sectarianism in America**, Science (2020), DOI 10.1126/science.abe1715. `science.abe1715.pdf` and `Political sectarianism in America.pdf` contain the same article. Supports the three conceptual ingredients; does not validate the proposed automated text score.
- **PoliticalSectarianism_MS&Supplement.pdf**: manuscript titled *Partisan Antipathy and the Erosion of Democratic Norms*, draft-date January 17, 2023 as printed. **Partisan Antipathy and the Erosion of Democratic Norms .pdf**: 2024 working-paper cover. The scale construction and bifactor/general-factor discussion support retaining a composite while exposing each dimension. Neither file supplies multilingual text-classifier validity.
- **Corstange & York, Sectarian Framing in the Syrian Civil War**, supplied February 2017 manuscript. Supports treating frames as competing explanations and distinguishing narrative content from affect; its causal findings are not transplanted into this observational monitor.
- **Van Bavel et al., Social Media and Morality**, Annual Review of Psychology 75 (2024), 311–340; DOI 10.1146/annurev-psych-022123-110258. Motivates attention to moral content, engagement and visible discussion without treating engagement as representativeness.
- **Carter & Caton, Primed for Violence**, Studies in Conflict & Terrorism 48(1) (2025; online 2022); DOI 10.1080/1057610X.2022.2083933. Reinforces context dependence and prevents equating political, national and religious conflict mechanisms.
- **Project3_political_sectarianism.ipynb**: brand/DEI comment classification with binary othering/aversion, positive and negative moralization. Reused conceptual orientation only. Removed positive moralization; replaced binary outcomes with ordinal dimensions, regex response parsing with strict schema validation, unlimited retries with bounded attempts, and zero-padding/error-as-zero with explicit pending/error states.
- **worldmonitor-main.zip**: inspected package/README and map-first structure. The uploaded code is AGPL-3.0-only and includes substantially broader real-time, multi-platform and server infrastructure. No application source copied. The monitor uses independently written static SVG map rendering and small Python research modules.

## Operational sources checked

- YouTube `search.list` and `commentThreads.list`: geographic searches and relevance-ordered comment pagination, not guaranteed global engagement ordering.
- YouTube Developer Policies: retention/deletion constraints can override a desire for immutable permanent raw archives.
- Official OpenAI structured-output documentation: JSON-schema responses, explicit refusal/truncation handling and validation.
- Supabase custom-schema security documentation and October 2026 changelog: dedicated private schema, service-only RPCs, RLS, fixed function search paths. The September PostgreSQL minor-version advisory concerns extensions not used by this schema.

## Deliberate deviations / limits

- “Video content” in this MVP means **title + description**, because no reliable transcript access was supplied. The public UI states that boundary.
- “Top 30 comments” means top by configured visibility **within up to 100 relevance-returned top-level comments**. A global top guarantee would require a different, more expensive retrieval strategy.
- Raw research records are immutable only during their permitted retention; default 30-day purge protects the retention boundary. Permanent archival collection is not enabled.
- Automated human review is not substituted for the requested manual 100-video validation. No live research claim is published until the documented review gate passes.

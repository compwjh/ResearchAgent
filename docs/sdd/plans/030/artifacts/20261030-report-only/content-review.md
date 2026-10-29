# Spec 030 report-only report — content review

Date: 2026-10-30  
Task: `bdcd7fc185425e0f8443599e9cdbe8ec`, report version 2  
Review scope: structured `report_content`, existing matrix, citation manifest, and the five frozen candidate abstracts. This is a single-reviewer, evidence-focused content review, not a multi-seat independent panel, and it does not assess Spec 030 closure.

## Overall result

**Qualified content pass.** The report genuinely exceeds the 1,500 CJK-character threshold: an independent call to the project’s `count_report_content_cjk` function returns **2,428**, matching the stored quality result. The body contains specific per-paper methods and findings, two comparisons, and four supported synthesis findings. Its length is substantive rather than repeated boilerplate, although some claims recur across the comparison and synthesis sections.

The principal factual summaries are faithful to the abstracts, and the report correctly states that its evidence is abstract-level. However, one research-gap statement conflicts with the MIGP abstract’s stated real-world deployment, and three of the five papers are adjacent or tangential to a strict password-login question. Those points should be corrected or qualified before treating the report as a focused review of password authentication.

## Evidence and source fidelity

All five matrix Evidence rows are `available` at `abstract` level. I compared each matrix abstract digest with the corresponding frozen `search_results.snapshot_json` abstract in the primary paper-search database; all five digests match. The citation manifest also labels all five citations as `abstract`. The report’s evidence-scope paragraph accurately discloses the evidence level and does not claim full-text review.

The per-paper summaries are materially faithful to those abstracts:

- **Citation 1 — “Phish in Sheep’s Clothing: Exploring the Authentication Pitfalls of Browser Fingerprinting.”** The report accurately describes fingerprint-vector replication, phishing-site measurements, risk-based authentication bypass, and the growing capability of phishing sites targeting some financial institutions.
- **Citation 2 — “Might I Get Pwned: A Second Generation Compromised Credential Checking Service.”** The report accurately covers credential-tweaking attacks, password-similarity measurement, privacy/security trade-offs, the 94% reduction in the simulated 1,000-guess attack, response time, and the Cloudflare deployment.
- **Citation 3 — “In-Kernel Control-Flow Integrity on Commodity OSes using ARM Pointer Authentication.”** The PAL, kernel CFI, post-validation, OS portability, and reported benchmark overhead are accurately summarized. This paper concerns kernel control-flow integrity and pointer authentication, not user password or login authentication.
- **Citation 4 — “Under the Hood of DANE Mismanagement in SMTP.”** The TLSA/certificate synchronization problem, automatic certificate reissuance, survey of 39 operators, client-compatibility concern, and deployment scale are accurately summarized. This is SMTP transport/server authentication and operational management, not password login.
- **Citation 5 — “Seeing is Living? Rethinking the Security of Facial Liveness Verification in the Deepfake Era.”** The report accurately captures missing or weak anti-deepfake controls, demographic bias, adversarial training, input-quality effects, the up-to-70% attack-success increase, and downstream application risk. It is relevant to biometric identity authentication, but not directly to password authentication.

The machine value `invalid_evidence_count=0` is consistent with the IDs and provenance reviewed. That structural result does not establish that all five selected papers are equally relevant to the research question.

## Findings requiring qualification

### Major — MIGP gap statement understates the reported deployment

The MIGP paper analysis correctly says the authors worked with Cloudflare to deploy the service in practice. The corresponding research-gap statement then says evaluation “mainly reports simulation results” and that real-user and cross-service deployment still need validation. That wording can lead readers to believe no practical deployment occurred, contradicting the same report’s paper analysis and the abstract.

A faithful gap would distinguish the two facts: the abstract reports a practical Cloudflare deployment and simulated attack-effectiveness results, but does not provide detailed field outcomes, user-level false-positive/usability measurements, deployment scale, or long-term adaptation results. Keep those as gaps only to the extent the abstract is silent about them.

### Moderate — the five-paper set is heterogeneous for a password-login question

For the stated focus “password authentication and login security,” the corpus divides into:

- **Directly relevant (2/5):** browser-fingerprint-assisted website login/risk authentication (citation 1) and compromised-password checking/credential tweaking (citation 2).
- **Adjacent (1/5):** facial liveness and biometric identity verification (citation 5). It supports a broader authentication-factor comparison, not a claim about password defenses.
- **Tangential to user login (2/5):** DANE/SMTP channel authentication and certificate operations (citation 4), and kernel CFI using ARM Pointer Authentication (citation 3). “Pointer Authentication” here is a hardware mechanism for protecting code pointers; it is not account authentication.

The report’s evidence-scope text does disclose the topics, and its PAL research-gap text explicitly notes that PAL was not evaluated for password-login endpoints. That transparency is useful. Still, the first cross-paper comparison groups FLV with password/login risks, and the method synthesis generalizes the five papers to “login security research.” Those claims should instead be framed as cross-domain analogies among authentication/security systems, while direct conclusions about password login should be anchored primarily in citations 1 and 2. Do not characterize all five as highly relevant password-authentication studies.

### Moderate — cross-domain operational synthesis needs an explicit boundary

The MIGP–DANE comparison supports a useful observation that deployability and operations affect security mechanisms. DANE’s SMTP/TLSA deployment problem is not evidence about user login or password-management deployments, though. Mark this as a cross-domain operational analogy rather than direct evidence about password-login controls.

### Minor — distinguish observed omissions from author-stated research gaps

The report correctly marks all five limitations as `not_stated`. Several `research_gaps`, including extending PAL to authentication infrastructure and evaluating long-term attack adaptation, are reviewer-derived proposals based on what these abstracts do not describe; the abstracts do not necessarily name those items as their own future-work agenda. Label such statements as inferences from this selected abstract set rather than author-reported gaps.

## CJK count and non-padding assessment

The independently recomputed count is **2,428 CJK ideographs**, 928 above the contract minimum. The count uses the structured `report_content`, not markdown, title, or citation list. The countable text includes five distinct method/finding summaries, two cross-paper comparisons, four evidence-linked synthesis statements, and scope/gap explanations. Some source facts are intentionally reused when the paper analysis is carried into a comparison or finding; I did not find duplicated filler being used to reach the threshold.

The count passes, but it should not be treated as a relevance score. A long report based on a mixed corpus can meet the length contract while still needing to label direct evidence separately from adjacent analogies.

## Limitations of this review

This review used the structured report content, the supplied matrix and citation manifest, and the matching frozen abstracts. It did not inspect full papers, so it cannot verify claims beyond those abstracts or make a full-text assessment of limitations, methods, or experimental validity. No model, deployment action, production code change, or Git operation was performed.

## Content-review disposition

The report meets the numeric 1,500-character gate and is mostly faithful to its abstract evidence. Before presenting it as a focused password-authentication review, correct the MIGP deployment gap wording and qualify the DANE/PAL/FLV contributions as adjacent or cross-domain evidence. This disposition is limited to report content; it is not an acceptance decision or a declaration that Spec 030 is complete.

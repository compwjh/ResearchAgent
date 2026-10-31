# Spec 030 report v5 — content review

Date: 2026-10-30  
Task: `bdcd7fc185425e0f8443599e9cdbe8ec`, report version 5  
Review scope: canonical `04-report.json`, published Markdown/HTML, citation manifest, `05-artifacts.json`, prior v2 content review, the real matrix at `20261030-real-report-r2/05-matrix.json`, and five frozen primary catalog abstracts. This is a single-reviewer content review. It does not assess Spec 030 closure.

## Overall result

**Qualified content pass for an abstract-level, mixed-scope synthesis.** The previous v2 review's major MIGP deployment contradiction is corrected. The report now separates MIGP's simulated 94% attack-effectiveness result from the separately reported Cloudflare deployment, and it does not imply that deployment effects were measured in the simulation. It also makes the relationship of each paper to password login explicit rather than treating all five as equally relevant.

I independently recomputed **2,912 CJK ideographs** from `report_content`, matching `quality_validation.cjk_count`. The report has five paper analyses, five comparisons, six evidence-supported synthesis findings, and six stated-inference gaps. Its length comes from distinct methods/findings, threat and system-layer comparisons, deployment distinctions, and scoped gaps. Some central distinctions recur between comparisons and synthesis, but I did not find filler or repeated boilerplate used to reach the threshold.

The remaining limitations are non-blocking for this qualified content disposition: citations are not human-readable bibliographic references in the downloaded report; one DANE gap sentence overstates what the abstract omits; and repeated dimension labels make comparison headings ambiguous. These should be improved before presenting this artifact as a polished standalone literature review.

## Source and citation traceability

All five matrix Evidence rows are `available` at `abstract` level, and the five citation manifest entries map one-to-one to `evidence-1` through `evidence-5`. I read the primary paper-search database in read-only mode and compared each frozen abstract digest with the matrix locator; all five digests match. No full-text claims are made, and the scope paragraph explicitly says the report has no full text, figures, or appendices.

The downloaded report's citation list currently renders only opaque paper IDs and Evidence IDs (Markdown lines 80–84); the supplied `citations.json` maps citation numbers to paper IDs and Evidence IDs but does not include titles, authors, DOI, or a source link. This preserves internal traceability but is weak for a reader trying to identify and verify a cited work from the report files alone. Add human-readable bibliographic metadata or a resolvable citation link when the artifact contract permits it.

## Per-paper fidelity and relevance

The primary abstract hashes matched the matrix snapshots. The report's per-paper methods and findings are materially faithful to the five abstracts:

- **Browser fingerprinting / phishing:** accurately describes fingerprint-vector replication, risk-based authentication and 2FA bypass, the phishing-site longitudinal observation, and vendor disclosure. The report labels it **adjacent** to password login and names the protected object and Web-authentication layer; this is more precise than v2's “direct” classification for a password-specific question.
- **MIGP / compromised credential checking:** accurately describes credential tweaking, privacy and breach-data extraction constraints, the simulated 94% reduction against a 1,000-guess attack, response time, and Cloudflare deployment. It is the only **direct** password-credential study in this five-paper set.
- **PAL / ARM Pointer Authentication:** accurately reports kernel CFI, refinement, post-validation, benchmark overheads, iOS-kernel attack vectors, and the open-source plan. It explicitly says this hardware primitive protects kernel control flow rather than user login; **cross-domain** is appropriate.
- **DANE / SMTP:** accurately reports TLSA/DNSSEC server authentication, more than one million TLSA-bearing SMTP domains, longitudinal measurement, the 39-operator survey, synchronization and automatic-reissue problems, CA-certificate concerns, and released tools. It is clearly labeled **cross-domain**, not password authentication.
- **Facial liveness verification:** accurately reports LiveBugger, anti-deepfake weaknesses, bias, adversarial training, input-quality effects, the up-to-70% attack-success increase, downstream proof-of-concept attacks, and vendor confirmation. **Adjacent** biometric/PaaS identity authentication is a fair classification, not direct password evidence.

The cross-paper synthesis consistently keeps the system layers separate. It says threat-success rates cannot be compared directly, distinguishes simulations from deployment facts, identifies PAL's open-source plan as different from deployment, and restricts password-login conclusions to MIGP. It does not overstate the three non-password papers as highly relevant password studies.

## Inference, gaps, and remaining wording issues

All six `research_gaps` are labeled as reviewer-derived inference from the supplied evidence, rather than author-stated future work. This correctly separates source limitations from what the review cannot determine from abstracts. The MIGP deployment gap now says deployment is reported but scale, duration, alert burden, and real-world longitudinal effects are unspecified; that resolves the v2 contradiction.

Two gap statements could be more exact:

1. The first gap says sample or platform details are “not provided,” although the abstracts do provide some high-level details (DANE's 39 operators and some >100K-domain services; FLV's representative platforms). The intended limitation appears to be that the abstracts lack detailed sampling frames, platform identities, and reproducibility information. State that narrower claim.
2. The DANE gap says the abstract does not report “deployment longitudinal results,” while the same abstract reports longitudinal measurement and summarizes operational findings. Clarify that the abstract omits the measurement window, detailed time series, and representativeness, rather than implying it has no longitudinal results.

One comparison describes PAL as handling a “consistency issue” in the context of preemptive hijacking and brute-forcing. That wording is imprecise: the abstract says PAL addresses hindsight problems of PA for in-kernel use, including those attack settings. Rephrase to preserve that specific claim. The comparison labels also repeat the two dimension names (`password authentication login security` twice and `研究方法` three times; Markdown lines 46–58). Distinct descriptive headings would make the five comparisons easier to scan.

## CJK count and scope limits

The independent count is **2,912**, above the 1,500 minimum. The report uses the countable structured body, not title, Markdown, citation list, or IDs. Per-paper text and the comparisons cover different analytic questions; synthesis restates some conclusions for a compact takeaway, but I found no evidence of empty repeated text being used as padding.

Only the five selected abstracts were examined. This review cannot validate full-text methods, experimental design, sampling, ethical review, or author-stated limitations beyond what the abstracts say. The result is a faithful and explicit abstract-level synthesis, not a comprehensive review of password authentication: four of its five sources are adjacent or cross-domain, and the report correctly exposes that narrow direct evidence base.

## Disposition

**Qualified PASS for report v5 content against the supplied abstract evidence.** The previous MIGP contradiction is closed; paper-level summaries, relevance categories, deployment distinctions, and inferred-gap labels are materially sound. Improve citation readability and the two DANE/sample wording points plus comparison labels before treating the downloaded files as a polished standalone review. This disposition does not declare Spec 030 complete or accepted.

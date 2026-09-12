import pathlib
import textwrap

import pytest

from backend.app.paper_discovery.infrastructure.usenix_paper_parser import (
    USENIX_PARSE_FAILED,
    UsenixAcceptedParser,
    UsenixPaperParseError,
    parse_accepted_listing,
    parse_accepted_papers,
    parse_usenix_detail,
)

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "usenix"


LISTING_URL = "https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
DETAIL_URL = "https://www.usenix.org/conference/usenixsecurity26/presentation/peng-jiaqian"
LISTING_HTML = """
<main>
  <a href="/conference/usenixsecurity26/presentation/peng-jiaqian">Paper title</a>
  <a href="/conference/usenixsecurity26/presentation/peng-jiaqian">Duplicate</a>
  <a href="/conference/usenixsecurity26/program">Program</a>
  <a href="https://evil.example/presentation/not-usenix">External</a>
  <a href="/conference/usenixsecurity26/presentation/with-query?token=secret">Token</a>
</main>
"""
DETAIL_HTML = """
<html><head>
  <meta name="citation_title" content="A Secure Accepted Paper">
  <meta name="citation_author" content="Alice Example">
  <meta name="citation_author" content="Bob Researcher">
  <meta name="citation_publication_date" content="2026-05-01">
</head><body>
  <a href="/system/files/usenixsecurity26-peng-jiaqian.pdf">PDF</a>
  <a href="/system/files/conference/usenixsecurity26/sec26_prepub_peng-jiaqian.pdf">Prepublication PDF</a>
  <a href="https://evil.example/paper.pdf">External PDF</a>
  <a href="/system/files/leak.pdf?token=secret">Token PDF</a>
</body></html>
"""


def test_listing_extracts_only_explicit_presentation_links_and_deduplicates():
    assert parse_accepted_listing(LISTING_HTML, page_url=LISTING_URL) == (
        DETAIL_URL,
    )


def test_detail_extracts_metadata_and_both_explicit_pdf_variants():
    paper = parse_usenix_detail(DETAIL_HTML, page_url=DETAIL_URL)

    assert paper.article_url == DETAIL_URL
    assert paper.title == "A Secure Accepted Paper"
    assert paper.authors == ("Alice Example", "Bob Researcher")
    assert paper.year == 2026
    assert paper.official_pdf_url == "https://www.usenix.org/system/files/usenixsecurity26-peng-jiaqian.pdf"
    assert paper.prepublication_pdf_url == (
        "https://www.usenix.org/system/files/conference/usenixsecurity26/sec26_prepub_peng-jiaqian.pdf"
    )
    assert paper.pdf_url == paper.official_pdf_url
    assert paper.pdf_access == "public"
    assert paper.publication_stage == "accepted"
    assert paper.source_kind == "usenix_accepted"


def test_detail_supports_explicit_author_markup():
    html = """
    <h1>Markup Authors</h1><time datetime="2025-08-01"></time>
    <span class="author">Ada Lovelace</span><span itemprop="author">Grace Hopper</span>
    """
    paper = parse_usenix_detail(html, page_url=DETAIL_URL)
    assert paper.title == "Markup Authors"
    assert paper.authors == ("Ada Lovelace", "Grace Hopper")
    assert paper.year == 2025


def test_parser_rejects_non_usenix_page_without_echoing_sensitive_url():
    with pytest.raises(UsenixPaperParseError) as error:
        parse_usenix_detail(
            DETAIL_HTML,
            page_url="https://www.usenix.org/conference/usenixsecurity26/presentation/peng?token=secret",
        )
    assert error.value.code == USENIX_PARSE_FAILED
    assert "secret" not in repr(error.value)


def test_object_parser_matches_functional_entry_points():
    parser = UsenixAcceptedParser()
    assert parser.parse_listing(LISTING_HTML, page_url=LISTING_URL) == (DETAIL_URL,)
    assert parser.parse_detail(DETAIL_HTML, page_url=DETAIL_URL).title == "A Secure Accepted Paper"
    assert parser.parse_papers(FIXTURE_DIR.joinpath("cycle1-accepted-papers.html").read_text("utf-8"),
                                page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers")


def _load(name: str) -> str:
    return textwrap.dedent(FIXTURE_DIR.joinpath(name).read_text("utf-8")).strip()


def test_cycle1_papers_extract_title_authors_abstract_and_year():
    papers = parse_accepted_papers(
        _load("cycle1-accepted-papers.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers",
    )
    assert [paper.title for paper in papers] == ["Cycle One Title", "Carol On Networks"]
    first = papers[0]
    assert first.article_url == "https://www.usenix.org/conference/usenixsecurity26/presentation/alice-secure"
    assert first.authors == ("Alice Example", "Bob Researcher")
    assert first.abstract == (
        "This paper studies secure systems and mentions keywords in the abstract text."
    )
    assert first.year == 2026
    assert papers[1].authors == ("Carol Danvers",)


def test_listing_papers_have_no_pdf_and_empty_keywords():
    papers = parse_accepted_papers(
        _load("cycle1-accepted-papers.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers",
    )
    for paper in papers:
        assert paper.official_pdf_url is None
        assert paper.prepublication_pdf_url is None
        assert paper.pdf_url is None
        assert paper.pdf_access == "unknown"
        assert paper.keywords == ()


@pytest.mark.parametrize(
    "name,page_url,title,year,authors",
    [
        (
            "usenixsecurity25-cycle1-accepted-papers.html",
            "https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers",
            "Dave Accepted In 2025",
            2025,
            ("Dave Grohl", "Eve Ada"),
        ),
        (
            "usenixsecurity24-summer-accepted-papers.html",
            "https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers",
            "Summer One",
            2024,
            ("Summer Field", "Autumn Leaf"),
        ),
        (
            "usenixsecurity24-fall-accepted-papers.html",
            "https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers",
            "Fall First",
            2024,
            ("Fall Winter", "Spring Rain"),
        ),
    ],
)
def test_cycle_summer_and_fall_layouts_parse(name, page_url, title, year, authors):
    papers = parse_accepted_papers(_load(name), page_url=page_url)
    assert papers[0].title == title
    assert papers[0].year == year
    assert papers[0].authors == authors
    assert papers[0].abstract
    assert papers[0].keywords == ()


def test_real_listing_field_markup_yields_authors_and_abstract_for_every_paper():
    """usenix.org puts the Drupal field class on a <div>; the <p> has no class."""
    papers = parse_accepted_papers(
        _load("cycle1-accepted-papers.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers",
    )
    assert [paper.authors for paper in papers] == [
        ("Alice Example", "Bob Researcher"),
        ("Carol Danvers",),
    ]
    assert [paper.abstract for paper in papers] == [
        "This paper studies secure systems and mentions keywords in the abstract text.",
        "A study of networked devices.",
    ]


def test_listing_field_class_on_non_paragraph_element_is_matched():
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/span-field">Span Field</a></h2>
        <span class="field field-name-field-paper-people-text">Dana Scully, <em>FBI</em></span>
        <section class="field field-name-field-paper-description-long"><p>An abstract held by a section.</p></section>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert len(papers) == 1
    assert papers[0].authors == ("Dana Scully",)
    assert papers[0].abstract == "An abstract held by a section."


def test_listing_field_text_does_not_leak_from_sibling_blocks():
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/leak-check">Leak Check</a></h2>
        <div class="content">
        <div class="field field-name-field-paper-people-text field-type-text-long field-label-hidden"><div class="field-items"><div class="field-item odd"><p>Alice Example, <em>Stanford University</em></p></div></div></div>
        <div class="usenix-schedule-media media-header">Available Media</div>
        <div class="field field-name-field-paper-description-long field-type-text-long field-label-hidden"><div class="field-items"><div class="field-item odd"><p>The abstract body.</p></div></div></div>
        <div class="usenix-schedule-media media-footer">Download Slides</div>
        </div>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert len(papers) == 1
    assert papers[0].authors == ("Alice Example",)
    assert papers[0].abstract == "The abstract body."


def test_listing_legacy_short_field_class_on_paragraph_still_parses():
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/legacy">Legacy Markup</a></h2>
        <p class="field-paper-people-text">Grace Hopper, <em>US Navy;</em> Ada Lovelace</p>
        <p class="field-paper-description-long">A legacy abstract paragraph.</p>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert len(papers) == 1
    assert papers[0].authors == ("Grace Hopper", "Ada Lovelace")
    assert papers[0].abstract == "A legacy abstract paragraph."


def test_listing_people_field_excludes_emphasis_affiliations_from_authors():
    """Real 2024 markup: `<em>` wraps the affiliation, never an author."""
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/ren">Secure Collaborative ML</a></h2>
        <div class="field field-name-field-paper-people-text field-type-text-long field-label-hidden"><div class="field-items field-items"><div class="field-item odd"><p>Zhenghang Ren, Mingxuan Fan, Zilong Wang, Junxue Zhang, and Chaoliang Zeng, <em>iSING Lab@The Hong Kong University of Science and Technology;</em> Zhicong Huang and Cheng Hong, <em>Ant Group;</em> Kai Chen, <em>iSING Lab@The Hong Kong University of Science and Technology and University of Science and Technology of China</em></p></div></div></div>
        <div class="field field-name-field-paper-description-long field-type-text-long field-label-hidden"><div class="field-items field-items"><div class="field-item odd"><p>An abstract for the emphasis test.</p></div></div></div>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert len(papers) == 1
    assert papers[0].authors == (
        "Zhenghang Ren",
        "Mingxuan Fan",
        "Zilong Wang",
        "Junxue Zhang",
        "Chaoliang Zeng",
        "Zhicong Huang",
        "Cheng Hong",
        "Kai Chen",
    )
    assert papers[0].abstract == "An abstract for the emphasis test."


def test_listing_authors_never_keep_affiliation_fragments_from_emphasis():
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/fragments">Fragment Check</a></h2>
        <p class="field-paper-people-text">Hyeonmin Lee, <em>Seoul National University;</em> Md. Ishtiaq Ashiq, <em>Virginia Tech;</em> Taejoong Chung, <em>Virginia Tech</em></p>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert papers[0].authors == ("Hyeonmin Lee", "Md. Ishtiaq Ashiq", "Taejoong Chung")
    for author in papers[0].authors:
        assert " " in author
        assert "@" not in author


def test_listing_people_field_ignores_award_banner_in_later_paragraph():
    """Real 2022 markup: the people field repeats as <p>s; only the first is authors.

    The second ``<p>`` (``style="font-weight: 600; font-style: italic;"``) holds
    the award / honour banner, which must never reach ``_split_authors``.
    """
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity22/presentation/xue-diwen">OpenVPN is Open to VPN Fingerprinting</a></h2>
        <div class="field field-name-field-paper-people-text field-type-text-long field-label-hidden">
        <div class="field-items field-items"><div class="field-item odd">
        <p>Diwen Xue, Reethika Ramesh, and Arham Jain, <em>University of Michigan;</em> Michalis Kallitsis, <em>Merit Network;</em> J. Alex Halderman, <em>University of Michigan;</em> Jedidiah R. Crandall, <em>University of Michigan;</em> Roya Ensafi, <em>University of Michigan</em></p>
        <p style="font-weight: 600; font-style: italic;">Distinguished Paper Award Winner and First Prize Winner of the 2022 Internet Defense Prize</p>
        </div></div>
        </div>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity22/technical-sessions"
    )
    assert len(papers) == 1
    assert papers[0].authors == (
        "Diwen Xue",
        "Reethika Ramesh",
        "Arham Jain",
        "Michalis Kallitsis",
        "J. Alex Halderman",
        "Jedidiah R. Crandall",
        "Roya Ensafi",
    )
    for author in papers[0].authors:
        assert not any(marker in author for marker in ("Award", "Distinguished", "Winner"))


def test_listing_people_field_drops_any_text_after_the_first_paragraph():
    """Once the field's first <p> closes, no later text is collected at all."""
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity22/presentation/trailing">Trailing Text</a></h2>
        <div class="field field-name-field-paper-people-text field-type-text-long field-label-hidden">
        <div class="field-items"><div class="field-item odd">
        <p>Alice Example, <em>MIT</em></p>
        <div class="award-note">Distinguished Paper Award Winner</div>
        </div></div>
        </div>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity22/technical-sessions"
    )
    assert papers[0].authors == ("Alice Example",)


def test_listing_abstract_field_still_collects_every_paragraph():
    """Only the people field stops at the first <p>; the abstract keeps all of it."""
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity22/presentation/multi-paragraph">Multi Paragraph</a></h2>
        <p class="field-paper-people-text">Alice Example, <em>MIT</em></p>
        <div class="field field-name-field-paper-description-long field-type-text-long field-label-hidden">
        <div class="field-items"><div class="field-item odd">
        <p>First abstract paragraph.</p>
        <p>Second abstract paragraph.</p>
        </div></div>
        </div>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity22/technical-sessions"
    )
    assert papers[0].authors == ("Alice Example",)
    # Exact equality, not a substring check: the two paragraphs of the field are
    # separate text nodes, and gluing them together (`First…paragraph.Second…`)
    # must be caught rather than masked by `in`.
    assert papers[0].abstract == "First abstract paragraph. Second abstract paragraph."


def test_listing_abstract_separates_every_block_level_boundary():
    """`<p>` / `<div>` / `<br/>` / `<li>` boundaries all separate field text."""
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/block-boundaries">Block Boundaries</a></h2>
        <p class="field-paper-people-text">Alice Example, <em>MIT</em></p>
        <div class="field field-name-field-paper-description-long field-type-text-long field-label-hidden">
        <div class="field-items"><div class="field-item odd">
        <p>First paragraph.</p>
        <div>Second paragraph.</div>
        <p>Third<br/>paragraph.</p>
        <ul><li>Fourth paragraph.</li></ul>
        </div></div>
        </div>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert papers[0].abstract == (
        "First paragraph. Second paragraph. Third paragraph. Fourth paragraph."
    )


def test_listing_abstract_does_not_split_inline_emphasis_text():
    """A block boundary separates fragments; an inline `<em>` must not."""
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/inline-emphasis">Inline Emphasis</a></h2>
        <p class="field-paper-people-text">Alice Example, <em>MIT</em></p>
        <div class="field field-name-field-paper-description-long field-type-text-long field-label-hidden">
        <div class="field-items"><div class="field-item odd">
        <p>The <em>state-of-the-art</em> system wins.</p>
        <div>It <em>outperforms</em> the baseline.</div>
        </div></div>
        </div>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert papers[0].abstract == (
        "The state-of-the-art system wins. It outperforms the baseline."
    )


def test_listing_abstract_keeps_emphasis_markup():
    """Only the people field drops `<em>`; an emphasised abstract is kept."""
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/emphatic">Emphatic Abstract</a></h2>
        <p class="field-paper-people-text">Alice Example, <em>MIT</em></p>
        <p class="field-paper-description-long">The <em>key</em> result is emphatic.</p>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert papers[0].authors == ("Alice Example",)
    assert papers[0].abstract == "The key result is emphatic."


def test_listing_self_closing_emphasis_keeps_the_counter_balanced():
    """A self-closing `<em/>` must not suppress the authors that follow it."""
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity26/presentation/self-closing">Self Closing</a></h2>
        <p class="field-paper-people-text">Alice Example, <em/> Bob Researcher, <em>MIT</em></p>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert papers[0].authors == ("Alice Example", "Bob Researcher")


def test_cross_year_presentation_link_is_skipped():
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity25/presentation/stale">Stale Reference</a></h2>
        <p class="field-paper-people-text">Old Guard</p>
        <p class="field-paper-description-long">A paper that must not be picked up.</p>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert papers == ()


def test_non_usenix_listing_page_raises_without_echoing_token():
    with pytest.raises(UsenixPaperParseError) as error:
        parse_accepted_papers(
            _load("cycle1-accepted-papers.html"),
            page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers?token=secret",
        )
    assert error.value.code == USENIX_PARSE_FAILED
    assert "secret" not in repr(error.value)


def test_detail_extracts_abstract_from_paper_description_field():
    paper = parse_usenix_detail(
        _load("presentation-detail.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity24/presentation/zhang-qingzhao",
    )
    assert paper.abstract == (
        "Collaborative perception greatly enhances automated driving, "
        "but it also widens the attack surface."
    )


def test_detail_abstract_is_not_the_open_access_site_notice():
    paper = parse_usenix_detail(
        _load("presentation-detail.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity24/presentation/zhang-qingzhao",
    )
    assert "Open Access" not in paper.abstract
    assert "USENIX is committed" not in paper.abstract


def test_detail_without_abstract_field_keeps_empty_abstract():
    paper = parse_usenix_detail(
        _load("presentation-detail-no-abstract.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity24/presentation/hopper-grace",
    )
    assert paper.abstract == ""
    assert "Open Access" not in paper.abstract


NO_CITATION_META_URL = "https://www.usenix.org/conference/usenixsecurity22/presentation/example"


def test_detail_without_citation_meta_falls_back_to_people_field_and_url_year():
    """usenix.org only emits ``citation_*`` on some pages; the rest must still parse."""
    paper = parse_usenix_detail(
        _load("presentation-detail-no-citation-meta.html"),
        page_url=NO_CITATION_META_URL,
    )
    assert paper.title
    assert "Snooping the GPU via Magnetic Side Channel" in paper.title
    assert paper.authors == (
        "Henrique Teles Maia",
        "Chang Xiao",
        "Dingzeyu Li",
        "Eitan Grinspun",
        "Changxi Zheng",
    )
    assert paper.year == 2022
    assert paper.abstract == (
        "Neural network applications have become popular in both enterprise and personal settings. "
        "We examine the magnetic fields emitted by accelerated hardware and discuss countermeasures."
    )
    assert paper.article_url == NO_CITATION_META_URL


def test_detail_without_citation_meta_keeps_affiliations_out_of_authors():
    paper = parse_usenix_detail(
        _load("presentation-detail-no-citation-meta.html"),
        page_url=NO_CITATION_META_URL,
    )
    for author in paper.authors:
        assert " " in author
        assert "@" not in author
        assert "University" not in author
        assert "Research" not in author


def test_detail_without_citation_meta_abstract_is_not_the_open_access_notice():
    paper = parse_usenix_detail(
        _load("presentation-detail-no-citation-meta.html"),
        page_url=NO_CITATION_META_URL,
    )
    assert "Open Access" not in paper.abstract
    assert "USENIX is committed" not in paper.abstract


def test_detail_without_citation_meta_and_without_people_field_stays_fail_closed():
    markup = textwrap.dedent(
        """
        <html><head><title>No People | USENIX</title></head><body>
        <h1 id="page-title">No People Field</h1>
        <div class="field field-name-field-paper-description field-type-text-long field-label-hidden">
        <div class="field-items"><div class="field-item odd"><p>An abstract without any author.</p></div></div>
        </div>
        </body></html>
        """
    )
    with pytest.raises(UsenixPaperParseError) as error:
        parse_usenix_detail(markup, page_url=NO_CITATION_META_URL)
    assert error.value.code == USENIX_PARSE_FAILED


def test_detail_author_fallback_ignores_a_sidebar_block_ahead_of_the_paper():
    """The first ``view-mode-full`` block can be a sidebar teaser, not this paper."""
    markup = textwrap.dedent(
        """
        <html><head><meta name="citation_publication_date" content="2026-05-01"></head><body>
        <h1 id="page-title">Real Paper Title</h1>
        <aside>
        <article class="node node-paper view-mode-full">
        <h2><a href="/conference/usenixsecurity26/presentation/sidebar-teaser">Sidebar Teaser</a></h2>
        <div class="field field-name-field-paper-people-text"><div class="field-items"><div class="field-item odd">
        <p>Sidebar Person, <em>Elsewhere</em></p>
        </div></div></div>
        </article>
        </aside>
        <article class="node node-paper view-mode-full">
        <h2><a href="/conference/usenixsecurity26/presentation/peng-jiaqian">Real Paper Title</a></h2>
        <div class="field field-name-field-paper-people-text"><div class="field-items"><div class="field-item odd">
        <p>Real Author, <em>Real University</em></p>
        </div></div></div>
        </article>
        </body></html>
        """
    )
    paper = parse_usenix_detail(markup, page_url=DETAIL_URL)
    assert paper.title == "Real Paper Title"
    assert paper.authors == ("Real Author",)
    assert "Sidebar Person" not in paper.authors


def test_detail_author_fallback_matches_the_page_url_despite_a_trailing_slash():
    """A trailing ``/`` on either side must not defeat the presentation identity check.

    The paper's own block is the *second* one and its ``<h2>`` text deliberately
    differs from the parsed title, so only the URL comparison can select it.
    """
    markup = textwrap.dedent(
        """
        <html><head><meta name="citation_publication_date" content="2026-05-01"></head><body>
        <h1 id="page-title">Real Paper Title</h1>
        <article class="node node-paper view-mode-full">
        <h2><a href="/conference/usenixsecurity26/presentation/sidebar-teaser">Sidebar Teaser</a></h2>
        <div class="field field-name-field-paper-people-text"><div class="field-items"><div class="field-item odd">
        <p>Sidebar Person, <em>Elsewhere</em></p>
        </div></div></div>
        </article>
        <article class="node node-paper view-mode-full">
        <h2><a href="/conference/usenixsecurity26/presentation/peng-jiaqian/">Block Heading</a></h2>
        <div class="field field-name-field-paper-people-text"><div class="field-items"><div class="field-item odd">
        <p>Real Author, <em>Real University</em></p>
        </div></div></div>
        </article>
        </body></html>
        """
    )
    paper = parse_usenix_detail(markup, page_url=DETAIL_URL)
    assert paper.authors == ("Real Author",)


def test_detail_author_fallback_matches_the_paper_block_by_title():
    """Without any presentation href, the title identifies this page's block."""
    markup = textwrap.dedent(
        """
        <html><head>
        <meta name="citation_title" content="Real Paper Title">
        <meta name="citation_publication_date" content="2026-05-01">
        </head><body>
        <article class="node node-paper view-mode-full">
        <h2>Sidebar Teaser</h2>
        <div class="field field-name-field-paper-people-text"><div class="field-items"><div class="field-item odd">
        <p>Sidebar Person, <em>Elsewhere</em></p>
        </div></div></div>
        </article>
        <article class="node node-paper view-mode-full">
        <h2>Real Paper Title</h2>
        <div class="field field-name-field-paper-people-text"><div class="field-items"><div class="field-item odd">
        <p>Real Author, <em>Real University</em></p>
        </div></div></div>
        </article>
        </body></html>
        """
    )
    paper = parse_usenix_detail(markup, page_url=DETAIL_URL)
    assert paper.title == "Real Paper Title"
    assert paper.authors == ("Real Author",)
    assert "Sidebar Person" not in paper.authors


def test_detail_with_citation_meta_is_unchanged_by_the_fallback():
    paper = parse_usenix_detail(
        _load("presentation-detail.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity24/presentation/zhang-qingzhao",
    )
    assert paper.title == "Cache Me If You Can: A Study of Side Channels"
    assert paper.authors == ("Qingzhao Zhang", "Ada Lovelace")
    assert paper.year == 2024
    assert paper.abstract == (
        "Collaborative perception greatly enhances automated driving, "
        "but it also widens the attack surface."
    )


def test_detail_citation_meta_authors_win_over_the_people_field():
    markup = textwrap.dedent(
        """
        <html><head>
        <meta name="citation_title" content="Meta Wins">
        <meta name="citation_author" content="Alice Example">
        <meta name="citation_publication_date" content="2026-05-01">
        </head><body>
        <article class="node node-paper view-mode-full">
        <div class="field field-name-field-paper-people-text"><div class="field-items"><div class="field-item odd">
        <p>Someone Else, <em>MIT</em></p>
        </div></div></div>
        </article>
        </body></html>
        """
    )
    paper = parse_usenix_detail(markup, page_url=DETAIL_URL)
    assert paper.title == "Meta Wins"
    assert paper.authors == ("Alice Example",)
    assert paper.year == 2026


def test_listing_still_ignores_view_mode_full_articles():
    """The detail fallback widens the article match for details only, never listings."""
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-full">
        <h2><a href="/conference/usenixsecurity26/presentation/detail-only">Detail Only</a></h2>
        <div class="field field-name-field-paper-people-text"><div class="field-items"><div class="field-item odd">
        <p>Alice Example, <em>MIT</em></p>
        </div></div></div>
        </article>
        </main>
        """
    )
    assert parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    ) == ()


def test_detail_without_citation_meta_title_drops_the_site_suffix():
    """The ``<h1 id="page-title">`` text is clean; the ``<title>`` site suffix must not win."""
    paper = parse_usenix_detail(
        _load("presentation-detail-no-citation-meta.html"),
        page_url=NO_CITATION_META_URL,
    )
    assert paper.title == (
        "Can one hear the shape of a neural network?: Snooping the GPU via Magnetic Side Channel"
    )
    assert "USENIX" not in paper.title
    assert "|" not in paper.title


def test_detail_h1_title_wins_over_the_document_title_tag():
    """Document order puts ``<title>`` first; the clean ``<h1>`` must still be preferred."""
    markup = textwrap.dedent(
        """
        <html><head><title>Site Suffixed Title | USENIX</title>
        <meta name="citation_author" content="Alice Example">
        <meta name="citation_publication_date" content="2026-05-01">
        </head><body>
        <h1 id="page-title">Clean Paper Title</h1>
        </body></html>
        """
    )
    paper = parse_usenix_detail(markup, page_url=DETAIL_URL)
    assert paper.title == "Clean Paper Title"


@pytest.mark.parametrize(
    "head_meta,expected",
    [
        (
            '<meta name="citation_title" content="Meta Title">'
            '<meta property="og:title" content="Og Title">',
            "Meta Title",
        ),
        ('<meta property="og:title" content="Og Title">', "Og Title"),
    ],
)
def test_detail_title_priority_is_citation_then_og_then_h1_then_title_tag(head_meta, expected):
    markup = (
        "<html><head>"
        + head_meta
        + '<title>Doc Title | USENIX</title>'
        + '<meta name="citation_author" content="Alice Example">'
        + '<meta name="citation_publication_date" content="2026-05-01">'
        + "</head><body><h1>H1 Title</h1></body></html>"
    )
    assert parse_usenix_detail(markup, page_url=DETAIL_URL).title == expected


@pytest.mark.parametrize(
    "document_title,expected",
    [
        ("A Plain Paper Title | USENIX", "A Plain Paper Title"),
        ("A Dashed Paper Title - USENIX", "A Dashed Paper Title"),
        ("A Site Named Title | USENIX Association", "A Site Named Title"),
    ],
)
def test_detail_title_tag_fallback_strips_the_site_suffix(document_title, expected):
    markup = textwrap.dedent(
        f"""
        <html><head><title>{document_title}</title>
        <meta name="citation_author" content="Alice Example">
        <meta name="citation_publication_date" content="2026-05-01">
        </head><body><p>Body text.</p></body></html>
        """
    )
    paper = parse_usenix_detail(markup, page_url=DETAIL_URL)
    assert paper.title == expected
    assert "USENIX" not in paper.title


def test_detail_title_tag_fallback_keeps_a_pipe_inside_the_paper_title():
    """Only a trailing site name is removed; a ``|`` in the title body is not."""
    markup = textwrap.dedent(
        """
        <html><head><title>Pipes | Are Not Site Names</title>
        <meta name="citation_author" content="Alice Example">
        <meta name="citation_publication_date" content="2026-05-01">
        </head><body><p>Body text.</p></body></html>
        """
    )
    assert parse_usenix_detail(markup, page_url=DETAIL_URL).title == "Pipes | Are Not Site Names"


def test_detail_with_citation_meta_title_keeps_no_site_suffix():
    paper = parse_usenix_detail(
        _load("presentation-detail.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity24/presentation/zhang-qingzhao",
    )
    assert paper.title == "Cache Me If You Can: A Study of Side Channels"
    assert "USENIX" not in paper.title

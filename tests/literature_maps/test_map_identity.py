from backend.app.literature_maps.domain.identity import (
    canonical_external_ids,
    deterministic_identity_key,
    normalize_external_id,
)


def test_identity_prefers_doi_then_arxiv_then_provider_id_without_catalog_aliasing():
    external = canonical_external_ids(
        {"DOI": "https://doi.org/10.1000/ABC", "ArXiv": "arXiv:2401.00001", "paperId": "s2-1"}
    )

    assert external == {
        "semantic_scholar": "s2-1",
        "doi": "10.1000/abc",
        "arxiv": "2401.00001",
    }
    assert deterministic_identity_key(external) == "doi:10.1000/abc"
    assert normalize_external_id("doi", "DOI:10.1000/ABC") == "10.1000/abc"


def test_identity_never_uses_title_as_deterministic_identity():
    assert deterministic_identity_key({"semantic_scholar": "s2"}) == "semantic_scholar:s2"
    assert deterministic_identity_key({}) is None

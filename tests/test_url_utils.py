from src.utils.url_utils import normalize_url


def test_normalize_url_strips_tracking_query_parameters() -> None:
    assert (
        normalize_url(
            "https://www.pwc.com/gx/en/issues/c-suite-insights/ceo-survey.html?icid=tla-top-banner&utm_source=newsletter"
        )
        == "https://www.pwc.com/gx/en/issues/c-suite-insights/ceo-survey.html"
    )


def test_normalize_url_preserves_functional_query_parameters() -> None:
    assert (
        normalize_url(
            "https://www.proximic.com/home/Resources?keywords=&typeofcontent=presentations_page&page=2"
        )
        == "https://www.proximic.com/home/Resources?keywords=&typeofcontent=presentations_page&page=2"
    )

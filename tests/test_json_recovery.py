from src.utils.json_recovery import parse_json_from_text


def test_parse_json_from_text_extracts_embedded_object() -> None:
    parsed, strategy = parse_json_from_text(
        "Model output:\n```json\n{\"result\": {\"ok\": true}}\n```",
        accepted_types=(dict,),
    )

    assert parsed == {"result": {"ok": True}}
    assert strategy == "direct_extracted"


def test_parse_json_from_text_rejects_non_accepted_json_type() -> None:
    parsed, strategy = parse_json_from_text("[1, 2, 3]", accepted_types=(dict,))

    assert parsed is None
    assert strategy == "json_non_object"


def test_parse_json_from_text_reports_invalid_json_for_unbalanced_payload() -> None:
    parsed, strategy = parse_json_from_text("{\"result\":", accepted_types=(dict,))

    assert parsed is None
    assert strategy == "invalid_json"

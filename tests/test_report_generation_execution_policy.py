from pathlib import Path

import yaml


def test_report_generation_structured_outputs_have_headroom_for_complete_json() -> None:
    config_path = Path(__file__).resolve().parents[1] / "src" / "config" / "app.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    policies = config["llm_execution_policies"]

    assert policies["report_vs"]["max_output_tokens"] == 8192
    assert policies["report_vs/taxonomy"]["max_output_tokens"] == 8192
    assert policies["report_vs/taxonomy_repair"]["max_output_tokens"] == 8192
    assert policies["report_vs/structured_output"]["max_output_tokens"] == 8192

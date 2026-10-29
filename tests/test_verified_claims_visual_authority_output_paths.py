from pathlib import Path

from src.generators.verified_claims_canary import default_visual_authority_output_dir


def test_canary_default_visual_output_avoids_nested_output_path(tmp_path):
    output_dir = tmp_path / ("r" * 160) / "output"

    resolved = Path(default_visual_authority_output_dir(str(output_dir)))

    assert resolved == output_dir.parent / "verified_claims_visual_canary"

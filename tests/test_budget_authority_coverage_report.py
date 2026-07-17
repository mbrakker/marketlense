from pathlib import Path

from scripts.quality.generate_budget_authority_coverage import (
    load_budget_authority_coverage,
    render_budget_authority_coverage,
)


def test_budget_authority_matrix_covers_material_resource_families() -> None:
    matrix = load_budget_authority_coverage(
        Path("docs/ops/budget_authority_coverage.yaml")
    )
    report = render_budget_authority_coverage(matrix)

    resource_types = {item["resource_type"] for item in matrix}
    assert {
        "llm_provider",
        "vector_store",
        "browser_use_model",
        "browser_launch",
        "pdf_process",
        "drive_read",
        "drive_write",
        "wordpress_write",
        "mailbox_read",
        "retry",
    } <= resource_types
    assert all(item["status"] == "covered" for item in matrix)
    assert "all governed by `evaluate_budget_request`" in report

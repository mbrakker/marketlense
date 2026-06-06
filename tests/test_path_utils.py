from src.utils import path_utils


def test_bounded_artifact_filename_compacts_oversized_png_name() -> None:
    assert hasattr(path_utils, "bounded_artifact_filename")

    filename = path_utils.bounded_artifact_filename(
        "report-" * 30,
        compact_stem="preview",
        extension=".png",
    )

    assert filename.startswith("preview-")
    assert filename.endswith(".png")
    assert len(filename) <= 96
    assert filename == path_utils.bounded_artifact_filename(
        "report-" * 30,
        compact_stem="preview",
        extension=".png",
    )


def test_bounded_artifact_filename_preserves_normal_name() -> None:
    assert hasattr(path_utils, "bounded_artifact_filename")

    assert (
        path_utils.bounded_artifact_filename(
            "report-contents",
            compact_stem="preview-contents",
            extension=".png",
        )
        == "report-contents.png"
    )

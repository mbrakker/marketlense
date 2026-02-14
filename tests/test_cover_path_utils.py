from src.utils.cover_path_utils import build_cover_asset_path


def test_build_cover_asset_path_is_bounded_for_long_titles():
    title = (
        "Our not-yet-trending report is back for 2026. "
        "From food to fashion to home decor and more, see where tomorrow's trends will take your audience next."
    )
    publisher = "Pinterest"
    file_id = "1T0q1n4OL3Im6tthF2n45-n4RjSwMy2kf"

    path = build_cover_asset_path("out", file_id=file_id, title=title, publisher=publisher)
    path_text = str(path)

    assert path_text.endswith(".png")
    assert "/assets/" in path_text.replace("\\", "/")
    assert len(path_text) < 220


def test_build_cover_asset_path_uses_file_id_suffix():
    path = build_cover_asset_path(
        "out",
        file_id="file_123",
        title="Retail trends 2026",
        publisher="Capgemini",
    )
    path_text = path.as_posix()
    assert "-file-123/" in path_text
    assert "-file-123.png" in path_text

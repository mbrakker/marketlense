import unittest

from src.utils.html_utils import (
    extract_body_html,
    extract_file_id,
    extract_image_sources,
    extract_preview_image,
    extract_title,
    replace_image_sources,
)


class TestHtmlUtils(unittest.TestCase):
    def test_extract_title_and_body(self) -> None:
        html = "<html><head><title>Doc</title></head><body><h1>Doc</h1><p>Hi</p></body></html>"
        self.assertEqual("Doc", extract_title(html))
        self.assertIn("<p>Hi</p>", extract_body_html(html))

    def test_extract_file_id(self) -> None:
        html = "Drive fileId: abc123"
        self.assertEqual("abc123", extract_file_id(html))

    def test_image_sources_and_replace(self) -> None:
        html = '<img src="a.png"><img src="b.png">'
        sources = extract_image_sources(html)
        self.assertEqual(["a.png", "b.png"], sources)
        replaced = replace_image_sources(html, {"a.png": "x.png"})
        self.assertIn('src="x.png"', replaced)

    def test_extract_preview_image(self) -> None:
        html = '<div class="preview"><img src="prev.png"></div>'
        self.assertEqual("prev.png", extract_preview_image(html))


if __name__ == "__main__":
    unittest.main()

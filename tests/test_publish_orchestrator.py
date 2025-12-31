import unittest
from unittest.mock import patch

from src.contracts.publish import PublishOutcome, PublishSettings
from src.contracts.wordpress import WordPressAuthSettings, WordPressPostLookupResponse
from src.orchestrators import publish_orchestrator as orch


class TestPublishOrchestrator(unittest.TestCase):
    def test_publish_runs_when_processed(self) -> None:
        settings = PublishSettings(
            schema_version="1.0",
            output_dir="./out",
            state_db=":memory:",
            wp=WordPressAuthSettings(
                schema_version="1.0",
                site_url="https://example.com",
                username="user",
                app_password="pass",
                bearer_token=None,
                post_status="publish",
            ),
        )

        html = "<html><body>Drive fileId: file123</body></html>"
        outcome = PublishOutcome(
            schema_version="1.0",
            html_path="out/report.html",
            file_id="file123",
            status="published",
            post_id=10,
            post_url="https://example.com/post",
        )

        with patch.object(orch, "list_html", return_value=type("X", (), {"html_paths": ["out/report.html"]})()):
            with patch.object(orch, "read_text", return_value=type("Y", (), {"content": html})()):
                with patch.object(orch, "state_get", return_value=type("Z", (), {"md5": "md5"})()):
                    with patch.object(orch, "state_already_published", return_value=False):
                        with patch.object(orch, "find_post_by_file_id", return_value=WordPressPostLookupResponse(
                            schema_version="1.0",
                            found=False,
                        )):
                            with patch.object(orch, "publish_html", return_value=outcome):
                                with patch.object(orch, "state_record_publish") as record_mock:
                                    results = orch.run_publish(settings, limit=1)
                                    self.assertEqual(1, len(results))
                                    self.assertEqual("published", results[0].status)
                                    record_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()

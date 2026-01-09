import json
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
            reports_db=":memory:",
            category_mapping_path="./src/config/category-mappings.yaml",
            validation_policy="warn",
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


    def test_publish_blocks_when_validation_fails(self) -> None:
        settings = PublishSettings(
            schema_version="1.0",
            output_dir="./out",
            state_db=":memory:",
            reports_db=":memory:",
            category_mapping_path="./src/config/category-mappings.yaml",
            validation_policy="block",
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
        validation_payload = json.dumps({
            "schema_version": "1.1",
            "status": "fail",
            "severity": "error",
            "issues": [{"schema_version": "1.0", "message": "bad data", "severity": "error", "affected_section": "insights"}],
        })

        def _read_text(req, ctx):
            content = html if str(req.path).endswith(".html") else validation_payload
            return type("Y", (), {"content": content})()

        with patch.object(orch, "list_html", return_value=type("X", (), {"html_paths": ["out/report.html"]})()):
            with patch.object(orch, "read_text", side_effect=_read_text):
                with patch.object(orch, "state_get", return_value=type("Z", (), {"md5": "md5"})()):
                    with patch.object(orch, "state_already_published", return_value=False):
                        with patch.object(orch, "find_post_by_file_id", return_value=WordPressPostLookupResponse(
                            schema_version="1.0",
                            found=False,
                        )):
                            with patch.object(orch, "publish_html") as publish_mock:
                                results = orch.run_publish(settings, limit=1)
                                publish_mock.assert_not_called()
                                self.assertEqual(1, len(results))
                                self.assertEqual("error", results[0].status)
                                self.assertEqual("validation_failed", results[0].error)
                                self.assertEqual("fail", results[0].validation_status)
                                self.assertTrue(results[0].validation_issues)


if __name__ == "__main__":
    unittest.main()

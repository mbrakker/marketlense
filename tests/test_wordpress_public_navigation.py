from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SHORTCODES_PATH = (
    REPO_ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "includes"
    / "class-marketlense-core-shortcodes.php"
)
REST_PROVISION_PATH = REPO_ROOT / "Wordpress" / "scripts" / "admin" / "provision.py"
SHELL_PROVISION_PATH = (
    REPO_ROOT / "Wordpress" / "scripts" / "provision-site-structure.sh"
)


def test_wordpress_primary_navigation_matches_readme_entity_model() -> None:
    source = SHORTCODES_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"public function render_primary_nav\(\): string\s*\{(?P<body>.*?)\n\s*\}",
        source,
        flags=re.S,
    )
    assert match is not None

    labels = re.findall(r"\['label' => __\('([^']+)'", match.group("body"))
    targets = re.findall(r"'target' => '([^']+)'", match.group("body"))

    assert labels == [
        "Reports",
        "Topics",
        "Publishers",
        "Signals",
        "Briefings",
        "Methodology",
    ]
    assert targets == [
        "reports",
        "topics-directory",
        "publishers-directory",
        "signals",
        "briefings",
        "methodology",
    ]


def test_wordpress_navigation_targets_are_resolvable_and_provisioned() -> None:
    shortcodes_source = SHORTCODES_PATH.read_text(encoding="utf-8")
    rest_source = REST_PROVISION_PATH.read_text(encoding="utf-8")
    shell_source = SHELL_PROVISION_PATH.read_text(encoding="utf-8")

    for target, slug in (("signals", "signals"), ("briefings", "briefings")):
        assert (
            f"'{target}' => $this->post_type_archive_url(Post_Type::"
            in shortcodes_source
        )
        assert f'title="{target.title()}", slug="{slug}"' in rest_source
        assert f'"{target.title()}|{slug}"' in shell_source

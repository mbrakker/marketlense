import re
from types import SimpleNamespace


def _source_reading(request):
    return SimpleNamespace(
        parsed_json={
            "status": "read",
            "pages": [
                {
                    "physical_page": int(match.group(1)) + 1,
                    "observations": [
                        "The source page visibly records a relevant finding."
                    ],
                    "uncertainties": [],
                }
                for path in request.image_paths
                for match in [re.search(r"page-(\d+)\.png$", path)]
                if match is not None
            ],
        },
        request_id="source-reading",
        model=request.model,
    )

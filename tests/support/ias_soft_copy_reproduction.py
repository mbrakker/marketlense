"""Provider-safe current-schema IAS reproduction inputs."""

from __future__ import annotations

IAS_UNSUPPORTED_SOFT_COPY_CLAIMS = (
    (
        "expert_comment",
        "UK media leaders are concentrating budgets in digital video and social, "
        "with 87% naming digital video as a primary format for 2026 while social "
        "remains the top digital environment.",
        "unsupported_budget_concentration",
    ),
    (
        "expert_comment",
        "Expect planning to tilt toward adjacency-first controls inside video and "
        "social activation.",
        "unsupported_prediction",
    ),
    (
        "expert_comment",
        "Generative AI intensifies this tension.",
        "invented_genai_causality",
    ),
    (
        "expert_comment",
        "Governance should codify gen-AI adjacency policies and apply consistent "
        "quality controls across buying and optimization workflows.",
        "unsupported_adjacency_recommendation",
    ),
    (
        "expert_comment",
        "CTV and retail media are scaling, but performance will hinge on attention "
        "and safety controls.",
        "unsupported_ctv_retail_media_performance_or_causality",
    ),
    (
        "expert_comment",
        "Operating models should elevate attention measurement and suitability "
        "governance to the same level as reach, with supply decisions anchored in "
        "these thresholds.",
        "unsupported_attention_measurement_prescription",
    ),
    (
        "linkedin_post",
        "Digital video is set to lead the UK market in 2026, but performance will "
        "hinge on tighter quality controls across AI, CTV, social, and retail media "
        "to protect attention, suitability, and safety.",
        "unsupported_linkedin_performance_claim",
    ),
)


def ias_soft_copy_payload(
    family: str, *, repaired: bool, repaired_expert_comment: str
) -> dict[str, object]:
    """Return current-schema IAS reproduction output for one soft-copy family."""

    if repaired:
        claims = {
            "expert_comment": repaired_expert_comment,
            "linkedin_post": "Read the report as an input to planning.",
        }
        return {
            family: claims[family],
            "claim_provenance": [
                {
                    "claim": claims[family],
                    "classification": "recommendation",
                    "evidence_ids": [],
                }
            ],
        }

    entries = [
        claim
        for claim_family, claim, _code in IAS_UNSUPPORTED_SOFT_COPY_CLAIMS
        if claim_family == family
    ]
    return {
        family: " ".join(entries),
        "claim_provenance": [
            {
                "claim": claim,
                "classification": (
                    "recommendation"
                    if claim.startswith("Governance should")
                    or claim.startswith("Operating models should")
                    else "factual"
                ),
                "evidence_ids": ["market-demand"],
            }
            for claim in entries
        ],
    }

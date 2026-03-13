from __future__ import annotations

from src.generators.evidence_packs.base import EvidencePackStrategy
from src.generators.evidence_packs.contradictions_strategy import (
    CONTRADICTIONS_STRATEGY,
)
from src.generators.evidence_packs.doc_map_strategy import DOC_MAP_STRATEGY
from src.generators.evidence_packs.findings_strategy import FINDINGS_STRATEGY
from src.generators.evidence_packs.key_metrics_strategy import KEY_METRICS_STRATEGY
from src.generators.evidence_packs.limitations_strategy import LIMITATIONS_STRATEGY
from src.generators.evidence_packs.methods_strategy import METHODS_STRATEGY
from src.generators.evidence_packs.quote_candidates_strategy import (
    QUOTE_CANDIDATES_STRATEGY,
)
from src.generators.evidence_packs.recommendations_strategy import (
    RECOMMENDATIONS_STRATEGY,
)
from src.generators.evidence_packs.risk_register_strategy import (
    RISK_REGISTER_STRATEGY,
)
from src.generators.evidence_packs.scope_strategy import SCOPE_STRATEGY

DEFAULT_PACK_REGISTRY: tuple[str, ...] = (
    "doc_map",
    "scope",
    "methods",
    "findings",
    "limitations",
    "quote_candidates",
)

VARIETY_PACKS: tuple[str, ...] = (
    "key_metrics",
    "risk_register",
    "recommendations",
    "contradictions",
)

PACK_STRATEGIES: dict[str, EvidencePackStrategy] = {
    strategy.pack_name: strategy
    for strategy in (
        DOC_MAP_STRATEGY,
        SCOPE_STRATEGY,
        METHODS_STRATEGY,
        FINDINGS_STRATEGY,
        LIMITATIONS_STRATEGY,
        QUOTE_CANDIDATES_STRATEGY,
        KEY_METRICS_STRATEGY,
        RISK_REGISTER_STRATEGY,
        RECOMMENDATIONS_STRATEGY,
        CONTRADICTIONS_STRATEGY,
    )
}

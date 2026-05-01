from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .routing import PublisherInventoryRecoveryRecipe
from .settings import PublisherInventorySettings

@dataclass(frozen=True)
class PublisherInventoryCandidateScreeningItem:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory candidate-screening item schema version."}
    )
    canonical_url: str = field(
        metadata={
            "doc": "Normalized candidate URL under review for future download persistence."
        }
    )
    title: str = field(metadata={"doc": "Normalized candidate title under review."})
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where the candidate was found."
        }
    )
    source_page_url: str = field(
        metadata={"doc": "Inventory page URL where the candidate was found."}
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateScreeningDecision:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory candidate-screening decision schema version."
        }
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL that was screened."}
    )
    accepted: bool = field(
        metadata={
            "doc": "Whether the candidate is a meaningful report-like asset that should be queued for future download."
        }
    )
    reason: str = field(
        metadata={
            "doc": "Short human-readable reason explaining the screening decision."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateScreeningRequest:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory candidate-screening request schema version."
        }
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports database."}
    )
    insights_url: str = field(
        metadata={
            "doc": "Publisher insights URL whose new diff items are being screened."
        }
    )
    candidates: List[PublisherInventoryCandidateScreeningItem] = field(
        metadata={
            "doc": "New diff candidates to evaluate before persistence into report_sources."
        }
    )
    settings: PublisherInventorySettings = field(
        metadata={
            "doc": "Loaded publisher inventory discovery settings including candidate-screening configuration."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateScreeningResponse:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory candidate-screening response schema version."
        }
    )
    approved_items: List[PublisherInventoryCandidateScreeningItem] = field(
        metadata={"doc": "Candidates accepted for future download persistence."}
    )
    rejected_items: List[PublisherInventoryCandidateScreeningItem] = field(
        metadata={"doc": "Candidates rejected by the LLM screening step."}
    )
    decisions: List[PublisherInventoryCandidateScreeningDecision] = field(
        metadata={
            "doc": "Full screening decision set returned for all reviewed candidates."
        }
    )
    model: str = field(
        metadata={"doc": "Resolved OpenAI model ID used for candidate screening."}
    )
    request_id: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Provider request identifier for the screening call, if available."
        },
    )
    raw_response: str = field(
        default="",
        metadata={
            "doc": "Raw model response text returned by the candidate-screening call."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryLandingPageInspectionItem:
    schema_version: str = field(
        metadata={"doc": "Landing-page inspection item schema version."}
    )
    canonical_url: str = field(
        metadata={
            "doc": "Normalized candidate URL whose destination page should be inspected."
        }
    )
    title: str = field(
        metadata={
            "doc": "Current normalized candidate title carried into landing-page inspection."
        }
    )
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where the candidate was found."
        }
    )
    source_page_url: str = field(
        metadata={"doc": "Inventory page URL where the candidate was found."}
    )


@dataclass(frozen=True)
class PublisherInventoryLandingPageInspectionRequest:
    schema_version: str = field(
        metadata={"doc": "Landing-page inspection request schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name for logging and inspection context."}
    )
    items: List[PublisherInventoryLandingPageInspectionItem] = field(
        metadata={
            "doc": "Candidate landing pages that should be fetched and inspected."
        }
    )
    timeout_seconds: float = field(
        metadata={
            "doc": "Per-request HTTP timeout in seconds used for landing-page inspection fetches."
        }
    )
    max_workers: int = field(
        metadata={
            "doc": "Maximum concurrent fetch workers used for landing-page inspection."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryLandingPageObservation:
    schema_version: str = field(
        metadata={"doc": "Landing-page observation schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL that was inspected."}
    )
    source_title: str = field(
        metadata={"doc": "Candidate title before landing-page qualification."}
    )
    final_url: str = field(
        metadata={"doc": "Final URL after redirects during landing-page inspection."}
    )
    final_title: str = field(
        metadata={
            "doc": "HTML <title> text extracted from the landing page when available."
        }
    )
    h1_title: str = field(
        metadata={
            "doc": "First H1 text extracted from the landing page when available."
        }
    )
    og_title: str = field(
        metadata={
            "doc": "Open Graph title extracted from the landing page when available."
        }
    )
    http_status_code: Optional[int] = field(
        default=None,
        metadata={
            "doc": "HTTP status code observed for the landing page when available."
        },
    )
    content_type: str = field(
        default="",
        metadata={
            "doc": "Observed response Content-Type header for the landing page fetch."
        },
    )
    fetch_error: str = field(
        default="",
        metadata={
            "doc": "Short fetch error message when the landing page could not be retrieved successfully."
        },
    )
    is_pdf: bool = field(
        default=False,
        metadata={
            "doc": "Whether the inspected target resolved to a direct PDF/document asset."
        },
    )
    has_asset_type_term: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page URL/title/content contains report-like asset type terms."
        },
    )
    has_download_language: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page includes strong download/access/get-report language."
        },
    )
    has_gated_form: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page includes a form likely used to access the asset."
        },
    )
    has_document_structure: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page exposes report-like document structure such as contents, methodology, or findings."
        },
    )
    has_price_or_purchase: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page exposes report product signals such as price, buy, or add-to-cart."
        },
    )
    has_print_language: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page includes print/printable/read-report language consistent with a document asset."
        },
    )
    has_editorial_url_pattern: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page URL matches common blog/news/article/editorial path patterns."
        },
    )
    has_editorial_markers: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page content exposes blog/article/news style markers."
        },
    )
    has_related_posts: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page prominently exposes related-post/article recommendations."
        },
    )
    has_newsletter_cta: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page prominently exposes newsletter signup CTAs."
        },
    )
    has_contact_sales_cta: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page prominently exposes contact-sales or demo-booking CTAs."
        },
    )
    has_dead_page_marker: bool = field(
        default=False,
        metadata={
            "doc": "Whether the landing page looks missing, 404, or otherwise dead."
        },
    )
    verification_class: str = field(
        default="verified",
        metadata={
            "doc": "Deterministic landing-page verification class: verified, dead, challenge, transient_fetch_failure, protected_document, or weak_signal_html."
        },
    )
    recovery_eligible: bool = field(
        default=False,
        metadata={
            "doc": "Whether this observation is eligible for orchestrator-owned deferred recovery instead of immediate hard rejection."
        },
    )
    source_surface_class: str = field(
        default="unknown",
        metadata={
            "doc": "Deterministic surface class inferred from the candidate/source route: archive_feed, direct_detail, mixed_content_hub, service_membership, research_hub, or unknown."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryLandingPageInspectionResponse:
    schema_version: str = field(
        metadata={"doc": "Landing-page inspection response schema version."}
    )
    observations: List[PublisherInventoryLandingPageObservation] = field(
        metadata={
            "doc": "Landing-page observations returned for the inspected candidate set."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryQualifiedCandidateItem:
    schema_version: str = field(
        metadata={"doc": "Qualified candidate item schema version."}
    )
    canonical_url: str = field(
        metadata={
            "doc": "Normalized candidate URL approved or rejected by the landing-page quality check."
        }
    )
    title: str = field(
        metadata={
            "doc": "Resolved report-like title used after landing-page qualification."
        }
    )
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where the candidate was found."
        }
    )
    source_page_url: str = field(
        metadata={"doc": "Inventory page URL where the candidate was found."}
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateQualityDecision:
    schema_version: str = field(
        metadata={"doc": "Candidate landing-page quality decision schema version."}
    )
    canonical_url: str = field(
        metadata={
            "doc": "Normalized candidate URL evaluated by the landing-page quality check."
        }
    )
    accepted: bool = field(
        metadata={
            "doc": "Whether the landing page qualifies as a report-like asset worth queueing for download."
        }
    )
    reason: str = field(
        metadata={
            "doc": "Short human-readable reason explaining the landing-page quality decision."
        }
    )
    resolved_title: str = field(
        metadata={
            "doc": "Best resolved title chosen from the candidate and landing-page metadata."
        }
    )
    source_surface_class: str = field(
        default="unknown",
        metadata={
            "doc": "Deterministic surface class inferred for the candidate landing page."
        },
    )
    recovery_recipe: Optional["PublisherInventoryRecoveryRecipe"] = field(
        default=None,
        metadata={
            "doc": "Optional deferred recovery recipe attached only to strong candidates rejected for recoverable verification failures."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateQualityRequest:
    schema_version: str = field(
        metadata={"doc": "Candidate landing-page quality-check request schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports database."}
    )
    insights_url: str = field(
        metadata={
            "doc": "Publisher insights URL whose already-screened candidates are being qualified."
        }
    )
    candidates: List[PublisherInventoryCandidateScreeningItem] = field(
        metadata={
            "doc": "Candidates already accepted by the LLM screening stage and pending final landing-page quality qualification."
        }
    )
    settings: PublisherInventorySettings = field(
        metadata={
            "doc": "Loaded publisher inventory discovery settings including quality-check configuration."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateQualityResponse:
    schema_version: str = field(
        metadata={
            "doc": "Candidate landing-page quality-check response schema version."
        }
    )
    approved_items: List[PublisherInventoryQualifiedCandidateItem] = field(
        metadata={
            "doc": "Candidates accepted for report_sources persistence after landing-page qualification."
        }
    )
    rejected_items: List[PublisherInventoryQualifiedCandidateItem] = field(
        metadata={"doc": "Candidates rejected by the landing-page quality check."}
    )
    decisions: List[PublisherInventoryCandidateQualityDecision] = field(
        metadata={
            "doc": "Full landing-page quality decision set returned for all reviewed candidates."
        }
    )


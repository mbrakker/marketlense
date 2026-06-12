from __future__ import annotations

from src.contracts.analytics_projection import (
    ReportClaimProjection,
    ReportFigureProjection,
    ReportFindingProjection,
    ReportMetricProjection,
    ReportQuoteProjection,
    ReportSectionProjection,
)

def _report_summary_text(
    *,
    title: str,
    publisher: str,
    tldr: str,
    executive_summary: str,
    category_ids: list[str],
    taxonomy: list[str],
) -> str:
    parts = [
        f"Title: {title}",
        f"Publisher: {publisher}" if publisher else "",
        f"TLDR: {tldr}" if tldr else "",
        f"Executive summary: {executive_summary}" if executive_summary else "",
        f"Categories: {', '.join(category_ids)}" if category_ids else "",
        f"Taxonomy: {', '.join(taxonomy)}" if taxonomy else "",
    ]
    return "\n".join(part for part in parts if part)

def _section_text(section: ReportSectionProjection) -> str:
    parts = [
        f"Title: {section.title}",
        f"Summary: {section.summary}" if section.summary else "",
    ]
    if section.key_points:
        parts.append("Key points: " + "; ".join(section.key_points))
    return "\n".join(part for part in parts if part)

def _finding_text(finding: ReportFindingProjection) -> str:
    parts = [f"Finding: {finding.text}"]
    if finding.evidence:
        parts.append(f"Evidence: {finding.evidence}")
    if finding.confidence:
        parts.append(f"Confidence: {finding.confidence}")
    return "\n".join(parts)

def _metric_text(metric: ReportMetricProjection) -> str:
    value_parts = [metric.value]
    if metric.unit:
        value_parts.append(metric.unit)
    parts = [
        f"Metric: {metric.metric}",
        "Value: " + " ".join(value_parts).strip(),
    ]
    if metric.evidence_id:
        parts.append(f"Evidence ID: {metric.evidence_id}")
    return "\n".join(parts)

def _quote_text(quote: ReportQuoteProjection) -> str:
    parts = [f"Quote: {quote.text}"]
    if quote.speaker:
        parts.append(f"Speaker: {quote.speaker}")
    if quote.citation:
        parts.append(f"Citation: {quote.citation}")
    return "\n".join(parts)

def _claim_text(claim: ReportClaimProjection) -> str:
    parts = [f"Claim: {claim.claim}"]
    if claim.evidence:
        parts.append(f"Evidence: {claim.evidence}")
    return "\n".join(parts)

def _figure_text(figure: ReportFigureProjection) -> str:
    caption = (
        figure.display_caption
        or figure.generated_caption
        or figure.detected_caption
        or figure.image_path
    )
    parts = [f"Figure caption: {caption}"]
    if figure.kind:
        parts.append(f"Figure kind: {figure.kind}")
    return "\n".join(parts)

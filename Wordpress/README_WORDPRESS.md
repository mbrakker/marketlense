WordPress Rendering Layer
Market Lense – Presentation & Distribution Module

This directory contains the WordPress Rendering Layer of Market Lense.

It is responsible for:

Rendering validated Insight Artifacts into a premium web experience

Preserving publishing contracts defined in the pipeline

Enforcing idempotent ingestion

Maintaining schema integrity between extraction and display

Providing deterministic deployment and local reproducibility

The WordPress layer does not perform extraction, transformation, or validation logic.
It consumes structured artifacts produced by the pipeline.

Architectural Role Within Market Lense
Ingestion → Extraction → Structuring → Validation → Artifact Contract
                                                       ↓
                                             WordPress Rendering Layer
                                                       ↓
                                                Public Distribution
Responsibilities
Layer	Responsibility
Pipeline	Generate structured Insight Artifact
Contract	Define canonical schema
WordPress Plugin	Persist artifact in WP data model
WordPress Theme	Render artifact using design system
WordPress Core	Routing, REST, editor, block system
Design Principles (Aligned with Pipeline Guardrails)
1. Contract-Driven Rendering

WordPress must never assume structure implicitly.

All rendering depends on:

Explicit post meta fields

Explicit taxonomy assignments

Explicit section hierarchy in artifact

If the artifact changes, the contract must be updated before theme adjustments.

2. Idempotent Publishing

Publishing must be:

Deterministic

Re-runnable without duplication

Upsert-based (via ml_doc_id or equivalent unique key)

No manual reconciliation logic inside theme templates.

3. Strict Separation of Concerns
Component	Owns
marketlense-core plugin	Data model
marketlense theme	Visual system
Docker stack	Runtime
Pipeline	Artifact creation

Theme must never:

Register post types

Register taxonomies

Contain ingestion logic

Plugin must never:

Contain layout logic

Hardcode visual markup

Directory Structure
Wordpress/
│
├── docker-compose.yml
├── .env.example
│
├── wp-content/
│   ├── themes/
│   │   └── marketlense/
│   │
│   └── plugins/
│       └── marketlense-core/
│
└── scripts/
    ├── install.sh
    ├── reset.sh
    ├── smoke-test.sh
Runtime Environment
Reproducible Local Stack

WordPress

MySQL

phpMyAdmin

WP-CLI

Environment variables are defined in .env.

Start
docker compose --env-file Wordpress/.env -f Wordpress/docker-compose.yml up -d
Stop
docker compose --env-file Wordpress/.env -f Wordpress/docker-compose.yml down
Clean Reset
docker compose --env-file Wordpress/.env -f Wordpress/docker-compose.yml down -v
Data Model (Plugin Layer)

Plugin: marketlense-core

Defines the canonical WordPress representation of the Insight Artifact.

Custom Post Type

ml_report

Represents one structured Insight Artifact.

Supports:

title

editor

excerpt

thumbnail

revisions

REST-enabled.

Taxonomies
Taxonomy	Purpose
ml_topic	Strategic domain classification
ml_publisher	Source authority
ml_region	Geographic scope
ml_channel	Channel classification
Post Meta (Schema Surface)
Meta Key	Description
ml_doc_id	Unique idempotency key
ml_source_url	Original report URL
ml_time_period	Covered timeframe
ml_key_metrics	Structured metrics object
ml_validation_status	Pipeline QA state
ml_ingested_at	Timestamp

Meta must be registered with:

show_in_rest = true

explicit type

sanitize callbacks

Artifact Contract Alignment

The WordPress layer assumes:

Digest HTML contains valid heading hierarchy (H2/H3) for TOC generation

Figures are uploaded and associated as media attachments

Key metrics object is structured and JSON-valid

Taxonomies are normalized upstream

If artifact structure changes:

Contract must be updated

Plugin meta registration must be reviewed

Theme rendering must be regression-tested

Theme Layer – Presentation System

Theme: marketlense

Type: Full Site Editing (Block Theme)

Design System

Defined in theme.json:

Typography scale

Spacing system

Color tokens

Radius and shadow presets

Global element styling

Design objectives:

High-density insight presentation

Editorial clarity

Executive-grade typography

Minimal visual noise

Strong content hierarchy

Accessible contrast

Performance-first rendering

Layout Architecture
Single Report (single-ml_report.html)

Desktop:

Left: Sticky TOC

Center: Digest content

Right: Insight rail (metrics + metadata)

Mobile:

Stacked layout

Collapsible TOC

Archive / Discovery Pages

Query Loop block

Structured report cards

Taxonomy chips

Publisher + timeframe metadata

No arbitrary filtering logic outside WP-native capabilities

Static Pages (Provisioned on Activation)

Created idempotently via plugin activation hook.

Core Platform Pages

Home

Topics

Publishers

About Market Lense

Methodology

Submit a Report

Contact

Privacy Policy

Terms of Use

Page Strategy
Page Type	Rendering Strategy
Home	Template-driven (Query Loop)
Topics	Taxonomy-driven
Publishers	Taxonomy-driven
About	Content-seeded
Methodology	Content-seeded
Legal	Content-seeded
Guardrails
Must Not

Change CPT slug post-production

Rename meta keys without migration

Store secrets in theme/plugin

Embed business logic in templates

Modify artifact structure in WordPress

Must

Maintain backward compatibility

Preserve URL stability

Ensure idempotent page creation

Validate meta registration after schema changes

Test on clean install before release

Testing Strategy
Development Loop
code → reload → verify → repeat
Deterministic Reset Test

Full environment reset

Activate plugin

Activate theme

Validate:

CPT exists

Taxonomies registered

Meta visible in REST

Pages created once

Homepage set

No PHP warnings

Templates render correctly

Release Packaging

Deliverables:

marketlense.zip (theme only)

marketlense-core.zip (plugin only)

ZIP must contain root folder.

Governance Model

WordPress layer is downstream of contract.

Schema changes require coordinated update.

Visual changes must not alter artifact assumptions.

Publishing interface must remain stable.
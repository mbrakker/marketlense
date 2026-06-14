# Effort-Under-Four Simplification Design

**Status:** Approved on 2026-06-13

**Goal:** Resolve every `simplification.md` item scored below effort 4 by
implementing the smallest production-quality shared changes, closing items
already proved complete, and documenting evidence-based keep rationales for
investigation items that cannot be removed safely.

## Scope Rules

- Effort 1, 2, and 3 entries are in scope.
- Overlapping entries are implemented once through the existing semantic owner.
- Existing public facades and canonical service boundaries remain stable.
- Investigation entries may remain open only when current repository or live
  evidence cannot prove safe removal. Each retained entry records the evidence,
  risk, owner, and next review date.
- No new deployable component is introduced.
- No production behavior changes are bundled into movement-only helper reuse.
- Tests use real primary logic and mock only true external boundaries.

## Baseline And Targets

| Area | Baseline | Target |
| --- | --- | --- |
| OpenAI facade runtime synchronization | One mutable synchronization call before every provider operation | Zero runtime child-module mutation |
| Vector-store credential ownership | Direct `OPENAI_API_KEY` environment read in vector-store service | Canonical OpenAI credential resolver |
| Generator filesystem/media I/O | Render, evidence, dashboard, publish paths contain direct parsing or binary transforms | Service-owned I/O/transforms with typed contracts |
| Duplicate pure helpers | Repeated normalization, ordered dedupe, JSON, SQLite, HTTP, clock, and PDF helpers | One semantic owner per identical behavior |
| UI-run request persistence | Orchestrator writes request JSON and derives persistent path | Service-owned write and shared deterministic path policy |
| Quality commands | CI checks require many separate commands | One local quality command plus focused refactor audit |
| Architecture drift checks | Direct-I/O check exists only as a pytest test; no provider-boundary map | CI-callable gates with owner/expiry allowlists |
| WordPress administration | Multiple user-facing REST scripts | One subcommand CLI; old scripts delegate for compatibility |

## Architecture

### Provider And Configuration

`openai_service.py` remains the canonical provider facade. Its private modules
use dependencies owned by their semantic modules; the facade no longer copies
mutable globals into them. A public provider-dependency contract supports
explicit fake-client injection in tests without private-helper patching.

OpenAI credential resolution is exposed once through the existing configuration
service boundary and reused by vector-store operations. Missing credentials
remain typed and sanitized.

### File, Cache, Dashboard, Media, And UI-Run Services

Existing `file_service`, `file_cache_service`, render service, and UI-run
services gain focused contract operations. Generators consume typed results and
retain only domain decisions:

- render cache resolution and template-bundle hashing;
- JSON/evidence-pack loading;
- bounded log tails and JSON payload reads;
- image upload preparation;
- worker request persistence and run-state path derivation.

No pass-through service is added where an existing owner fits.

### Shared Pure Internals

Identical pure behavior moves to existing utility or private service-common
modules. Helpers remain narrow:

- text normalization and ordered uniqueness;
- deterministic JSON serialization;
- SQLite metadata/connection/lock behavior;
- HTTP pool-key derivation;
- contract required-field semantics;
- UTC clock formatting;
- PDF parallel chunking/reason tally and candidate score helpers.

Call sites with intentionally different semantics remain local and are
documented rather than forced into a generic abstraction.

### Tooling And WordPress

Repository quality tooling gains:

- `scripts/quality_gate.py` as the canonical local CI-equivalent command;
- `scripts/refactor_audit.py` for movement/refactor checks;
- CI-callable role-mixing/direct-I/O and provider-boundary checks;
- documented intake-to-active-backlog promotion rules.

WordPress REST administration gains one CLI with `provision`, `seed-homepages`,
and `sync-profiles` subcommands. Existing script names remain compatibility
launchers during this change.

CSS and legacy compatibility are removed only when static inventory plus runtime
evidence proves they are unused. Otherwise their keep rationale remains open.

## Error Handling And Logging

- New service operations raise typed `AppError` values with code, retryability,
  severity, and sanitized context.
- Service entry/exit and failure events include the required run/task/span,
  role, module, and event fields.
- Cleanup suppression records a low-severity structured event without replacing
  the original exception.
- Utility functions remain log-free.

## Testing

Each behavior change follows red-green TDD. Coverage includes:

- positive and negative provider/config paths;
- cache hit, miss, stale, invalid JSON, and I/O failure;
- bounded log reads and grouped directory counts;
- media no-op, optimized, decode failure, and not-smaller fallback;
- UI-run persistence success, failure, and deterministic path/idempotency;
- pure helper equivalence and non-string edge cases used by current callers;
- SQLite and HTTP transport semantics;
- PDF fixture parity;
- quality/architecture gate failure fixtures;
- WordPress CLI routing and dry-run-compatible behavior.

After focused suites, run formatting, typing, architecture, WordPress, full
pytest/coverage, mutation, schema, and prompt-corpus gates.

## Live Verification

Use existing repository artifacts only:

1. Run report rendering twice against an existing generated report to prove
   miss/write then hit behavior without output drift.
2. Load existing logs and output trees through the dashboard read model and
   compare bounded counts/events.
3. Run a real existing PDF through affected candidate extraction and compare
   candidate artifacts.
4. Run a configured OpenAI smoke call and vector-store status-capable path when
   credentials and an existing project vector-store ID are available.
5. Exercise the WordPress CLI against the configured site in read/verification
   mode before any mutating operation; mutations are performed only by existing
   idempotent commands.

Any failure is investigated at the failing boundary, fixed with a regression
test, and rerun.

## Backlog Disposition

Completed implementation items are removed from `simplification.md` and from any
overlapping active entry in `CONSOLIDATED_TODO.md`. Evidence-only closures are
listed under the closed section. Retained investigations include:

- exact evidence checked;
- why removal is unsafe now;
- operational risk;
- owner (`repository maintainers` unless a narrower owner exists);
- next review date (`2026-09-13` by default).


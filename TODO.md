# TODO

1. Upgrade validator to perform semantic comparisons (reduce word-by-word false positives).
2. Upgrade all prompts.
3. Parallelize report processing.
4. Make GPT model selection flexible per prompt call.
5. Combine redundant services to reduce excessive service proliferation.
6. Update `AGENTS.md`:
Service scope enforcement (add to Services section):

One service = one external system/task. All interactions with the same external system (e.g., PDF file I/O via pypdf/fitz) must live in a single service module. Do not split identical external dependencies across multiple services.

No thin wrappers. Services must not exist solely to re-log and delegate to another service without adding distinct I/O or contract adaptation.

Shared dependency consolidation. When multiple functions share the same external handle (e.g., PDF readers), the service must centralize resource management, error taxonomy, and logging in one place, exposing top-level functions for each operation (e.g., context build, text extract, metadata extract).

Contract-bound API. Each service function must use explicit request/response dataclasses and must validate inputs/outputs; reuse the same contract set for related operations on the same external system.
7. Add cost tables.
8. Add vector store logging to avoid recreating entries.
9. Add categories/tags to vector store records.
10. Create a GUI.
11. Add vector store deletion support.
12. Define and enforce cost limits.
13. Refine HTML and deduplicate repeated blocks.

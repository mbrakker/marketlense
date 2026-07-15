# External System Boundaries

> **Documentation type:** Architectural
> **Canonical topic:** External-system boundaries
> **Update trigger:** Provider ownership, canonical service entrypoint, or I/O policy changes.

Each external system has one canonical service boundary. Callers use the public service module; internal capability packages may support it without becoming competing entrypoints.

| System | Canonical service |
| --- | --- |
| LLM providers | `src/services/llm_service.py` |
| Google Drive | `src/services/drive_service.py` |
| Browser report acquisition | `src/services/browser_report_download_service.py` |
| Mailbox acquisition | `src/services/mailbox_acquisition_service.py` |
| WordPress | `src/services/wordpress_service.py` |
| Filesystem | `src/services/file_service.py` |
| Report/state persistence | `src/services/report_store_service.py` and `src/services/state_service.py` |

Prompt loading and rendering belongs to `src/services/prompt_service.py`. WordPress receives validated publication payloads; it is not an intelligence-generation boundary. The enforced source of truth is [`docs/quality/architecture_policy.yaml`](../quality/architecture_policy.yaml).

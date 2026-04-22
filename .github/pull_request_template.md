## Summary

- 

## Validation

- [ ] `python -m pytest -q`
- [ ] Relevant smoke/live run completed or explicitly not applicable

## Architecture Checklist

- [ ] Contracts use dataclasses with documented fields and `schema_version`.
- [ ] Services contain only external I/O boundary logic.
- [ ] Generators contain domain logic and do not perform direct I/O.
- [ ] Orchestrators own sequencing, retries, idempotency, and state transitions.
- [ ] Prompt text remains in prompt namespaces and is loaded through prompt service.
- [ ] Logs include `run_id`, `task_id`, `span_id`, `module`, `role`, and `event`.
- [ ] Tests assert observable behavior without patching internal/private logic.

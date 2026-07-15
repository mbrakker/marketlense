# Operator Cockpit

> **Documentation type:** Current reference
> **Canonical topic:** Operator cockpit
> **Update trigger:** Streamlit navigation, run-control, or configuration-management changes.

The Streamlit cockpit is the operator and administrator surface. Its entrypoint is `src/streamlit_app.py`; the UI reads service-backed data and dispatches workflows through orchestrators rather than duplicating domain logic in pages.

It covers workflow launch and run control, report and validation inspection, acquisition operations, publishing and taxonomy controls, cost and log views, and structured configuration editing. Long-running UI actions use the persisted run registry and can be inspected, cancelled, retried, or handled as dead letters.

Run it with `streamlit run src/streamlit_app.py`. The cockpit is not public portal navigation; public WordPress behavior is documented in [README_WORDPRESS.md](../../README_WORDPRESS.md).

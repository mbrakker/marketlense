# Report Discovery

> **Documentation type:** Current reference
> **Canonical topic:** Report discovery workflow
> **Update trigger:** Publisher inventory, source eligibility, or discovery persistence changes.

Publisher discovery identifies candidate report sources and persists normalized source and publisher context. A discovered source is not a Report: it becomes one only after acquisition, processing, validation, and artifact generation succeed.

Use `python -m src.cli discover-publisher-inventory <publisher-url>` for the CLI workflow. Discovery configuration is in `publisher_discovery`; source records and route information are retained in the reports database. See [configuration](../ops/configuration.md) and [report acquisition](report-acquisition.md).

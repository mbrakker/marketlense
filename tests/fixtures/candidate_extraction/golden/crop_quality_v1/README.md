# Retained crop-quality golden corpus v1

This is the project-retained crop/candidate corpus copied from the approved local
benchmark on 2026-07-13. It is intentionally versioned under the existing
candidate-extraction golden-fixture namespace so changes are reviewable and
hash-verifiable in CI.

- Reports: 9
- Candidate records: 438
- Crop images: 438
- Crop-image aggregate SHA-256: `dcccfb61091635f52e97d13e2f6d028258ccd7ba20a334aedce486e3d3f2c171`

The corpus contains candidate packs and rendered crop images. It does not contain
source PDFs or `crop_refine.json` outputs, so it is not a substitute for the
separate PDF-extraction and crop-refinement benchmark corpora.

`manifest.json` preserves source-run metadata. The portable paths used for crop
verification are the per-report `candidates/candidates.json` packs and their
relative `crop_path` entries.

# HTML TODO

Last reviewed: 2026-02-13

## Remaining items (non-template scope)

1. Wire real image dimensions from generation output into template context.
   - Current template now sets explicit `width`/`height` defaults to reduce CLS.
   - Follow-up should pass actual dimensions from the image generation/render pipeline for exact layout reservation.
2. Complete responsive image pipeline for true Core Web Vitals gains.
   - Generate and persist responsive variants (for example: `webp` + multiple widths).
   - Expose those variants to HTML rendering so `srcset`/`sizes` pick smaller assets on mobile.
3. Externalize shared HTML stylesheet for cache reuse (if publish path supports static asset hosting).
   - Current template keeps styles inline for self-contained portability.
   - Follow-up should move stable CSS to a shared file and keep only critical CSS inline.

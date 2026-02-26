# WordPress Subproject (Current State)

This document reflects the actual WordPress scope in this repository.

## Scope

`Wordpress/` currently contains only the WordPress theme source used by Market Lense publishing outputs.

- No Docker runtime is maintained in this folder.
- No plugin/CPT layer is maintained in this folder.

## Current Structure

Existing files:

- `Wordpress/.gitignore`
- `Wordpress/README_WORDPRESS.md`
- `Wordpress/wp-content/themes/marketlense-theme/*`

Theme type:

- Classic theme scaffold (PHP templates + CSS)

Core files:

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `index.php`
- `template-parts/content.php`
- `style.css`
- `assets/css/main.css`

## Not Included

These are intentionally not present right now:

- Docker Compose stack
- `Wordpress/.env.example`
- WordPress plugin code (`wp-content/plugins/marketlense-core/`)
- `theme.json`
- `single-ml_report.html`
- `Wordpress/scripts/*`

## Environment Strategy

Use the root project `.env` (`c:\Programing\Market lense\.env`) as the single source for publish-related configuration.

Relevant keys:

- `WP_SITE_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD` (or `WP_BEARER_TOKEN`)

Do not maintain a separate WordPress-only `.env` in this subproject unless you explicitly need one.

## Pipeline Integration

Publishing is handled by Python code in `src/` and targets a WordPress site over REST.

Commands:

```powershell
python -m src.cli publish-wp
python -m src.cli update-wp-categories
```

Current behavior:

- Publishes to standard WordPress posts endpoint.
- Uploads report images to WordPress media.
- Records publish state (`file_id -> wp_post_id/wp_post_url`) in the pipeline state DB.

## Maintenance Rule

If you add runtime tooling (local WordPress server, plugin layer, scripts), update this file and root `README.md` in the same commit.

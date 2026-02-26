# WordPress Theme Development Environment

This folder provides a local WordPress stack and a native WordPress theme scaffold for Market Lense.

## What is included

- `docker-compose.yml`: WordPress + MySQL + phpMyAdmin local stack.
- `.env.example`: environment variables template.
- `wp-content/themes/marketlense-theme`: starter classic theme using WordPress-native template hierarchy and APIs.

## Quick start

1. Create your local environment file:

   ```bash
   cp Wordpress/.env.example Wordpress/.env
   ```

2. Start the stack:

   ```bash
   docker compose --env-file Wordpress/.env -f Wordpress/docker-compose.yml up -d
   ```

3. Complete WordPress install at:

   - Site: `http://localhost:8088`
   - phpMyAdmin: `http://localhost:8089`

4. Activate the theme:

   - WP Admin -> Appearance -> Themes -> **Market Lense Theme** -> Activate

## Theme architecture

The scaffold follows WordPress native conventions:

- `style.css`: theme metadata + global CSS entrypoint.
- `functions.php`: theme setup (`add_theme_support`, menu registration, enqueueing).
- `index.php`: fallback template and post loop.
- `front-page.php`: static front-page template.
- `header.php` / `footer.php`: global layout.
- `template-parts/content.php`: reusable post snippet.

## Development notes

- Prefer WordPress-native features first: template hierarchy, block editor, `theme.json`, `add_theme_support`, and enqueue APIs.
- Keep custom logic in theme files only when needed; use WordPress hooks/actions/filters for extensibility.
- Do not store secrets in committed files; keep credentials in `Wordpress/.env`.

## Useful commands

Start:

```bash
docker compose --env-file Wordpress/.env -f Wordpress/docker-compose.yml up -d
```

Stop:

```bash
docker compose --env-file Wordpress/.env -f Wordpress/docker-compose.yml down
```

Stop and remove DB volume (clean reset):

```bash
docker compose --env-file Wordpress/.env -f Wordpress/docker-compose.yml down -v
```

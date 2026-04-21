Frontend lives here so the UI is grouped separately from backend code.

Structure:
- `templates/layouts`: shared Jinja layouts
- `templates/pages`: Jinja page templates
- `assets/css`: global and screen-specific stylesheets
- `assets/js`: browser JavaScript files
- `assets/images`: static UI images

Current entry points:
- Jinja templates root: `views/frontend/templates`
- Static root: `views/frontend/assets`

# AI Brief

A local AI news reader built around GeneralNewsExtractor. Fetches real RSS/Atom feeds from TechCrunch, The Verge, and MIT Technology Review. No API keys required.

## Start

From the repository directory, with Python 3.9 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m ai_news.app
```

Open http://127.0.0.1:8080 and choose **Refresh news**. Use `--port 8090` to choose another port and `--db /path/to/news.sqlite3` to choose the storage location. Stop with Ctrl+C. Restarting preserves saved stories and the article cache.

## Features

- Concurrent feed collection with timeouts, size limits, and per-source status.
- AI relevance filtering and automatic topic classification.
- Source excerpts, publication dates, and links to original reporting.
- Search across titles, excerpts, topics, and publishers; filter by source or topic.
- Persistent saved reading list and URL deduplication, including removal of common tracking parameters.
- Responsive interface, keyboard-accessible controls, and explicit empty/error states.

## How the model works

`ai_news/model.py` implements a deterministic baseline, not a trained neural model. AI relevance uses whole-word terms; topic classification scores keyword matches, weighting titles twice. The highest score wins, with “AI overview” as the fallback. It can miss implicit AI stories and misclassify ambiguous mentions. No accuracy benchmark has been established.

GNE extracts main text from longer HTML bodies supplied by feeds. Plain-text parsing is the fallback for short descriptions or extraction failures. Excerpts use the first two sentences, capped at approximately 360 characters. They are shortened publisher text, not generated analysis or fact checking. The application does not fetch full article pages or bypass subscriptions.

Topic counts describe the accumulated local collection; they are not a measure of web-wide trends. Different publishers reporting the same event remain separate stories. Refresh is manual; there are no background notifications.

## Scope

This is a single-user local prototype. It binds to loopback only and stores one shared reading list in SQLite. Public multi-user hosting would require authentication, per-user storage, a production web server, rate limiting, and a scheduled ingestion service. Feed availability and editorial coverage depend on publishers.

Feed sources are defined in `ai_news/app.py` (`SOURCES`). Add trusted public RSS/Atom feeds there. Never treat publisher content as application instructions.

## Verification

```sh
.venv/bin/python -m unittest discover -s ai_news_tests -v
```

Tests cover RSS/Atom parsing, date normalization, relevance filtering, unsafe article URL rejection, summary handling, deduplication, saved-state persistence, and preservation of cached articles on feed failure. Live collection and browser search/save flows were also checked during development.

## Article illustrations

The 34 stories collected during the initial run have individually generated editorial illustrations. Images are original conceptual artwork made with the built-in image generation tool, not publisher photographs or evidence of events. Each card labels the artwork accordingly and provides alternative text. Images load lazily and honor reduced-motion preferences.

Assets are stored in `ai_news/static/artwork/`, keyed by stable article ID. `manifest.json` maps stories to images and alternative text; `prompts.json` preserves the exact generation prompts. Existing article artwork persists across refreshes. Newly discovered stories remain text-only until an illustration is generated and added to the manifest; this local app does not silently call a paid image-generation API.

## GitHub Pages and automatic refresh

The `Refresh and publish AI Brief` workflow builds a static version for GitHub Pages. It runs at 03:00, 07:00, 11:00, 15:00, 19:00, and 23:00 in `Europe/Dublin`, following daylight-saving changes. GitHub schedules are best-effort and can be delayed. GitHub may disable scheduled workflows in public repositories after 60 days without repository activity; check the Actions tab if updates stop.

Each run collects the configured publisher feeds, retains older stories when a source fails, keeps up to 300 recent articles, commits the public news snapshot, and deploys a Pages artifact. If every source fails, the workflow fails and the previous website stays published. Pushes to application files and manual workflow dispatch also refresh and publish.

On the public site, saved stories are stored only in the visitor's browser. **Reload news** retrieves the latest published edition; it does not start an ingestion job. The last successful edition timestamp appears above the stories. Existing generated images are included; new articles do not automatically receive generated images.

Build locally with `.venv/bin/python -m ai_news.build_site` (cached snapshot) or add `--refresh` to fetch live feeds. Output goes to `_site/`. The older `site/` landing page and its CNAME are not deployed by this workflow.

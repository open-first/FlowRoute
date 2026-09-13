# Deploy these docs

The documentation source is ordinary Markdown under `docs/`, with navigation and theme
configuration in `mkdocs.yml`. You can keep the Markdown as-is or render it to a portable
static site.

## Preview locally

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Open the local address printed by MkDocs.

## Build static files

```bash
mkdocs build --strict
```

The generated site is written to `site/`. Upload that directory to any static host.

## Common hosting targets

| Host | Build command | Publish directory |
| --- | --- | --- |
| GitHub Pages | `mkdocs build --strict` | `site` |
| GitLab Pages | `mkdocs build --strict` | `site` |
| Netlify | `mkdocs build --strict` | `site` |
| Cloudflare Pages | `mkdocs build --strict` | `site` |
| Vercel | `mkdocs build --strict` | `site` |
| Read the Docs | Install `requirements-docs.txt` | MkDocs project root |

For GitHub Pages, MkDocs also provides:

```bash
mkdocs gh-deploy
```

Run that only from the intended Git repository and branch. It creates or replaces the generated
documentation branch according to MkDocs' deployment behavior.

## Host without Material for MkDocs

Every page remains readable Markdown. If your platform has its own Markdown renderer, point it
at `docs/` and reproduce the order from `mkdocs.yml`. Material-only features such as tabbed
content and admonitions may render as plain text unless the host supports the same extensions.

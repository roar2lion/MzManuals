# ModelDocs

Manuals for the Mozambique power-system model (PLEXOS and its PyPSA benchmark). Each manual is written as JSON, and the builder turns it into a GitHub Pages site and a PDF.

## Layout

| Path | What it holds |
|---|---|
| `content/manuals/<id>.json` | One manual each (methodology, definitions, …) |
| `content/glossary.json` | Terms shared by all manuals, cited as `[[term-id]]` |
| `content/site.json` | Site title, intro, `base_url` (live address, used for links between manuals inside PDFs) |
| `content/assets/` | Figures used by manuals |
| `schema/` | JSON Schemas: editors validate and autocomplete through each file's `$schema` line |
| `builder/build.py` | Validator and renderer (site + PDF) |
| `builder/static/` | Site CSS/JS and the print stylesheet |
| `.github/workflows/pages.yml` | Validates every push or PR; builds and deploys the site and PDFs from `main` |
| `site/` | Build output (git-ignored) |

## Use

```
build.cmd                                     validate, build site\ with drafts and PDFs, open it
build.cmd --check                             validate only
python builder/build.py --new methodology "Methodology"   scaffold a new manual (starts as a draft, unpublished)
```

The PDFs are printed by a local Chrome or Edge, or by Chrome on the CI runner, so the PDF looks the same as the site, maths and diagrams included. Set `CHROME_PATH` if the browser is not in a standard place.

How to write a manual (block types, inline syntax, cross-references, glossary, publishing setup): the **Authoring Guide**, `content/manuals/authoring-guide.json`. It is built locally (`build.cmd`) and kept off the live site.

## Compared with the SPLAT-to-PyPSA manual

- **Many manuals, one builder.** The builder knows block types (text, list, table, entries, equation, callout, figure, diagram, code), not manual sections. A new manual needs no code change.
- **Checked before it is built.** A JSON Schema checks every manual, and the build also checks glossary terms, cross-references, figure files and duplicate anchors. Any problem stops the build.
- **Automatic numbering.** Sections, tables, figures and equations are numbered automatically, and cross-references follow when things move.
- **One source for HTML and PDF.** The PDF is printed from the same HTML, with a cover, a linked contents list, page numbers, a glossary appendix and the version history.
- **Shared glossary.** Terms are defined once and show their definition on hover. The glossary page lists which manuals use each term.
- **Search and draft control.** Search works offline. Drafts stay off the live site until `"publish": true`.
- **Provenance.** Each section can list the workspace files it was written from.
- **Deterministic output.** Same JSON in gives the same files out, with no build timestamps.

# ModelDocs

Manuals for the Mozambique power-system model (PLEXOS and its PyPSA benchmark). Each manual is written as JSON, and the builder turns it into a GitHub Pages site and a PDF.

## Contents

- [View the manuals](#view-the-manuals)
- [Refresh](#refresh)
  - [Local copy](#local-copy)
  - [Live site](#live-site)
- [First-time setup (once)](#first-time-setup-once)
- [Layout](#layout)
- [Use](#use)
- [Editing a manual as Markdown (e.g. with AI help)](#editing-a-manual-as-markdown-eg-with-ai-help)
- [Linking to a section (e.g. from slides)](#linking-to-a-section-eg-from-slides)
- [Compared with the SPLAT-to-PyPSA manual](#compared-with-the-splat-to-pypsa-manual)

## View the manuals

- **Live site:** <https://roar2lion.github.io/MzManuals/> (works once the repo is on GitHub, see *First-time setup* below; the PDFs are linked from each manual's page)
- **Local copy:** [site/index.html](site/index.html), created by `build.cmd`. It includes drafts and is not visible to anyone else.

## Refresh

### Local copy

To check your edits before publishing:

1. Edit the JSON in `content/`.
2. Run `build.cmd`. It validates every manual, rebuilds `site/` (drafts included) with the PDFs, and opens it in the browser. If it lists problems, fix them and run it again.

### Live site

What everyone else sees:

1. Make sure the manual has `"publish": true`; drafts with `"publish": false` stay off the live site.
2. Run `build.cmd --check` to catch problems before pushing.
3. Commit and push to `main`:
   ```
   git add -A
   git commit -m "Update methodology manual"
   git push
   ```
4. GitHub Actions rebuilds the site and PDFs and publishes them, in about 2 minutes. Progress is in the repo's *Actions* tab; a red cross there means the build found a problem and the live site was left unchanged.
5. Reload the live site. If the old version still shows, force a refresh (Ctrl+F5).

## First-time setup (once)

1. On GitHub, create an empty repository named `MzManuals` under `roar2lion`. Don't add a README, so the first push doesn't conflict. On a free GitHub account, Pages works only for a **public** repository; a private one needs GitHub Pro or a paid organisation plan, and otherwise shows a 404.
2. Connect this folder and push:
   ```
   git remote add origin https://github.com/roar2lion/MzManuals.git
   git push -u origin main
   ```
3. On GitHub: *Settings → Pages → Build and deployment → Source: GitHub Actions*. Then re-run the workflow from the *Actions* tab (or push again).
4. `content/site.json` holds `"base_url": "https://roar2lion.github.io/MzManuals/"` (links between manuals inside PDFs use it) and `"repo_url"`. Update both if the repository is renamed.

If the repository gets a different name, use `https://roar2lion.github.io/<name>/` in the links above.

## Layout

| Path | What it holds |
|---|---|
| `content/manuals/<id>.json` | One manual each (methodology, definitions, …) |
| `content/glossary.json` | Terms shared by all manuals, cited as `[[term-id]]` |
| `content/site.json` | Site title, intro, `base_url` (live address, used for links between manuals inside PDFs) |
| `content/assets/` | Figures used by manuals |
| `schema/` | JSON Schemas: editors validate and autocomplete through each file's `$schema` line |
| `scripts/builder/build.py` | Validator and renderer (site + PDF) |
| `scripts/builder/static/` | Site CSS/JS and the print stylesheet |
| `scripts/json_to_md.py`, `scripts/md_to_json.py` | Convert a manual to Markdown and back (shared format: `scripts/manual_md.py`) |
| `build.cmd`, `json_to_md.cmd`, `md_to_json.cmd` | Double-click wrappers for the three scripts |
| `.github/workflows/pages.yml` | Validates every push or PR; builds and deploys the site and PDFs from `main` |
| `site/` | Build output (git-ignored) |
| `md/` | Markdown working copies of the manuals (git-ignored) |

## Use

```
build.cmd                                     validate, build site\ with drafts and PDFs, open it
build.cmd --check                             validate only
json_to_md.cmd                                write manuals as Markdown to md\ (pick from a list)
md_to_json.cmd                                put edited Markdown back into the JSON, then validate
python scripts/builder/build.py --new methodology "Methodology"   scaffold a new manual (starts as a draft, unpublished)
```

The PDFs are printed by a local Chrome or Edge, or by Chrome on the CI runner, so the PDF looks the same as the site, maths and diagrams included. Set `CHROME_PATH` if the browser is not in a standard place.

How to write a manual (block types, inline syntax, cross-references, glossary, publishing setup): the **Authoring Guide**, `content/manuals/authoring-guide.json`. It is built locally (`build.cmd`) and kept off the live site.

## Editing a manual as Markdown (e.g. with AI help)

The JSON is the source of every manual, but it is hard to read and edit as prose. The two converters give a Markdown working copy and bring the edits back:

1. **`json_to_md.cmd`**: pick the manuals (Enter = all). Each becomes `md/<id>.md`: sections as headings, paragraphs, lists, tables, entries and equations as ordinary Markdown.
2. **Edit `md/<id>.md`**, by hand or with AI help. Keep the front matter, every `<!-- ... -->` comment line and the `{#id}` at the end of each heading: they carry the structure back. The file's second line repeats these rules, so an AI assistant reading it sees them too.
   - A new paragraph needs nothing extra; it becomes a text block.
   - A new list, table or other block starts with a type comment line (e.g. `<!-- list -->`) copied from a block of the same type.
   - A new section needs a heading ending in a new `{#id}` (lower case, digits, hyphens).
   - Captions, notes and sources sit in the JSON of a comment line; edit them there.
   - The **Contents** list at the top links to every section and subsection (Ctrl+click in the editor, or click in the Markdown preview). It and the `<a id="…">` line above each heading are generated: `md_to_json` refreshes them, so a new or renamed heading gets its link on the next conversion.
3. **`md_to_json.cmd`**: pick the files (Enter = all). Each is written back to its JSON and validated with `scripts/builder/build.py --check`. If validation fails, the JSON is left as it was and the problems are listed.
4. Check the JSON diff, run `build.cmd` to see the result, then commit as usual.

The round trip is exact: parts you didn't edit keep their original text, so the JSON diff shows only your changes, and converting an unedited file changes nothing. Two safeguards ask before going ahead: `json_to_md` before overwriting an md file whose edits haven't gone back into the JSON, and `md_to_json` if the JSON changed after its md file was made (writing would undo that change). `md/` is git-ignored: the JSON stays the only source.

## Linking to a section (e.g. from slides)

Every section and subsection has a permanent link: the site address, the manual's page, `#` and the section's `id`:

```
https://roar2lion.github.io/MzManuals/<manual-id>.html#<section-id>
```

e.g. `https://roar2lion.github.io/MzManuals/pypsa-architecture.html#snsp`. The `id` is set in the manual's JSON, not derived from the title or number, so a link survives renaming and reordering; never change an `id` once something links to it. In PowerPoint, select a text box or icon, press Ctrl+K and paste the link.

Sections of `pypsa-architecture` for the efforts behind PyPSA's parity with PLEXOS (its Overview lists all six, `#overview`):

| Effort | Section `id` |
|---|---|
| Model size: milestone years and myopic blocks | `model-size` |
| Vintages, and builds locked in across blocks | `vintages`, `foresight` |
| Sampled chronology with peak and energy rescaling | `time-resolution` (`time-sampling`, `time-vs-plexos`) |
| Constraints added at solve time | `constraint-visibility`, `snsp`, `csp`, `energy-caps` |
| Corridor losses, token flow cost, cross-border markets | `corridors` (`corridor-losses`, `corridor-flow-cost`), `trade` |
| Economics and availability | `npv`, `availability` |

## Compared with the SPLAT-to-PyPSA manual

- **Many manuals, one builder.** The builder knows block types (text, list, table, entries, equation, callout, figure, diagram, code), not manual sections. A new manual needs no code change.
- **Checked before it is built.** A JSON Schema checks every manual, and the build also checks glossary terms, cross-references, figure files and duplicate anchors. Any problem stops the build.
- **Automatic numbering.** Sections, tables, figures and equations are numbered automatically, and cross-references follow when things move.
- **One source for HTML and PDF.** The PDF is printed from the same HTML, with a cover, a linked contents list, page numbers, a glossary appendix and the version history.
- **Shared glossary.** Terms are defined once and show their definition on hover. The glossary page lists which manuals use each term.
- **Search and draft control.** Search works offline. Drafts stay off the live site until `"publish": true`.
- **Provenance.** Each section can list the workspace files it was written from.
- **Deterministic output.** Same JSON in gives the same files out, with no build timestamps.

# tools — rebuilding the printable guides

The beginner guide exists in four forms. Two of them are **generated**, so they must be
rebuilt whenever the Markdown changes — otherwise they drift, which is exactly what
happened before 1.3.2 (the old PDF still described a dictation-only engine and told
readers to install into OneDrive-synced Documents).

| Source (edit this) | Generated | Build with |
|---|---|---|
| `docs/SETUP-CPU-LAPTOP.md` | `docs/Zero-Flow-Setup-Guide.pdf` | `python tools/build_setup_pdf.py` |
| `docs/SETUP-CPU-LAPTOP.ar.md` | `docs/SETUP-CPU-LAPTOP.ar.docx` | `node tools/build_setup_docx.js` |

Both read the Markdown directly and write into `docs/`, so the generated files can only
say what the guides say. Pass a path to write somewhere else and preview first.

## What you need once

```powershell
pip install reportlab      # the PDF
npm install docx           # the Word file (installs into ./node_modules)
```

Both run on Windows and use its **Arial** and **Consolas** fonts: ReportLab's built-in
fonts cannot draw the arrows and dashes the guide uses, and the Word file needs a font
with Arabic glyphs. `node_modules/` is git-ignored.

## After a rebuild, look at the result

The PDF opens in any viewer. For the Word file, open it in Word — check that the Arabic
still reads right-to-left, that code stays left-to-right inside it, and that no heading
was orphaned at the foot of a page.

## How they work

Each script is a small Markdown reader for the subset these guides use: headings,
paragraphs, bullet and numbered lists, tables, fenced code, and blockquotes that become
coloured call-out boxes (`💡` → TIP, `⚠️`/`🛑` → IMPORTANT, and so on). Both keep the
palette of the original hand-made documents: dark ink, green headings, red warnings,
grey code blocks.

Two things worth knowing before changing them:

- **The PDF has no emoji.** Its fonts have no colour glyphs, so emoji are stripped and
  blockquotes become labelled boxes instead. It also cannot shape Arabic, so the one
  bullet listing Arabic spoken commands points at the Arabic guide.
- **The Word file is right-to-left.** Runs holding only spaces or punctuation follow the
  paragraph direction, or Word parks them on the wrong side of Latin text — that is why
  `` `F7` **مرة واحدة** `` would otherwise come out as "F7مرة واحدة". A neutral run
  *between two Latin runs* stays left-to-right, so `F6/F8` does not flip.

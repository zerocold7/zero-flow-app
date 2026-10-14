# tools — rebuilding the printable guides

The beginner guide exists in four forms: the English and Arabic Markdown, and a PDF of
each. The PDFs are **generated**, so they must be rebuilt whenever the Markdown changes —
otherwise they drift, which is exactly what happened before 1.3.2 (the old PDF still
described a dictation-only engine and told readers to install into OneDrive-synced
Documents).

| Source (edit this) | Generated | Build with |
|---|---|---|
| `docs/SETUP-CPU-LAPTOP.md` | `docs/Zero-Flow-Setup-Guide.pdf` | `python tools/build_setup_pdf.py` |
| `docs/SETUP-CPU-LAPTOP.ar.md` | `docs/Zero-Flow-Setup-Guide.ar.pdf` | `powershell -ExecutionPolicy Bypass -File tools\build_setup_ar_pdf.ps1` |

Both read the Markdown directly and write into `docs/`, so the generated files can only
say what the guides say. Pass a path to write somewhere else and preview first
(`build_setup_pdf.py other.pdf`, `build_setup_ar_pdf.ps1 -Out other.pdf`).

The Arabic PDF takes two steps, because ReportLab (which makes the English one) cannot
shape Arabic: `build_setup_docx.js` lays the guide out as a right-to-left Word document
in a temporary folder, and Microsoft Word prints that to PDF. The Word document is
deleted afterwards — only the PDF is published.

## What you need once

```powershell
pip install reportlab      # the English PDF
npm install docx           # the Arabic layout step (installs into ./node_modules)
```

…and Microsoft Word, for the Arabic PDF. Both builds use Windows' **Arial** and
**Consolas** fonts: ReportLab's built-in fonts cannot draw the arrows and dashes the
guide uses, and the Arabic needs a font with Arabic glyphs. `node_modules/` is
git-ignored.

## After a rebuild, look at the result

Open both PDFs. In the Arabic one, check that the text still reads right-to-left, that
code stays left-to-right inside it, and that no heading was orphaned at the foot of a
page. (It is ~4 MB, against ~120 KB for the English one: it keeps the guide's colour
emoji, and Word embeds the emoji font for them.)

## How they work

Each layout script is a small Markdown reader for the subset these guides use:
headings, paragraphs, bullet and numbered lists, tables, fenced code, and blockquotes
that become coloured call-out boxes (`💡` → TIP, `⚠️`/`🛑` → IMPORTANT, and so on). Both
keep the palette of the original hand-made documents: dark ink, green headings, red
warnings, grey code blocks.

Two things worth knowing before changing them:

- **The English PDF has no emoji.** Its fonts have no colour glyphs, so emoji are
  stripped and blockquotes become labelled boxes instead. It also cannot shape Arabic,
  so the one bullet listing Arabic spoken commands points at the Arabic guide.
- **The Arabic layout is right-to-left.** Runs holding only spaces or punctuation follow
  the paragraph direction, or Word parks them on the wrong side of Latin text — that is
  why `` `F7` **مرة واحدة** `` would otherwise come out as "F7مرة واحدة". A neutral run
  *between two Latin runs* stays left-to-right, so `F6/F8` does not flip.

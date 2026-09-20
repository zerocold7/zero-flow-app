// Rebuild docs/SETUP-CPU-LAPTOP.ar.docx from docs/SETUP-CPU-LAPTOP.ar.md (RTL Arabic).
//
// Run it after editing the Arabic beginner guide, so the Word file never drifts from
// the Markdown it comes from:
//
//     npm install docx
//     node tools/build_setup_docx.js            // writes docs/SETUP-CPU-LAPTOP.ar.docx
//     node tools/build_setup_docx.js other.docx // or somewhere else, to preview first
//
// See tools/README.md.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, Footer,
  AlignmentType, BorderStyle, ShadingType, WidthType, LevelFormat, PageNumber,
  HeadingLevel,
} = require("docx");

const REPO = path.dirname(__dirname);
const SRC = path.join(REPO, "docs/SETUP-CPU-LAPTOP.ar.md");
const OUT = process.argv[2] || path.join(REPO, "docs/SETUP-CPU-LAPTOP.ar.docx");

const C = {
  body: "1B1F24", green: "2F6F4F", red: "B23B3B", blue: "244B6B", grey: "5B636C",
  code: "10222E", codeFill: "F3F4F6", warnFill: "FBEEE6", tipFill: "EAF4EE", rule: "C9D6CF",
};
const PAGE_W = 11906, MARGIN = 720, CONTENT_W = PAGE_W - 2 * MARGIN;   // A4, 0.5" margins
const ARABIC = /[\u0600-\u06FF]/;
const LATIN = /[A-Za-z0-9]/;
// A run is right-to-left unless it is purely Latin. Spaces and punctuation between an
// inline-code run and Arabic ("`F7` **\u0645\u0631\u0629**", "`qwen2.5:3b`).") must follow the
// paragraph, or Word parks them on the wrong side of the Latin text.
const isRtl = (s) => ARABIC.test(s) || !LATIN.test(s);

const font = (name) => ({ ascii: name, hAnsi: name, cs: name, eastAsia: name });

// ---------------------------------------------------------------- inline text
function runs(text, { size = 24, color = C.body, boldColor = null, bold = false } = {}) {
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");            // links → their text
  const pieces = [];
  text.split("**").forEach((seg, i) => {
    seg.split("`").forEach((piece, j) => {
      if (piece) pieces.push({ piece, isBold: bold || i % 2 === 1, isCode: j % 2 === 1 });
    });
  });
  // Unicode bidi keeps a neutral between two Latin runs left-to-right ("F6/F8");
  // everywhere else a neutral follows the paragraph (see isRtl).
  const latin = (p) => p && (p.isCode || (LATIN.test(p.piece) && !ARABIC.test(p.piece)));
  pieces.forEach((p, k) => {
    p.rtl = !p.isCode && isRtl(p.piece) &&
            !(!LATIN.test(p.piece) && !ARABIC.test(p.piece) && latin(pieces[k - 1]) && latin(pieces[k + 1]));
  });
  const out = [];
  pieces.forEach(({ piece, isBold, isCode, rtl }) => {
    {
      if (isCode) {
        out.push(new TextRun({
          text: piece, font: font("Consolas"), size: size - 4, sizeComplexScript: size - 4,
          color: C.code, shading: { type: ShadingType.CLEAR, fill: C.codeFill, color: "auto" },
          rightToLeft: false,
        }));
      } else {
        out.push(new TextRun({
          text: piece, font: font("Arial"), size, sizeComplexScript: size,
          bold: isBold, boldComplexScript: isBold,
          color: isBold && boldColor ? boldColor : color,
          rightToLeft: rtl,
        }));
      }
    }
  });
  return out;
}

const box = (color) => {
  const side = { style: BorderStyle.SINGLE, size: 6, color, space: 4 };
  return { top: side, bottom: side, left: side, right: side };
};

// ---------------------------------------------------------------- blocks
function para(text, opts = {}) {
  return new Paragraph({
    bidirectional: true,
    // a problem stays with its answer, and "…:" stays with the code block under it
    keepNext: /^\*\*المشكلة/.test(text) || /:\s*$/.test(text),
    spacing: { before: opts.before ?? 60, after: opts.after ?? 100, line: 300 },
    children: runs(text, opts),
  });
}

function heading(text, level, accent) {
  const h2 = level === 2;
  return new Paragraph({
    bidirectional: true,
    heading: h2 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
    spacing: { before: h2 ? 320 : 220, after: 120 },
    keepNext: true,
    border: h2 ? { bottom: { style: BorderStyle.SINGLE, size: 8, color: accent, space: 4 } } : undefined,
    children: runs(text, { size: h2 ? 30 : 26, color: accent, bold: true }),
  });
}

function callout(text) {
  const warn = /^(⚠️|🛑)/.test(text);
  const accent = warn ? C.red : C.green;
  return new Paragraph({
    bidirectional: true,
    spacing: { before: 140, after: 140, line: 300 },
    indent: { left: 120, right: 120 },
    shading: { type: ShadingType.CLEAR, fill: warn ? C.warnFill : C.tipFill, color: "auto" },
    border: box(accent),
    children: runs(text, { boldColor: accent }),
  });
}

function code(lines) {
  const size = lines.some((l) => l.length > 90) ? 17 : 20;
  return lines.map((line, i) => new Paragraph({
    bidirectional: false,
    alignment: AlignmentType.LEFT,
    spacing: { before: i === 0 ? 100 : 0, after: i === lines.length - 1 ? 140 : 0, line: 260 },
    indent: { left: 120, right: 120 },
    shading: { type: ShadingType.CLEAR, fill: C.codeFill, color: "auto" },
    border: box("D5D9DE"),
    children: [new TextRun({
      text: line || " ", font: font("Consolas"), size, sizeComplexScript: size,
      color: C.code, rightToLeft: false,
    })],
  }));
}

function table(rows) {
  const widths = [2300, CONTENT_W - 2300];
  const cell = (text, i, header) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: header ? { type: ShadingType.CLEAR, fill: C.green, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({
      bidirectional: true,
      children: runs(text, header ? { size: 22, color: "FFFFFF", bold: true } : { size: 22 }),
    })],
  });
  return new Table({
    visuallyRightToLeft: true,
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: ri === 0,
      children: r.map((t, i) => cell(t, i, ri === 0)),
    })),
  });
}

// ---------------------------------------------------------------- the markdown
const lines = fs.readFileSync(SRC, "utf8").split(/\r?\n/);
const children = [];
let accent = C.green;         // colour of the current section
let listInstance = 0;          // restart numbering for each numbered list
let inNumbered = false;
let seenTitle = false, headerLines = 0;

for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  const t = line.trim();
  if (!t || t.startsWith("<div") || t === "</div>" || t === "---") continue;

  if (t.startsWith("```")) {
    const body = [];
    while (++i < lines.length && !lines[i].trim().startsWith("```")) body.push(lines[i]);
    children.push(...code(body));
    continue;
  }
  if (!/^\d+\. /.test(t)) inNumbered = false;

  if (t.startsWith("# ")) {
    seenTitle = true;
    children.push(new Paragraph({
      bidirectional: true, spacing: { after: 60 },
      children: runs(t.slice(2), { size: 36, bold: true }),
    }));
  } else if (seenTitle && headerLines < 2 && !t.startsWith(">") && !t.startsWith("#")) {
    // the two lines under the title: the green subtitle, then the grey meta line
    children.push(headerLines === 0
      ? para(t.replace(/\*\*/g, ""), { size: 24, color: C.green, bold: true, after: 40 })
      : para(t, { size: 17, color: C.grey, after: 200 }));
    headerLines++;
  } else if (t.startsWith("## ")) {
    accent = t.includes("🚨") ? C.red : t.includes("سابعاً") ? C.blue : C.green;
    children.push(heading(t.slice(3), 2, accent));
  } else if (t.startsWith("### ")) {
    children.push(heading(t.slice(4), 3, accent));
  } else if (t.startsWith(">")) {
    const quote = t.replace(/^>\s?/, "");
    if (quote.startsWith("🌍")) continue;                  // cross-links between the Markdown files
    children.push(callout(quote));
  } else if (t.startsWith("|")) {
    const rows = [];
    for (; i < lines.length && lines[i].trim().startsWith("|"); i++) {
      const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      if (!cells.every((c) => /^-+$/.test(c))) rows.push(cells);
    }
    i--;
    children.push(table(rows));
  } else if (t.startsWith("- ")) {
    children.push(new Paragraph({
      bidirectional: true,
      numbering: { reference: "bullets", level: 0 },
      spacing: { before: 40, after: 60, line: 300 },
      children: runs(t.slice(2), { boldColor: accent }),
    }));
  } else if (/^\d+\. /.test(t)) {
    if (!inNumbered) { listInstance++; inNumbered = true; }
    children.push(new Paragraph({
      bidirectional: true,
      numbering: { reference: "steps", level: 0, instance: listInstance },
      keepNext: /:\s*$/.test(t),
      spacing: { before: 40, after: 60, line: 300 },
      children: runs(t.replace(/^\d+\. /, "")),
    }));
  } else if (/^\*\*المشكلة/.test(t)) {
    children.push(para(t, { color: C.red, bold: true, before: 180, after: 40 }));
  } else if (t.startsWith("الحل:")) {
    children.push(para(t.replace(/^الحل:/, "**الحل:**"), { size: 22, after: 80 }));
  } else if (/^\(.*\)$/.test(t)) {
    children.push(para(t, { size: 21, color: C.grey }));   // the small bracketed asides
  } else {
    children.push(para(t, { boldColor: /^\*\*\d+\.\*\*/.test(t) ? C.green : null }));
  }
}

// ---------------------------------------------------------------- the document
const doc = new Document({
  creator: "zerocold7",
  title: "دليل تثبيت Zero- Flow Engine - نسخة اللابتوب",
  description: "Generated from docs/SETUP-CPU-LAPTOP.ar.md",
  styles: {
    default: { document: { run: { font: "Arial", size: 24, language: { value: "en-US", bidirectional: "ar-SA" } } } },
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.START,
          style: { paragraph: { indent: { left: 460, hanging: 260 } } } }] },
      { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.START,
          style: { paragraph: { indent: { left: 460, hanging: 320 } }, run: { bold: true, color: C.green } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 },
      margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN, footer: 400 } } },
    footers: { default: new Footer({ children: [new Paragraph({
      bidirectional: true, alignment: AlignmentType.CENTER,
      border: { top: { style: BorderStyle.SINGLE, size: 4, color: C.rule, space: 4 } },
      children: [new TextRun({ children: ["Zero- Flow Engine — دليل اللابتوب · صفحة ", PageNumber.CURRENT],
        font: font("Arial"), size: 17, sizeComplexScript: 17, color: C.grey, rightToLeft: true })],
    })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`wrote ${OUT} (${buf.length} bytes, ${children.length} blocks)`);
});

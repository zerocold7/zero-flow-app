# Rebuild docs/Zero-Flow-Setup-Guide.ar.pdf from docs/SETUP-CPU-LAPTOP.ar.md.
#
#     powershell -ExecutionPolicy Bypass -File tools\build_setup_ar_pdf.ps1
#
# The Arabic guide is laid out by build_setup_docx.js (right-to-left, with code kept
# left-to-right inside it) and then printed to PDF by Microsoft Word, which shapes
# Arabic correctly - ReportLab, which makes the English PDF, cannot. The Word file is
# only an in-between step: it is written to a temporary folder and deleted.
# Needs: node with `npm install docx` (see tools/README.md), and Microsoft Word.
param([string]$Out = "")

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Out) { $Out = Join-Path $repo "docs\Zero-Flow-Setup-Guide.ar.pdf" }
$docx = Join-Path ([IO.Path]::GetTempPath()) ("zero-flow-guide-ar-" + [guid]::NewGuid() + ".docx")

try {
    node (Join-Path $repo "tools\build_setup_docx.js") $docx
    if ($LASTEXITCODE -ne 0) { throw "build_setup_docx.js failed (exit $LASTEXITCODE)" }

    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    try {
        $doc = $word.Documents.Open($docx, $false, $true)    # not a conversion, read-only
        $doc.ExportAsFixedFormat($Out, 17)                    # 17 = wdExportFormatPDF
        $doc.Close($false)
    } finally {
        $word.Quit()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
    Write-Output "wrote $Out"
} finally {
    if (Test-Path $docx) { Remove-Item $docx -Force }
}

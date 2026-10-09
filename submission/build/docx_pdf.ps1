# Export a Word document to PDF through Word (COM). Usage: powershell -File docx_pdf.ps1 -In <docx> -Out <pdf>
param([Parameter(Mandatory)][string]$In, [Parameter(Mandatory)][string]$Out)
$w = New-Object -ComObject Word.Application
$w.Visible = $false
try {
    $d = $w.Documents.Open((Resolve-Path $In).Path, $false, $true)
    $d.ExportAsFixedFormat($Out, 17)   # 17 = wdExportFormatPDF
    $d.Close($false)
    "wrote $Out"
} finally {
    $w.Quit()
}

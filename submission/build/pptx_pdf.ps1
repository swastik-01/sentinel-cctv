# Export the deck to PDF through PowerPoint itself (real fonts, same rendering as the slides).
# powershell -File pptx_pdf.ps1 [-Pptx ..\out\Sentinel-Solution.pptx] [-Pdf ..\out\Sentinel-Solution.pdf]
param([string]$Pptx = "$PSScriptRoot\..\out\Sentinel-Solution.pptx",
      [string]$Pdf = "$PSScriptRoot\..\out\Sentinel-Solution.pdf")

$ErrorActionPreference = "Stop"
$Pptx = (Resolve-Path $Pptx).Path
$Pdf = [System.IO.Path]::GetFullPath($Pdf)
$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open($Pptx, -1, 0, 0)   # read-only, no window
    $pres.SaveAs($Pdf, 32)                               # 32 = ppSaveAsPDF
    $pres.Close()
    "wrote $Pdf"
} finally {
    $app.Quit()
}

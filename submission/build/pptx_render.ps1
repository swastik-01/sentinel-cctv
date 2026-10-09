# Render every slide of a .pptx to PNG through PowerPoint itself (visual QA with real fonts).
# powershell -File pptx_render.ps1 -Pptx deck.pptx -OutDir slides_png [-Width 1600]
param([Parameter(Mandatory)][string]$Pptx, [Parameter(Mandatory)][string]$OutDir, [int]$Width = 1600)

$ErrorActionPreference = "Stop"
$Pptx = (Resolve-Path $Pptx).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
Get-ChildItem $OutDir -Filter *.png -ErrorAction SilentlyContinue | Remove-Item -Force

$app = New-Object -ComObject PowerPoint.Application
try {
    # Open(FileName, ReadOnly, Untitled, WithWindow) — MsoTriState: -1 true, 0 false
    $pres = $app.Presentations.Open($Pptx, -1, 0, 0)
    $height = [int]($Width * $pres.PageSetup.SlideHeight / $pres.PageSetup.SlideWidth)
    $i = 0
    foreach ($slide in $pres.Slides) {
        $i++
        $file = Join-Path $OutDir ("slide-{0:D2}.png" -f $i)
        $slide.Export($file, "PNG", $Width, $height)
    }
    "rendered $i slides to $OutDir"
    $pres.Close()
} finally {
    $app.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}

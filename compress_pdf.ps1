Param(
  [string]$InputPath,
  [string]$OutputPath,
  [ValidateSet("screen","ebook","printer","prepress")] [string]$Quality = "ebook",
  [int]$ColorDpi = 150,
  [int]$GrayDpi = 150,
  [int]$MonoDpi = 300,
  [switch]$NoDownsample,
  [string]$GhostscriptPath
)

$ErrorActionPreference = "Stop"

function Get-Ghostscript {
  if ($GhostscriptPath) {
    if (-not (Test-Path $GhostscriptPath)) {
      throw "GhostscriptPath introuvable: $GhostscriptPath"
    }
    return $GhostscriptPath
  }
  $cmd = Get-Command gswin64c -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $cmd = Get-Command gswin32c -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $gsCandidates = @()
  $gsCandidates += Get-ChildItem -Path "C:\\Program Files\\gs\\*\\bin\\gswin64c.exe" -ErrorAction SilentlyContinue
  $gsCandidates += Get-ChildItem -Path "C:\\Program Files\\gs\\*\\bin\\gswin32c.exe" -ErrorAction SilentlyContinue
  if ($gsCandidates.Count -gt 0) {
    return $gsCandidates | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
  }
  return $null
}

$gs = Get-Ghostscript
if (-not $gs) {
  throw "Ghostscript introuvable (gswin64c/gswin32c). Installez Ghostscript et rouvrez PowerShell."
}

if (-not $InputPath) {
  $latest = Get-ChildItem -Filter *.pdf | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $latest) { throw "Aucun PDF trouve dans le dossier." }
  $InputPath = $latest.FullName
}

if (-not (Test-Path $InputPath)) {
  throw "Fichier introuvable: $InputPath"
}

$InputPath = (Resolve-Path -LiteralPath $InputPath).Path

if (-not $OutputPath) {
  $dir = Split-Path -Parent $InputPath
  if ([string]::IsNullOrWhiteSpace($dir)) {
    $dir = (Get-Location).Path
  }
  $base = [System.IO.Path]::GetFileNameWithoutExtension($InputPath)
  $OutputPath = Join-Path $dir ($base + "_compressed.pdf")
}

$pdfSettings = "/$Quality"

$args = @(
  "-sDEVICE=pdfwrite",
  "-dCompatibilityLevel=1.4",
  "-dPDFSETTINGS=$pdfSettings",
  "-dNOPAUSE",
  "-dBATCH"
)

if (-not $NoDownsample) {
  $args += @(
    "-dDownsampleColorImages=true",
    "-dColorImageResolution=$ColorDpi",
    "-dDownsampleGrayImages=true",
    "-dGrayImageResolution=$GrayDpi",
    "-dDownsampleMonoImages=true",
    "-dMonoImageResolution=$MonoDpi"
  )
}

$args += @(
  "-sOutputFile=$OutputPath",
  $InputPath
)

Write-Host "Input : $InputPath"
Write-Host "Output: $OutputPath"
Write-Host "Quality: $Quality" + ($(if ($NoDownsample) { " (no downsample)" } else { "" }))

& $gs @args
Write-Host "Done."

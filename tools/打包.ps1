# Builds the zip that gets handed to other people.
#
# Windows' bundled tar.exe writes zip entry names in the local code page, which
# silently mangles every Chinese filename - including 開啟建材彙整.cmd, the one
# file the recipient is told to double-click. It does not fail loudly; the files
# simply refuse to extract on the other end. So the archive is built through
# .NET, which writes UTF-8 entry names.
#
# runtime\ and vendor\ ARE included on purpose: they are what makes the folder
# run with nothing installed. .venv and node_modules are not - they are specific
# to the machine that built them and are rebuilt on demand.

[CmdletBinding()]
param(
    [string]$Out = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) '建材彙整_可直接執行.zip')
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$name = Split-Path -Leaf $root

# Directory names excluded wherever they appear in the tree.
$skipDirs = @('.venv', 'node_modules', '__pycache__', 'logs', 'out', '.git')

Write-Host "打包 $root" -ForegroundColor Cyan

$files = Get-ChildItem -LiteralPath $root -Recurse -File -Force | Where-Object {
    $rel = $_.FullName.Substring($root.Length).TrimStart('\')
    $parts = $rel -split '\\'
    # Drop anything under an excluded directory, plus loose build leftovers.
    -not ($parts | Where-Object { $skipDirs -contains $_ }) -and $_.Extension -ne '.pyc'
}

Write-Host ("   {0:N0} 個檔案" -f $files.Count)

if (Test-Path -LiteralPath $Out) { Remove-Item -LiteralPath $Out -Force }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = [System.IO.Compression.ZipFile]::Open($Out, 'Create')
try {
    foreach ($f in $files) {
        $rel = $f.FullName.Substring($root.Length).TrimStart('\')
        # Zip entries use forward slashes; keep the project folder as the root
        # so extracting produces one tidy directory rather than loose files.
        $entry = "$name/" + ($rel -replace '\\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, $f.FullName, $entry,
            [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally {
    $zip.Dispose()
}

$mb = [math]::Round((Get-Item -LiteralPath $Out).Length / 1MB, 1)
Write-Host "   完成：$Out（$mb MB）" -ForegroundColor Green

$urls = @(
 'https://github.com/oschwartz10612/poppler-windows/releases/download/v23.10.0/Poppler-23.10.0.zip',
 'https://github.com/oschwartz10612/poppler-windows/releases/download/v23.05.0/Poppler-23.05.0.zip',
 'https://github.com/oschwartz10612/poppler-windows/releases/download/v22.12.0/Poppler-22.12.0.zip'
)
New-Item -ItemType Directory -Force -Path 'tools' | Out-Null
$downloaded = $false
foreach ($u in $urls) {
 try {
   $tmp='tools\poppler.zip'
   Write-Host "Trying $u"
   Invoke-WebRequest -Uri $u -OutFile $tmp -UseBasicParsing -ErrorAction Stop
   Expand-Archive -Path $tmp -DestinationPath 'tools\poppler' -Force
   $downloaded=$true
   break
 } catch {
   Write-Host ('Failed {0}: {1}' -f $u, $_.Exception.Message)
 }
}
if (-not $downloaded) {
 if (Get-Command winget -ErrorAction SilentlyContinue) {
   Write-Host 'Attempting winget search poppler'
   winget search poppler
 } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
   Write-Host 'Attempting choco install poppler'
   choco install poppler -y
 } else {
   Write-Host 'No winget or choco available; cannot automatically install Poppler'
 }
}
if ($downloaded) { Write-Host 'Poppler extracted to tools\poppler' } else { Write-Host 'Poppler installation/extract did not succeed'; exit 2 }

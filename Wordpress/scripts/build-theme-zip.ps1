Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$rootDir = Split-Path -Parent $PSScriptRoot
$themeSlug = 'marketlense'
$themeDir = Join-Path $rootDir "wp-content/themes/$themeSlug"
$distDir = Join-Path $rootDir 'dist'
$zipPath = Join-Path $distDir "$themeSlug.zip"
$rootParent = Split-Path -Parent $themeDir

if (-not (Test-Path -Path $themeDir -PathType Container)) {
    throw "Theme directory not found: $themeDir"
}

$excludeDirs = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
@(
    '.git',
    '.github',
    'node_modules',
    'tests',
    'test',
    'dist',
    'coverage',
    '__pycache__',
    '.pytest_cache'
) | ForEach-Object {
    [void] $excludeDirs.Add($_)
}

$excludeFiles = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
@('.DS_Store', 'Thumbs.db', '.env') | ForEach-Object {
    [void] $excludeFiles.Add($_)
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BasePath,

        [Parameter(Mandatory = $true)]
        [string] $TargetPath
    )

    $baseFullPath = [System.IO.Path]::GetFullPath($BasePath)
    $targetFullPath = [System.IO.Path]::GetFullPath($TargetPath)

    if (-not $baseFullPath.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $baseFullPath += [System.IO.Path]::DirectorySeparatorChar
    }

    $baseUri = [System.Uri] $baseFullPath
    $targetUri = [System.Uri] $targetFullPath
    $relativeUri = $baseUri.MakeRelativeUri($targetUri)

    return [System.Uri]::UnescapeDataString($relativeUri.ToString()).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
}

function Test-ExcludedPath {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo] $File
    )

    if ($excludeFiles.Contains($File.Name) -or $File.Name.StartsWith('.env.', [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }

    $relativeDirectory = Get-RelativePath -BasePath $themeDir -TargetPath $File.DirectoryName
    if ([string]::IsNullOrWhiteSpace($relativeDirectory) -or $relativeDirectory -eq '.') {
        return $false
    }

    foreach ($segment in $relativeDirectory.Split([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)) {
        if ($segment -ne '' -and $excludeDirs.Contains($segment)) {
            return $true
        }
    }

    return $false
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

New-Item -ItemType Directory -Path $distDir -Force | Out-Null
if (Test-Path -Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

$archive = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)

try {
    foreach ($file in Get-ChildItem -Path $themeDir -File -Recurse | Sort-Object FullName) {
        if (Test-ExcludedPath -File $file) {
            continue
        }

        $entryPath = (Get-RelativePath -BasePath $rootParent -TargetPath $file.FullName).Replace('\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $file.FullName,
            $entryPath,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $archive.Dispose()
}

$verificationArchive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    foreach ($entryPath in @("$themeSlug/style.css", "$themeSlug/assets/css/theme.css")) {
        if ($null -eq $verificationArchive.GetEntry($entryPath)) {
            throw "Theme archive is missing required entry: $entryPath"
        }
    }
}
finally {
    $verificationArchive.Dispose()
}

Write-Output "Built theme archive: $zipPath"

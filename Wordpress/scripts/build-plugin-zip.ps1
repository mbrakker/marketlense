Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$rootDir = Split-Path -Parent $PSScriptRoot
$pluginSlug = 'marketlense-core'
$pluginDir = Join-Path $rootDir "wp-content/plugins/$pluginSlug"
$distDir = Join-Path $rootDir 'dist'
$zipPath = Join-Path $distDir "$pluginSlug.zip"
$rootParent = Split-Path -Parent $pluginDir

if (-not (Test-Path -Path $pluginDir -PathType Container)) {
    throw "Plugin directory not found: $pluginDir"
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

function Test-ExcludedPath {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo] $File
    )

    if ($excludeFiles.Contains($File.Name)) {
        return $true
    }

    if ($File.Name.StartsWith('.env.', [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }

    $relativeDirectory = Get-RelativePath -BasePath $pluginDir -TargetPath $File.DirectoryName
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

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

New-Item -ItemType Directory -Path $distDir -Force | Out-Null
if (Test-Path -Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

$archive = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)

try {
    foreach ($file in Get-ChildItem -Path $pluginDir -File -Recurse | Sort-Object FullName) {
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

Write-Output "Built plugin archive: $zipPath"

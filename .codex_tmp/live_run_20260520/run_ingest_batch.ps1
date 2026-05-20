$ErrorActionPreference = 'Continue'
$root = '.codex_tmp/live_run_20260520'
$targetsPath = Join-Path $root 'ingest_targets.json'
$partialPath = Join-Path $root 'ingest_results.partial.json'
$finalPath = Join-Path $root 'ingest_results.json'
$statusPath = Join-Path $root 'ingest_batch_status.json'
$targets = Get-Content $targetsPath -Raw | ConvertFrom-Json
$results = @()
$idx = 0

foreach ($target in $targets) {
  $idx += 1
  $safe = ($target.publisher -replace '[^A-Za-z0-9_-]+', '_').Trim('_')
  $out = Join-Path $root ("ingest_{0:D2}_{1}.out.txt" -f $idx, $safe)
  $err = Join-Path $root ("ingest_{0:D2}_{1}.err.txt" -f $idx, $safe)
  $started = Get-Date
  [pscustomobject]@{
    current_index = $idx
    current_publisher = $target.publisher
    current_folder_id = $target.folder_id
    started_at = $started.ToUniversalTime().ToString('o')
    total_targets = $targets.Count
    completed_targets = $results.Count
  } | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $statusPath

  & python -m src.cli ingest --folder $target.folder_id --limit ([int]$target.limit) 1> $out 2> $err
  $code = $LASTEXITCODE
  $finished = Get-Date
  $results += [pscustomobject]@{
    publisher = $target.publisher
    folder_id = $target.folder_id
    limit = $target.limit
    returncode = $code
    started_at = $started.ToUniversalTime().ToString('o')
    finished_at = $finished.ToUniversalTime().ToString('o')
    duration_seconds = [math]::Round(($finished - $started).TotalSeconds, 2)
    stdout_path = $out
    stderr_path = $err
    stdout_tail = if (Test-Path $out) { (Get-Content $out -Tail 160) -join "`n" } else { '' }
    stderr_tail = if (Test-Path $err) { (Get-Content $err -Tail 220) -join "`n" } else { '' }
  }
  $results | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $partialPath

  [pscustomobject]@{
    current_index = $idx
    current_publisher = $target.publisher
    current_folder_id = $target.folder_id
    started_at = $started.ToUniversalTime().ToString('o')
    finished_at = $finished.ToUniversalTime().ToString('o')
    total_targets = $targets.Count
    completed_targets = $results.Count
    last_returncode = $code
  } | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $statusPath
}

$results | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $finalPath
[pscustomobject]@{
  finished_at = (Get-Date).ToUniversalTime().ToString('o')
  total_targets = $targets.Count
  completed_targets = $results.Count
  failed_targets = @($results | Where-Object { $_.returncode -ne 0 }).Count
} | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $statusPath

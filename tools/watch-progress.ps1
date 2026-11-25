# 实时下载进度条监控
# 用法: powershell -File watch-progress.ps1
param(
    [string]$Path = "$env:TEMP\cmdline-tools.zip",
    [long]$Total = 153583359,
    [int]$IntervalSec = 2
)

$last = 0
$lastTime = Get-Date

while ($true) {
    $len = if (Test-Path $Path) { (Get-Item $Path).Length } else { 0 }
    $pct = if ($Total -gt 0) { $len / $Total * 100 } else { 0 }
    $bars = [math]::Floor($pct / 5)
    $barStr = ('█' * $bars).PadRight(20, '░')

    $now = Get-Date
    $dt = ($now - $lastTime).TotalSeconds
    $speed = if ($dt -gt 0) { ($len - $last) / 1MB / $dt } else { 0 }
    $remain = if ($speed -gt 0 -and $len -lt $Total) { ($Total - $len) / 1MB / $speed } else { 0 }

    $line = "[{0}] {1,5:N1}%  {2,7:N1}/{3:N1} MB  {4,5:N2} MB/s  剩余 {5,4:N0}s" -f `
        $barStr, $pct, ($len / 1MB), ($Total / 1MB), $speed, $remain
    Write-Host "`r$line" -NoNewline

    $last = $len
    $lastTime = $now

    if ($len -ge $Total) {
        Write-Host "`n下载完成"
        break
    }
    Start-Sleep -Seconds $IntervalSec
}

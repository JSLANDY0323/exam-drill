<#
.SYNOPSIS
Windows 電子書截圖：截取目前頁，再按鍵盤右方向鍵翻頁。
.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\capture_ebook.ps1 -Pages 20
#>
[CmdletBinding()]
param(
    [ValidateRange(0, 5000)][int]$Pages = 0,
    [ValidateRange(0.5, 30)][double]$Delay = 2
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
if (-not ('EbookScreenshot.Native' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace EbookScreenshot {
    [StructLayout(LayoutKind.Sequential)]
    public struct Point { public int X; public int Y; }
    public static class Native {
        [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
        [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int key);
        [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point point);
        [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point point);
        [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr window, uint flags);
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);
    }
}
'@
}
[void][EbookScreenshot.Native]::SetProcessDPIAware()

function Test-Key([int]$Key) {
    return (([int][EbookScreenshot.Native]::GetAsyncKeyState($Key) -band 0x8000) -ne 0)
}
function Wait-StopAware([double]$Seconds) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        if (Test-Key 0x79) { throw '已按 F10 停止。' }
        Start-Sleep -Milliseconds 50
    } while ($timer.Elapsed.TotalSeconds -lt $Seconds)
}
function Select-Point([string]$Message) {
    Write-Host $Message -ForegroundColor Cyan
    while (Test-Key 0x77) { Wait-StopAware 0.05 }
    while (-not (Test-Key 0x77)) { Wait-StopAware 0.05 }
    $point = New-Object EbookScreenshot.Point
    if (-not [EbookScreenshot.Native]::GetCursorPos([ref]$point)) { throw '無法讀取滑鼠位置。' }
    while (Test-Key 0x77) { Wait-StopAware 0.05 }
    return $point
}
function Assert-Reader([IntPtr]$Window) {
    if (Test-Key 0x79) { throw '已按 F10 停止。' }
    if ([EbookScreenshot.Native]::GetForegroundWindow() -ne $Window) {
        throw '已切換到其他視窗，停止截圖。'
    }
}
function Save-Screenshot([Drawing.Rectangle]$Area, [string]$Path) {
    $bitmap = New-Object Drawing.Bitmap($Area.Width, $Area.Height)
    $graphics = $null
    $stream = $null
    try {
        $graphics = [Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($Area.Location, [Drawing.Point]::Empty, $Area.Size)
        $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
        $bitmap.Save($stream, [Drawing.Imaging.ImageFormat]::Png)
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ($null -ne $graphics) { $graphics.Dispose() }
        $bitmap.Dispose()
    }
}

$saved = 0
try {
    Write-Host '電子書截圖：目前頁 → 鍵盤右方向鍵 → 下一頁' -ForegroundColor Green
    Write-Host '先在瀏覽器打開起始頁，確認鍵盤 → 可以翻頁。'
    if ($Pages -eq 0) {
        $inputPages = Read-Host '要截幾張圖片'
        $parsedPages = 0
        if (-not [int]::TryParse($inputPages, [ref]$parsedPages) -or $parsedPages -lt 1 -or $parsedPages -gt 5000) {
            throw '請輸入 1～5000 的整數。'
        }
        $Pages = $parsedPages
    }
    Write-Host '接著切到閱讀器，依序用 F8 設定截圖左上角、右下角。'
    Write-Host '兩個位置都設定好後，會倒數 5 秒開始；按住 F10 可停止。'
    [void](Read-Host '按 Enter 後開始選取')
    $upper = Select-Point '1/2 滑鼠移到書頁左上角，按一下 F8（不用點滑鼠）。'
    $lower = Select-Point '2/2 滑鼠移到書頁右下角，按一下 F8（不用點滑鼠）。'
    $width = $lower.X - $upper.X
    $height = $lower.Y - $upper.Y
    if ($width -lt 50 -or $height -lt 50) { throw '範圍太小或角落順序錯誤，請重新執行。' }
    $area = New-Object Drawing.Rectangle($upper.X, $upper.Y, $width, $height)
    $center = New-Object EbookScreenshot.Point
    $center.X = $upper.X + [int]($width / 2)
    $center.Y = $upper.Y + [int]($height / 2)
    $reader = [EbookScreenshot.Native]::GetAncestor([EbookScreenshot.Native]::WindowFromPoint($center), 2)
    if ($reader -eq [IntPtr]::Zero) { throw '找不到閱讀器視窗。' }
    $project = Split-Path -Parent $PSScriptRoot
    $runName = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
    $output = Join-Path (Join-Path $project 'private\ebook_captures') $runName
    [void][IO.Directory]::CreateDirectory($output)
    Write-Host "5 秒後開始，共 $Pages 張。請保持閱讀器在前景，不要移動視窗或切換分頁。"
    Write-Host "儲存位置：$output"
    Wait-StopAware 5
    for ($page = 1; $page -le $Pages; $page++) {
        Assert-Reader $reader
        Save-Screenshot $area (Join-Path $output ('page-{0:D4}.png' -f $page))
        $saved++
        Write-Host "已存 $saved / $Pages"
        if ($page -eq $Pages) { break }
        Assert-Reader $reader
        # VK_RIGHT = 0x27; KEYEVENTF_KEYUP = 0x0002.
        try { [EbookScreenshot.Native]::keybd_event(0x27, 0, 0, [UIntPtr]::Zero) }
        finally { [EbookScreenshot.Native]::keybd_event(0x27, 0, 2, [UIntPtr]::Zero) }
        Wait-StopAware $Delay
    }
    Write-Host "完成，共 $saved 張。圖片：$output" -ForegroundColor Green
} catch {
    Write-Host ("停止：{0} 已存 {1} 張。" -f $_.Exception.Message, $saved) -ForegroundColor Yellow
    exit 1
}

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PdfPath,

    [string]$Language = "vi-VN"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Add-Type -AssemblyName System.Runtime.WindowsRuntime

function Get-AsTaskMethod {
    param(
        [int]$GenericCount,
        [int]$ParameterCount,
        [string]$SignatureHint = ""
    )

    return [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.GetGenericArguments().Count -eq $GenericCount -and
            $_.GetParameters().Count -eq $ParameterCount -and
            (
                -not $SignatureHint -or
                $_.ToString().Contains($SignatureHint)
            )
        } |
        Select-Object -First 1
}

function Await-WinRtResult {
    param(
        [Parameter(Mandatory = $true)]
        $AsyncOperation,

        [Parameter(Mandatory = $true)]
        [Type]$ResultType
    )

    $method = Get-AsTaskMethod -GenericCount 1 -ParameterCount 1 -SignatureHint "IAsyncOperation"
    $genericMethod = $method.MakeGenericMethod($ResultType)
    $task = $genericMethod.Invoke($null, @($AsyncOperation))
    return $task.GetAwaiter().GetResult()
}

function Await-WinRtAction {
    param(
        [Parameter(Mandatory = $true)]
        $AsyncAction
    )

    $method = Get-AsTaskMethod -GenericCount 0 -ParameterCount 1 -SignatureHint "IAsyncAction"
    $task = $method.Invoke($null, @($AsyncAction))
    $task.GetAwaiter().GetResult() | Out-Null
}

function New-OcrEngine {
    param([string]$LanguageTag)

    $null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime]

    if ($LanguageTag) {
        try {
            $language = [Windows.Globalization.Language]::new($LanguageTag)
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
            if ($engine) {
                return $engine
            }
        } catch {
        }
    }

    return [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Data.Pdf.PdfPageRenderOptions, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType = WindowsRuntime]

$resolvedPath = (Resolve-Path -LiteralPath $PdfPath).Path
$file = Await-WinRtResult -AsyncOperation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolvedPath)) -ResultType ([Windows.Storage.StorageFile])
$pdf = Await-WinRtResult -AsyncOperation ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) -ResultType ([Windows.Data.Pdf.PdfDocument])
$engine = New-OcrEngine -LanguageTag $Language

if (-not $engine) {
    throw "Windows OCR engine is not available for the requested language."
}

$pages = @()

for ($index = 0; $index -lt $pdf.PageCount; $index++) {
    $page = $pdf.GetPage($index)
    try {
        $stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
        $renderOptions = [Windows.Data.Pdf.PdfPageRenderOptions]::new()
        $renderOptions.DestinationWidth = [uint32]1800
        $renderOptions.DestinationHeight = [uint32]2400
        Await-WinRtAction -AsyncAction ($page.RenderToStreamAsync($stream, $renderOptions))

        $decoder = Await-WinRtResult -AsyncOperation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) -ResultType ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-WinRtResult -AsyncOperation ($decoder.GetSoftwareBitmapAsync()) -ResultType ([Windows.Graphics.Imaging.SoftwareBitmap])
        $ocrBitmap = [Windows.Graphics.Imaging.SoftwareBitmap]::Convert($bitmap, [Windows.Graphics.Imaging.BitmapPixelFormat]::Gray8)
        $ocrResult = Await-WinRtResult -AsyncOperation ($engine.RecognizeAsync($ocrBitmap)) -ResultType ([Windows.Media.Ocr.OcrResult])

        $pages += [pscustomobject]@{
            page = $index + 1
            text = (($ocrResult.Text -replace "`r`n?", "`n").Trim())
        }
    } finally {
        if ($page) {
            $page.Dispose()
        }
    }
}

$pages | ConvertTo-Json -Depth 4 -Compress

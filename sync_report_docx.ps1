$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8Text([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Escape-Xml([string]$Text) {
    return [System.Security.SecurityElement]::Escape($Text)
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourcePath = Join-Path $repoRoot "BAO_CAO_DO_AN.md"
$outputPath = Join-Path $repoRoot "bao_cao_do_an_ictu_student_assistant.docx"
$tempDir = Join-Path $repoRoot "_docx_build_report"

if (-not (Test-Path $sourcePath)) {
    throw "Khong tim thay file nguon: $sourcePath"
}

if (Test-Path $tempDir) {
    Remove-Item -LiteralPath $tempDir -Recurse -Force
}

if (Test-Path $outputPath) {
    Remove-Item -LiteralPath $outputPath -Force
}

[void][System.IO.Directory]::CreateDirectory($tempDir)
[void][System.IO.Directory]::CreateDirectory((Join-Path $tempDir "_rels"))
[void][System.IO.Directory]::CreateDirectory((Join-Path $tempDir "docProps"))
[void][System.IO.Directory]::CreateDirectory((Join-Path $tempDir "word"))
[void][System.IO.Directory]::CreateDirectory((Join-Path $tempDir "word\_rels"))

$lines = [System.IO.File]::ReadAllLines($sourcePath, [System.Text.Encoding]::UTF8)
$paragraphs = New-Object System.Collections.Generic.List[string]

foreach ($line in $lines) {
    $text = $line.TrimEnd()

    if ([string]::IsNullOrWhiteSpace($text)) {
        [void]$paragraphs.Add("<w:p/>")
        continue
    }

    $escaped = Escape-Xml $text

    if ($text.StartsWith("# ")) {
        [void]$paragraphs.Add("<w:p><w:pPr><w:jc w:val=`"center`"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val=`"34`"/></w:rPr><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>")
        continue
    }

    if ($text.StartsWith("## ")) {
        [void]$paragraphs.Add("<w:p><w:r><w:rPr><w:b/><w:sz w:val=`"28`"/></w:rPr><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>")
        continue
    }

    if ($text.StartsWith("### ")) {
        [void]$paragraphs.Add("<w:p><w:r><w:rPr><w:b/><w:sz w:val=`"24`"/></w:rPr><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>")
        continue
    }

    [void]$paragraphs.Add("<w:p><w:r><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>")
}

$contentTypes = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
'@

$rels = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
'@

$core = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Bao cao do an ICTU Student Assistant</dc:title>
  <dc:creator>OpenAI Codex</dc:creator>
  <cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-03-26T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-03-26T00:00:00Z</dcterms:modified>
</cp:coreProperties>
'@

$app = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application>
</Properties>
'@

$document = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    $($paragraphs -join "`n    ")
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"@

$docRels = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
'@

Write-Utf8Text (Join-Path $tempDir "[Content_Types].xml") $contentTypes
Write-Utf8Text (Join-Path $tempDir "_rels\.rels") $rels
Write-Utf8Text (Join-Path $tempDir "docProps\core.xml") $core
Write-Utf8Text (Join-Path $tempDir "docProps\app.xml") $app
Write-Utf8Text (Join-Path $tempDir "word\document.xml") $document
Write-Utf8Text (Join-Path $tempDir "word\_rels\document.xml.rels") $docRels

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir, $outputPath)
Remove-Item -LiteralPath $tempDir -Recurse -Force

Write-Output "Da tao file DOCX: $outputPath"

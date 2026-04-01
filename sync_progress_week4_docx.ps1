$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.Drawing

function Write-Utf8Text([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Escape-Xml([string]$Text) {
    return [System.Security.SecurityElement]::Escape($Text)
}

function Resolve-MarkdownAssetPath([string]$RepoRoot, [string]$MarkdownPath) {
    $normalized = $MarkdownPath -replace '/', '\'
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $normalized))
}

function New-TextParagraph([string]$Text) {
    $escaped = Escape-Xml $Text
    return "<w:p><w:r><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>"
}

function New-HeadingParagraph([string]$Text, [int]$Size, [switch]$Center) {
    $escaped = Escape-Xml $Text
    $pPr = if ($Center) { "<w:pPr><w:jc w:val=`"center`"/></w:pPr>" } else { "" }
    return "<w:p>$pPr<w:r><w:rPr><w:b/><w:sz w:val=`"$Size`"/></w:rPr><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>"
}

function New-CaptionParagraph([string]$Text) {
    $escaped = Escape-Xml $Text
    return "<w:p><w:pPr><w:jc w:val=`"center`"/></w:pPr><w:r><w:rPr><w:i/><w:color w:val=`"475569`"/><w:sz w:val=`"20`"/></w:rPr><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>"
}

function New-ImageParagraph(
    [string]$RelationshipId,
    [string]$ImagePath,
    [string]$Name,
    [int]$DocPrId,
    [double]$TargetWidthInches = 6.2
) {
    $image = [System.Drawing.Image]::FromFile($ImagePath)
    try {
        $widthPx = [double]$image.Width
        $heightPx = [double]$image.Height
    }
    finally {
        $image.Dispose()
    }

    $widthEmu = [int64]($TargetWidthInches * 914400)
    $heightEmu = [int64]($widthEmu * ($heightPx / $widthPx))
    $escapedName = Escape-Xml $Name

    return @"
<w:p>
  <w:pPr><w:jc w:val="center"/></w:pPr>
  <w:r>
    <w:drawing>
      <wp:inline distT="0" distB="0" distL="0" distR="0">
        <wp:extent cx="$widthEmu" cy="$heightEmu"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:docPr id="$DocPrId" name="$escapedName"/>
        <wp:cNvGraphicFramePr>
          <a:graphicFrameLocks noChangeAspect="1"/>
        </wp:cNvGraphicFramePr>
        <a:graphic>
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic>
              <pic:nvPicPr>
                <pic:cNvPr id="$DocPrId" name="$escapedName"/>
                <pic:cNvPicPr/>
              </pic:nvPicPr>
              <pic:blipFill>
                <a:blip r:embed="$RelationshipId"/>
                <a:stretch><a:fillRect/></a:stretch>
              </pic:blipFill>
              <pic:spPr>
                <a:xfrm>
                  <a:off x="0" y="0"/>
                  <a:ext cx="$widthEmu" cy="$heightEmu"/>
                </a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
"@
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourcePath = Join-Path $repoRoot "BAO_CAO_TIEN_DO_TUAN_4.md"
$outputPath = Join-Path $repoRoot "bao_cao_tien_do_tuan_4_dinh_xuan_luc.docx"
$tempDir = Join-Path $repoRoot "_docx_build_progress_week4"
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

if (-not (Test-Path $sourcePath)) {
    throw "Không tìm thấy file nguồn: $sourcePath"
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
[void][System.IO.Directory]::CreateDirectory((Join-Path $tempDir "word\media"))

$lines = [System.IO.File]::ReadAllLines($sourcePath, [System.Text.Encoding]::UTF8)
$paragraphs = New-Object System.Collections.Generic.List[string]
$docRelationships = New-Object System.Collections.Generic.List[string]
$imageExtensions = New-Object System.Collections.Generic.HashSet[string]
$imageIndex = 1
$docPrId = 1

foreach ($line in $lines) {
    $text = $line.TrimEnd()

    if ([string]::IsNullOrWhiteSpace($text)) {
        [void]$paragraphs.Add("<w:p/>")
        continue
    }

    if ($text -match '^\!\[(?<alt>[^\]]*)\]\((?<path>[^)]+)\)$') {
        $alt = $Matches["alt"]
        $imageSourcePath = Resolve-MarkdownAssetPath -RepoRoot $repoRoot -MarkdownPath $Matches["path"]
        if (-not (Test-Path $imageSourcePath)) {
            throw "Không tìm thấy ảnh trong Markdown: $imageSourcePath"
        }

        $extension = [System.IO.Path]::GetExtension($imageSourcePath).TrimStart(".").ToLowerInvariant()
        [void]$imageExtensions.Add($extension)

        $mediaName = "image$imageIndex.$extension"
        $mediaTargetPath = Join-Path $tempDir "word\media\$mediaName"
        Copy-Item -LiteralPath $imageSourcePath -Destination $mediaTargetPath -Force

        $relationshipId = "rIdImage$imageIndex"
        [void]$docRelationships.Add("<Relationship Id=`"$relationshipId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image`" Target=`"media/$mediaName`"/>")
        $imageName = if ([string]::IsNullOrWhiteSpace($alt)) { $mediaName } else { $alt }
        [void]$paragraphs.Add((New-ImageParagraph -RelationshipId $relationshipId -ImagePath $imageSourcePath -Name $imageName -DocPrId $docPrId))

        if ($alt) {
            [void]$paragraphs.Add((New-CaptionParagraph $alt))
        }

        $imageIndex += 1
        $docPrId += 1
        continue
    }

    if ($text.StartsWith("# ")) {
        [void]$paragraphs.Add((New-HeadingParagraph -Text $text -Size 34 -Center))
        continue
    }

    if ($text.StartsWith("## ")) {
        [void]$paragraphs.Add((New-HeadingParagraph -Text $text -Size 28))
        continue
    }

    if ($text.StartsWith("### ")) {
        [void]$paragraphs.Add((New-HeadingParagraph -Text $text -Size 24))
        continue
    }

    [void]$paragraphs.Add((New-TextParagraph $text))
}

$contentTypeLines = @(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
    '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
    '  <Default Extension="xml" ContentType="application/xml"/>'
)

foreach ($extension in ($imageExtensions | Sort-Object)) {
    $contentType = switch ($extension) {
        "png" { "image/png" }
        "jpg" { "image/jpeg" }
        "jpeg" { "image/jpeg" }
        default { "image/$extension" }
    }
    $contentTypeLines += "  <Default Extension=`"$extension`" ContentType=`"$contentType`"/>"
}

$contentTypeLines += @(
    '  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
    '  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
    '  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    '</Types>'
)
$contentTypes = ($contentTypeLines -join "`n")

$rels = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
'@

$core = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Báo cáo tiến độ đồ án đến tuần 4</dc:title>
  <dc:creator>OpenAI Codex</dc:creator>
  <cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">$timestamp</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">$timestamp</dcterms:modified>
</cp:coreProperties>
"@

$app = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application>
</Properties>
'@

$document = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    $($paragraphs -join "`n    ")
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"@

$docRels = @(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
)

foreach ($relationship in $docRelationships) {
    $docRels += "  $relationship"
}

$docRels += '</Relationships>'
$docRelsXml = ($docRels -join "`n")

Write-Utf8Text (Join-Path $tempDir "[Content_Types].xml") $contentTypes
Write-Utf8Text (Join-Path $tempDir "_rels\.rels") $rels
Write-Utf8Text (Join-Path $tempDir "docProps\core.xml") $core
Write-Utf8Text (Join-Path $tempDir "docProps\app.xml") $app
Write-Utf8Text (Join-Path $tempDir "word\document.xml") $document
Write-Utf8Text (Join-Path $tempDir "word\_rels\document.xml.rels") $docRelsXml

[System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir, $outputPath)
Remove-Item -LiteralPath $tempDir -Recurse -Force

Write-Output "Đã tạo file DOCX: $outputPath"

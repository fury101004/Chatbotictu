$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Read-Utf8Text([string]$Path) {
    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Write-Utf8Text([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Parse-Frontmatter([string]$Path) {
    $raw = Read-Utf8Text $Path
    $lines = $raw -split "`r?`n"
    $meta = [ordered]@{}

    if ($lines.Length -gt 0 -and $lines[0] -eq "---") {
        for ($i = 1; $i -lt $lines.Length; $i++) {
            if ($lines[$i] -eq "---") { break }
            if ($lines[$i] -match "^(?<key>[^:]+):\s*(?<value>.*)$") {
                $key = $matches["key"].Trim()
                $value = $matches["value"].Trim()
                if ($value.StartsWith('"') -and $value.EndsWith('"')) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
                $meta[$key] = $value
            }
        }
    }

    return $meta
}

function Dump-Frontmatter($Meta) {
    $lines = @("---")
    foreach ($key in $Meta.Keys) {
        $escaped = $Meta[$key].ToString().Replace('"', '\"')
        $lines += ('{0}: "{1}"' -f $key, $escaped)
    }
    $lines += "---"
    return ($lines -join "`n") + "`n"
}

$repoRoot = "e:\datadoantn"
$pipelinePath = Join-Path $repoRoot "app\data\pipeline.py"
$pipelineText = Read-Utf8Text $pipelinePath
$match = [regex]::Match(
    $pipelineText,
    "FAQ_TOPIC_CONFIG = (\{.*?\n\})\n\nROUTE_HINTS",
    [System.Text.RegularExpressions.RegexOptions]::Singleline
)

if (-not $match.Success) {
    throw "Không tách được FAQ_TOPIC_CONFIG từ pipeline.py"
}

$json = $match.Groups[1].Value
$json = [regex]::Replace($json, ",(\s*[}\]])", '$1')
$config = ConvertFrom-Json $json

$topicSources = @{}
Get-ChildItem -Path (Join-Path $repoRoot "data\policy"), (Join-Path $repoRoot "data\handbook") -Recurse -Filter "*.md" | ForEach-Object {
    $meta = Parse-Frontmatter $_.FullName
    if (-not $meta.Contains("route")) { return }

    $route = $meta["route"]
    $topic = if ($route -eq "handbook") { "handbook_general" } else { $meta["topic"] }
    if ([string]::IsNullOrWhiteSpace($topic)) { return }

    if (-not $topicSources.ContainsKey($topic)) {
        $topicSources[$topic] = New-Object System.Collections.ArrayList
    }

    $entry = [pscustomobject]@{
        title = [string]$meta["title"]
        year = [string]$meta["year"]
        source_file = [string]$meta["source_file"]
        route = [string]$route
    }

    $exists = $false
    foreach ($item in $topicSources[$topic]) {
        if ($item.title -eq $entry.title -and $item.year -eq $entry.year -and $item.source_file -eq $entry.source_file) {
            $exists = $true
            break
        }
    }

    if (-not $exists) {
        [void]$topicSources[$topic].Add($entry)
    }
}

$faqDir = Join-Path $repoRoot "data\faq"
$agentLabel = "Agent Câu hỏi sinh viên thường dùng"
$createdAt = "2026-03-24"

foreach ($topicProp in $config.PSObject.Properties) {
    $topic = $topicProp.Name
    $cfg = $topicProp.Value
    $sources = @()

    if ($topicSources.ContainsKey($topic)) {
        $sources = $topicSources[$topic] |
            Sort-Object @{Expression = { if ([string]::IsNullOrWhiteSpace($_.year)) { 0 } else { [int]$_.year } }; Descending = $true }, @{Expression = { $_.title }; Descending = $true } |
            Select-Object -First 12
    }

    $meta = [ordered]@{
        doc_id = "faq_$topic"
        title = [string]$cfg.title
        route = "faq"
        agent_label = $agentLabel
        topic = $topic
        category = "faq_generated"
        source_file = "generated://faq/$topic"
        source_md = "generated://faq/$topic.md"
        source_type = "generated"
        language = "vi"
        created_at = $createdAt
    }

    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add("# $($cfg.title)")
    [void]$lines.Add("")
    [void]$lines.Add("## Khi nên hỏi agent này")
    [void]$lines.Add("")
    [void]$lines.Add("- Khi bạn hỏi một vấn đề quen thuộc, cần trả lời nhanh, dễ hiểu.")
    [void]$lines.Add("- Khi câu hỏi cần thêm năm học, đợt, học kỳ hoặc số văn bản để tra cứu sâu hơn.")
    [void]$lines.Add("")
    [void]$lines.Add("## Câu hỏi và trả lời")
    [void]$lines.Add("")

    foreach ($item in $cfg.faq_items) {
        [void]$lines.Add("**Q:** $($item.question)")
        [void]$lines.Add("")
        [void]$lines.Add("**A:**")
        [void]$lines.Add("")
        foreach ($answer in $item.answers) {
            [void]$lines.Add("- $answer")
        }
        [void]$lines.Add("")
    }

    [void]$lines.Add("## Từ khóa nên có trong câu hỏi")
    [void]$lines.Add("")
    foreach ($keyword in $cfg.keywords) {
        [void]$lines.Add("- $keyword")
    }

    [void]$lines.Add("")
    [void]$lines.Add("## Nguồn ưu tiên để đối chiếu")
    [void]$lines.Add("")

    if ($sources.Count -gt 0) {
        foreach ($source in $sources) {
            $year = if ([string]::IsNullOrWhiteSpace($source.year)) { "không rõ năm" } else { $source.year }
            $title = if ([string]::IsNullOrWhiteSpace($source.title)) { "Tài liệu không tên" } else { $source.title }
            $sourceFile = if ([string]::IsNullOrWhiteSpace($source.source_file)) { "Không rõ nguồn" } else { $source.source_file }
            [void]$lines.Add("- [$year] $title | $sourceFile")
        }
    }
    else {
        [void]$lines.Add("- Kho dữ liệu chưa có tài liệu tham chiếu cụ thể cho chủ đề này.")
    }

    [void]$lines.Add("")
    [void]$lines.Add("## Ghi chú cho chatbot")
    [void]$lines.Add("")
    [void]$lines.Add("- Nếu người dùng hỏi chưa đủ rõ, cần hỏi thêm năm học, học kỳ, khóa hoặc hệ đào tạo.")
    [void]$lines.Add("- Ưu tiên dẫn nguồn sang văn bản chính thức trong kho policy khi cần căn cứ cụ thể.")

    $content = (Dump-Frontmatter $meta) + (($lines -join "`n").TrimEnd()) + "`n"
    Write-Utf8Text (Join-Path $faqDir "$topic.md") $content
}

Get-ChildItem -Path (Join-Path $repoRoot "data") -Recurse -Filter "*.md" | ForEach-Object {
    $content = Read-Utf8Text $_.FullName
    $updated = $content.Replace("Agent So tay sinh vien", "Agent Sổ tay sinh viên")
    $updated = $updated.Replace("Agent Chinh sach - Cong van - Quyet dinh", "Agent Chính sách - Công văn - Quyết định")
    $updated = $updated.Replace("Agent Cau hoi sinh vien thuong dung", "Agent Câu hỏi sinh viên thường dùng")
    if ($updated -ne $content) {
        Write-Utf8Text $_.FullName $updated
    }
}

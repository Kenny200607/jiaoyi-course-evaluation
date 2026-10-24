param(
    [Parameter(Mandatory)][string]$DownloadDirectory,
    [Parameter(Mandatory)][string]$WorkingRoot,
    [Parameter(Mandatory)][string]$ReleaseTag,
    [Parameter(Mandatory)][string]$ExpectedCommit
)
$ErrorActionPreference = 'Stop'
$archiveName = "JiaoyiCourseEvaluation-$ReleaseTag-windows-x64.zip"
$archive = Join-Path $DownloadDirectory $archiveName
$entry = @(Get-Content -LiteralPath (Join-Path $DownloadDirectory 'SHA256SUMS.txt') | Where-Object { ($_ -split '\s+', 2)[1] -eq $archiveName })
if ($entry.Count -ne 1) { throw 'Checksum entry missing or ambiguous' }
$expectedHash = ($entry[0] -split '\s+', 2)[0]
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Checksum mismatch' }
New-Item -ItemType Directory -Path $WorkingRoot -Force | Out-Null
$evidence = Join-Path $WorkingRoot 'evidence'
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $WorkingRoot
$applicationRoot = Join-Path $WorkingRoot ([IO.Path]::GetFileNameWithoutExtension($archiveName))
$application = Join-Path $applicationRoot 'RunCourseEvaluation.exe'
$info = Get-Content -LiteralPath (Join-Path $applicationRoot 'BUILD-INFO.json') -Raw | ConvertFrom-Json
if ($info.source_commit -ne $ExpectedCommit -or $info.source_dirty -ne $false) { throw 'Build provenance mismatch' }

function Invoke-Portable([string]$Label, [string[]]$Arguments, [string]$InputText = '') {
    $start = [Diagnostics.ProcessStartInfo]::new($application)
    $start.WorkingDirectory = $WorkingRoot
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.RedirectStandardInput = $true
    $start.StandardOutputEncoding = [Text.Encoding]::UTF8
    $start.StandardErrorEncoding = [Text.Encoding]::UTF8
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -match '^(PYTHON|VIRTUAL_ENV|CONDA|GH_TOKEN$|GITHUB_TOKEN$|ACTIONS_RUNTIME_TOKEN$)') {
            $start.Environment.Remove($key) | Out-Null
        }
    }
    $start.Environment['PATH'] = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
    $start.Environment['SE_CACHE_PATH'] = Join-Path $WorkingRoot 'selenium-cache'
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    $process.Start() | Out-Null
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    $errorTask = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.WriteLine($InputText)
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(180000)) {
        $process.Kill($true)
        throw "Timed out: $Label"
    }
    $output = $outputTask.GetAwaiter().GetResult() + $errorTask.GetAwaiter().GetResult()
    [IO.File]::WriteAllText((Join-Path $evidence "$Label.txt"), $output)
    if ($process.ExitCode -ne 0) { throw "Failed: $Label (exit $($process.ExitCode)); $output" }
    Write-Host "PASS $Label"
    return $output
}

$version = Invoke-Portable -Label 'version' -Arguments @('--version')
if ($version.Trim() -ne $ReleaseTag.Substring(1)) { throw 'Application version mismatch' }
$ini = Join-Path $applicationRoot 'config.ini'
$supportsLevels = [version]$ReleaseTag.Substring(1) -ge [version]'0.1.3'
Remove-Item -LiteralPath $ini
$first = Invoke-Portable -Label 'first-run' -Arguments @() -InputText ''
if (-not (Test-Path -LiteralPath $ini) -or $first -notmatch '已建立 config.ini') { throw 'First-run setup failed' }
foreach ($browser in @('Chrome', 'Edge')) {
    [IO.File]::WriteAllText($ini, "[user-account]`nusername=`npassword=`n[browser-option]`ndriver=$browser`n")
    $check = Invoke-Portable -Label "$browser-config" -Arguments @('--check')
    $config = $check | ConvertFrom-Json
    if ($config.login -ne 'manual' -or $config.evaluation_submit -ne $false -or $config.browser -ne $browser) { throw 'Unsafe or invalid configuration defaults' }
    if ($supportsLevels) {
        if ($config.rating_level -ne 'highest') { throw 'Highest rating default missing' }
        [IO.File]::AppendAllText($ini, "`n[evaluation-option]`nrating_level=3`n")
        $selected = Invoke-Portable -Label "$browser-rating-config" -Arguments @('--check')
        if (($selected | ConvertFrom-Json).rating_level -ne 3) { throw 'Configured rating ignored' }
        $overridden = Invoke-Portable -Label "$browser-rating-override" -Arguments @('--rating-level', '5', '--check')
        if (($overridden | ConvertFrom-Json).rating_level -ne 5) { throw 'CLI rating override ignored' }
    }
    $diagnose = Invoke-Portable -Label "$browser-OCR" -Arguments @('--diagnose')
    if ($diagnose -notmatch 'model loaded successfully' -or $diagnose -notmatch 'Selenium Manager: available' -or $diagnose -notmatch 'Browser: .+ found') { throw 'Dependency or browser detection failed' }
    $browserCheck = Invoke-Portable -Label "$browser-start" -Arguments @('--check-browser')
    if ($browserCheck -notmatch 'Local browser check: PASS') { throw 'Browser startup failed' }
}
$cancel = Invoke-Portable -Label 'cancel-submit' -Arguments @('--submit') -InputText 'CANCEL'
if ($cancel -notmatch '已取消') { throw 'Submission cancellation failed' }
if ($supportsLevels -and ($cancel -notmatch '交医课程评价工具' -or $cancel -notmatch '第 3 级')) { throw 'Application title or rating summary missing' }
$result = [ordered]@{
    release = $ReleaseTag
    source_commit = $info.source_commit
    archive_sha256 = $expectedHash
    os = [Environment]::OSVersion.VersionString
    image = $env:ImageOS
    image_version = $env:ImageVersion
    checks = @('checksum', 'provenance', 'version', 'first-run', 'manual-preview-defaults', 'OCR', 'Chrome', 'Edge', 'cancel-submit', 'Unicode-space-path') + $(if ($supportsLevels) { @('highest-rating-default', 'rating-config', 'rating-cli-override', 'Chinese-title') } else { @() })
    external_python_path = $false
    dependencies_installed_by_test = $false
    school_login_or_submission = $false
    limitation = 'GitHub hosted Windows Server image contains preinstalled development software. This test removes external Python paths but is not a clean consumer Windows 10/11 certification.'
}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'result.json') -Encoding utf8
$result | ConvertTo-Json -Depth 4

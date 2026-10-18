param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [ValidateRange(5,600)][int]$TimeoutSeconds=120,
    [switch]$Worker,
    [string]$PidReceipt
)
$ErrorActionPreference='Stop'
if(-not $Worker){
    if(Test-Path -LiteralPath $OutDir){throw 'Fresh output directory required'}
    $resolvedInput=(Resolve-Path -LiteralPath $Source).Path
    $resolvedDestination=[System.IO.Path]::GetFullPath($OutDir)
    $supervisorDirectory=Join-Path ([System.IO.Path]::GetTempPath()) ('word-template-refresh-'+[guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $supervisorDirectory)
    $pidFile=Join-Path $supervisorDirectory 'owned-word-pid.txt'
    $stdoutFile=Join-Path $supervisorDirectory 'stdout.log'
    $stderrFile=Join-Path $supervisorDirectory 'stderr.log'
    $invocation="& '"+$PSCommandPath.Replace("'","''")+"' -Source '"+$resolvedInput.Replace("'","''")+"' -OutDir '"+$resolvedDestination.Replace("'","''")+"' -Worker -PidReceipt '"+$pidFile.Replace("'","''")+"'"
    $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($invocation))
    $workerProcess=Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList @('-NoProfile','-EncodedCommand',$encoded) -WindowStyle Hidden -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile -PassThru
    if(-not $workerProcess.WaitForExit($TimeoutSeconds*1000)){
        Stop-Process -Id $workerProcess.Id -ErrorAction SilentlyContinue
        if(Test-Path -LiteralPath $pidFile){
            $ownedWordId=[int](Get-Content -LiteralPath $pidFile -Raw)
            $ownedWord=Get-CimInstance Win32_Process -Filter "ProcessId=$ownedWordId"
            if($null -ne $ownedWord -and $ownedWord.CommandLine -like '*WINWORD.EXE*Automation*Embedding*'){
                Stop-Process -Id $ownedWordId -ErrorAction SilentlyContinue
            }
        }
        $timeoutReport=@{passed=$false;timed_out=$true;timeout_seconds=$TimeoutSeconds;diagnostics=$supervisorDirectory;reason='Word automation did not finish; no refresh success is claimed'}
        if(Test-Path -LiteralPath $resolvedDestination){$timeoutReport|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $resolvedDestination 'word-refresh-timeout.json') -Encoding utf8}
        throw "Word refresh timed out. Diagnostics: $supervisorDirectory"
    }
    if(Test-Path -LiteralPath $stdoutFile){Get-Content -LiteralPath $stdoutFile}
    if($workerProcess.ExitCode -ne 0){
        if(Test-Path -LiteralPath $stderrFile){Get-Content -LiteralPath $stderrFile|Write-Host}
        throw "Word refresh failed. Diagnostics: $supervisorDirectory"
    }
    exit 0
}
$sourcePath=(Resolve-Path -LiteralPath $Source).Path
if(Test-Path -LiteralPath $OutDir){throw 'Fresh output directory required'}
[void](New-Item -ItemType Directory -Path $OutDir)
$outputPath=(Resolve-Path -LiteralPath $OutDir).Path
$copyPath=Join-Path $outputPath 'word-refreshed.docx'
$sourceHash=(Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
Copy-Item -LiteralPath $sourcePath -Destination $copyPath
$app=$null; $doc=$null

function Get-Snapshot($document){
    $tables=@()
    foreach($toc in $document.TablesOfContents){
        $rows=@()
        foreach($paragraph in $toc.Range.Paragraphs){
            $rows+=@{text=$paragraph.Range.Text;style=$paragraph.Style.NameLocal;
                left_points=$paragraph.LeftIndent;first_line_points=$paragraph.FirstLineIndent}
        }
        $tables+=@{use_fields=$toc.UseFields;table_id=$toc.TableID;rows=$rows}
    }
    return @{pages=$document.ComputeStatistics(2);toc_count=$document.TablesOfContents.Count;
        tables=$tables;footnotes=$document.Footnotes.Count;hyperlinks=$document.Hyperlinks.Count}
}

function Update-Document($document){
    $results=@(@{area='main';result=$document.Fields.Update()})
    # Enumerate finite collections: some imported documents expose repeating
    # NextStoryRange COM chains. Do not traverse that chain without bounds.
    foreach($section in $document.Sections){
        foreach($header in $section.Headers){
            if($header.Exists){$results+=@{area='header';result=$header.Range.Fields.Update()}}
        }
        foreach($footer in $section.Footers){
            if($footer.Exists){$results+=@{area='footer';result=$footer.Range.Fields.Update()}}
        }
    }
    foreach($note in $document.Footnotes){$results+=@{area='footnote';result=$note.Range.Fields.Update()}}
    foreach($note in $document.Endnotes){$results+=@{area='endnote';result=$note.Range.Fields.Update()}}
    $document.Repaginate()
    foreach($toc in $document.TablesOfContents){$toc.Update()}
    $document.Repaginate()
    foreach($toc in $document.TablesOfContents){$toc.UpdatePageNumbers()}
    return ,$results
}

try {
    $app=New-Object -ComObject Word.Application
    $app.Visible=$false; $app.DisplayAlerts=0; $app.AutomationSecurity=3
    if($PidReceipt){
        Add-Type -Namespace WordTemplate -Name ProcessIdentity -MemberDefinition '[System.Runtime.InteropServices.DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr hwnd, out uint processId);'
        [uint32]$ownedPid=0
        [void][WordTemplate.ProcessIdentity]::GetWindowThreadProcessId([IntPtr]$app.Hwnd,[ref]$ownedPid)
        if($ownedPid -eq 0){throw 'Unable to identify the owned Word process'}
        [System.IO.File]::WriteAllText($PidReceipt,[string]$ownedPid)
    }
    Write-Host 'Opening verification copy'
    $doc=$app.Documents.Open($copyPath,$false,$false,$false)
    $doc.ActiveWindow.View.ShowFieldCodes=$false
    $doc.ActiveWindow.View.ShowAll=$false
    $doc.ActiveWindow.View.ShowHiddenText=$false
    Write-Host 'Recording initial snapshot'
    $before=Get-Snapshot $doc
    Write-Host 'Updating fields and TOC twice'
    $firstResults=Update-Document $doc
    $first=Get-Snapshot $doc
    $secondResults=Update-Document $doc
    $second=Get-Snapshot $doc
    $doc.Save()
    $doc.Close(0)
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc)
    $doc=$null
    Write-Host 'Reopening saved copy'
    $doc=$app.Documents.Open($copyPath,$false,$false,$false)
    $reopenBefore=Get-Snapshot $doc
    $reopenResults=Update-Document $doc
    $reopenAfter=Get-Snapshot $doc
    $doc.Save()
    $doc.ExportAsFixedFormat((Join-Path $outputPath 'word-refreshed.pdf'),17)
    $stable=(($second|ConvertTo-Json -Depth 12 -Compress) -eq ($reopenAfter|ConvertTo-Json -Depth 12 -Compress))
    $allResults=@($firstResults)+@($secondResults)+@($reopenResults)
    $fieldFailures=@($allResults | Where-Object {$_.result -ne 0})
    $report=@{source=$sourcePath;source_sha256=$sourceHash;word_version=$app.Version;
        before=$before;first=$first;second=$second;reopen_before=$reopenBefore;reopen_after=$reopenAfter;
        update_results=$allResults;field_update_failures=$fieldFailures;
        repeated_and_reopen_stable=$stable;passed=($stable -and $fieldFailures.Count -eq 0);
        output_sha256=(Get-FileHash -LiteralPath $copyPath -Algorithm SHA256).Hash;
        limitations=@('No individual click or document-edit mutation tested','PDF still requires visual inspection')}
    $report|ConvertTo-Json -Depth 15|Set-Content -LiteralPath (Join-Path $outputPath 'word-refresh-report.json') -Encoding utf8
    if((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne $sourceHash){throw 'Source changed'}
    $report|Select-Object word_version,passed,repeated_and_reopen_stable|ConvertTo-Json
    if(-not $report.passed){throw 'Word refresh failed or changed on reopen; inspect report'}
} finally {
    if($null -ne $doc){$doc.Close(0);[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc)}
    if($null -ne $app){$app.Quit();[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)}
}

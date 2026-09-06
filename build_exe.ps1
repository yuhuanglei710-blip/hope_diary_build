$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project

python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name "DiaryReplica" `
  --distpath "$project\dist" `
  --workpath "$project\build" `
  "$project\diary_query_gui.py"

Write-Host "已生成：$project\dist\DiaryReplica.exe"

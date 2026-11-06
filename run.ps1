$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv\Scripts\python.exe)) {
    py -3.12 -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "已生成 .env。请先填入 GEMINI_API_KEY 或 DASHSCOPE_API_KEY。"
}
& .\.venv\Scripts\python.exe -m floatsub

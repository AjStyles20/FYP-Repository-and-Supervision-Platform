$ErrorActionPreference = 'Stop'
$project = Join-Path $PSScriptRoot 'projecthub_slice1'
Set-Location $project
$env:DB_ENGINE = 'sqlite'
& (Join-Path $project '.venv\Scripts\python.exe') manage.py test apps --verbosity 1

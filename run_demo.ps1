# Run the app on the demo database (SQLite) instead of the real MySQL one.
#
#   .\run_demo.ps1            seed if needed, then start the server on http://127.0.0.1:8000/
#   .\run_demo.ps1 -Fresh     delete the demo database first and build the demo story again
#   .\run_demo.ps1 -NoServer  prepare the demo database without starting the server
#
# Demo accounts log in with their Baze email and the password ChangeMe123! (for example
# admin@bazeuniversity.edu.ng, coordinator@bazeuniversity.edu.ng, okoro@bazeuniversity.edu.ng,
# amina@bazeuniversity.edu.ng). The real MySQL database is not touched, and this terminal goes back to
# using MySQL when the script ends.
param([switch]$Fresh, [switch]$NoServer)

$app = Join-Path $PSScriptRoot "projecthub_slice1"
$python = Join-Path $app ".venv\Scripts\python.exe"
$database = Join-Path $app "demo.sqlite3"
$saved = @{ DB_ENGINE = $env:DB_ENGINE; SQLITE_PATH = $env:SQLITE_PATH }

Push-Location $app
try {
    $env:DB_ENGINE = "sqlite"
    $env:SQLITE_PATH = $database
    if ($Fresh -and (Test-Path $database)) { Remove-Item $database }
    & $python manage.py migrate --noinput
    & $python manage.py seed_demo --force
    if (-not $NoServer) {
        Write-Host "Demo server: http://127.0.0.1:8000/  (password ChangeMe123!; Ctrl+C to stop)"
        & $python manage.py runserver
    }
}
finally {
    $env:DB_ENGINE = $saved.DB_ENGINE
    $env:SQLITE_PATH = $saved.SQLITE_PATH
    Pop-Location
}

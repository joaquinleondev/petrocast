param(
    [Parameter(Position = 0)]
    [ValidateSet("tracking-runs", "api-offline", "api-live", "retrain-cli", "help")]
    [string] $Command = "help",

    [string] $MlflowTrackingUri = $env:MLFLOW_TRACKING_URI,
    [string] $MlflowExperimentName = $env:MLFLOW_EXPERIMENT_NAME,
    [string] $ApiBaseUrl = $env:API_BASE_URL,
    [string] $ApiKey = $env:API_KEY,
    [string] $ApiWellId = $env:API_WELL_ID,
    [string] $ApiWellWithoutFeatures = $env:API_WELL_WITHOUT_FEATURES,
    [string] $Partition = $env:PARTITION,
    [string] $DemoDir = $env:DEMO_DIR
)

$ErrorActionPreference = "Stop"

$rootDir = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$MlflowTrackingUri = if ($MlflowTrackingUri) { $MlflowTrackingUri } else { "http://localhost:5000" }
$MlflowExperimentName = if ($MlflowExperimentName) { $MlflowExperimentName } else { "petrocast-production-forecast" }
$ApiBaseUrl = if ($ApiBaseUrl) { $ApiBaseUrl } else { "http://localhost:8000" }
$ApiKey = if ($ApiKey) { $ApiKey } else { "abcdef12345" }
$ApiWellId = if ($ApiWellId) { $ApiWellId } else { "POZO-001" }
$ApiWellWithoutFeatures = if ($ApiWellWithoutFeatures) { $ApiWellWithoutFeatures } else { "POZO-003" }
$Partition = if ($Partition) { $Partition } else { "2026-01-01" }
$DemoDir = if ($DemoDir) { $DemoDir } else { Join-Path $env:TEMP "petrocast-f3-21-demo" }

function Show-Usage {
    @"
Usage:
  infra/scripts/demo/f3-21-demo-evidence.ps1 <command>

Commands:
  tracking-runs   Create two MLflow training runs with different metrics.
  api-offline     Exercise prediction API scenarios through FastAPI TestClient.
  api-live        Exercise prediction API scenarios against a running API.
  retrain-cli     Trigger the Dagster retraining asset chain by partition.

Environment/parameters:
  MLFLOW_TRACKING_URI       default: http://localhost:5000
  MLFLOW_EXPERIMENT_NAME    default: petrocast-production-forecast
  API_BASE_URL              default: http://localhost:8000
  API_KEY                   default: abcdef12345
  API_WELL_ID               default: POZO-001
  API_WELL_WITHOUT_FEATURES default: POZO-003
  PARTITION                 default: 2026-01-01
  DEMO_DIR                  default: `$env:TEMP\petrocast-f3-21-demo
"@
}

function Invoke-CheckedCommand {
    param(
        [string] $WorkingDirectory,
        [string[]] $CommandArgs
    )

    Push-Location $WorkingDirectory
    try {
        & $CommandArgs[0] @($CommandArgs[1..($CommandArgs.Count - 1)])
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $($CommandArgs -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-TrainingRun {
    param(
        [string] $Name,
        [string] $Horizons,
        [string] $FeaturesVersion
    )

    $outputDir = Join-Path $DemoDir $Name
    Remove-Item -LiteralPath $outputDir -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "==> Creating MLflow run: $Name (horizons=$Horizons)"
    Push-Location (Join-Path $rootDir "apps\ml")
    try {
        $output = & python -m uv run python -m petrocast_ml.training `
            --features-csv tests/fixtures/well_features.csv `
            --production-csv tests/fixtures/production_monthly.csv `
            --as-of 2026-01-01 `
            --horizons $Horizons `
            --features-version $FeaturesVersion `
            --output-dir $outputDir `
            --track 2>&1
        $status = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    $outputText = $output -join "`n"
    Write-Host $outputText
    if ($outputText -notmatch '"tracked_run": "[^"]+"') {
        throw "No tracked_run was produced. Is MLflow reachable at $MlflowTrackingUri?"
    }
    if ($status -ne 0) {
        Write-Host "Note: quality gates failed, but the tracked run was created for demo evidence."
    }
}

function Invoke-TrackingRuns {
    New-Item -ItemType Directory -Force -Path $DemoDir | Out-Null
    $env:MLFLOW_TRACKING_URI = $MlflowTrackingUri
    $env:MLFLOW_EXPERIMENT_NAME = $MlflowExperimentName
    if (-not $env:PETROCAST_GIT_SHA) {
        $env:PETROCAST_GIT_SHA = (& git -C $rootDir rev-parse --short HEAD).Trim()
    }

    Invoke-TrainingRun "horizon-1" "1" "f3-21-demo-h1"
    Invoke-TrainingRun "horizon-1-2-3" "1,2,3" "f3-21-demo-h123"

    Write-Host ""
    Write-Host "Open $MlflowTrackingUri and compare the two runs in experiment '$MlflowExperimentName'."
}

function Invoke-ApiOffline {
    Write-Host "==> Running offline API scenarios through FastAPI TestClient"
    Invoke-CheckedCommand `
        -WorkingDirectory (Join-Path $rootDir "apps\api") `
        -CommandArgs @("python", "-m", "uv", "run", "pytest", "tests/integration/api/v1/test_prediction.py", "-q")
}

function Invoke-ApiRequest {
    param(
        [string] $Label,
        [string] $Path
    )

    Write-Host ""
    Write-Host "==> $Label"
    Write-Host "GET $ApiBaseUrl$Path"
    & curl.exe -sS -H "X-API-Key: $ApiKey" "$ApiBaseUrl$Path" -w "`nHTTP_STATUS=%{http_code}`n"
}

function Invoke-ApiLive {
    Write-Host "==> Checking API liveness at $ApiBaseUrl"
    & curl.exe -sS "$ApiBaseUrl/health/live" -w "`nHTTP_STATUS=%{http_code}`n"

    Invoke-ApiRequest `
        "Happy path: known well, three-month horizon" `
        "/api/v1/predictions?id_well=$ApiWellId&as_of_date=2024-03-15&horizon=3"
    Invoke-ApiRequest `
        "Boundary path: prediction months cross year boundary" `
        "/api/v1/predictions?id_well=$ApiWellId&as_of_date=2024-12-31&horizon=2"
    Invoke-ApiRequest `
        "Business error: well without persisted features" `
        "/api/v1/predictions?id_well=$ApiWellWithoutFeatures&as_of_date=2024-03-15&horizon=3"
    Invoke-ApiRequest `
        "Validation error: horizon outside contract" `
        "/api/v1/predictions?id_well=$ApiWellId&as_of_date=2024-03-15&horizon=13"
}

function Invoke-RetrainCli {
    Write-Host "==> Triggering retraining_job asset chain for partition $Partition"
    Invoke-CheckedCommand `
        -WorkingDirectory (Join-Path $rootDir "apps\data") `
        -CommandArgs @(
            "python", "-m", "uv", "run", "dagster", "asset", "materialize",
            "--module-name", "petrocast_data.definitions",
            "--select", "features/well_features,ml/training_candidate,ml/model_evaluation,ml/champion_promotion",
            "--partition", $Partition
        )
}

switch ($Command) {
    "tracking-runs" { Invoke-TrackingRuns }
    "api-offline" { Invoke-ApiOffline }
    "api-live" { Invoke-ApiLive }
    "retrain-cli" { Invoke-RetrainCli }
    "help" { Show-Usage }
}

# ============================================================
#  IBM Code Engine - Deployment Script
#  Account: 54191206a31a44d6acdc2ac76f1ea72f
# ============================================================

$ACCOUNT_ID = "54191206a31a44d6acdc2ac76f1ea72f"
$REGION     = "eu-de"
$REGISTRY   = "de.icr.io"
$NAMESPACE  = "workplace-ai"
$IMAGE_NAME = "$REGISTRY/$NAMESPACE/backend:latest"
$CE_PROJECT = "workplace-ai"
$CE_APP     = "workplace-ai-backend"

# CA_API_KEY aus .env lesen (falls vorhanden), sonst manuell eingeben
$CA_API_KEY = $env:CA_API_KEY
if (-not $CA_API_KEY) {
    if (Test-Path ".env") {
        $CA_API_KEY = (Get-Content ".env" | Where-Object { $_ -match "^CA_API_KEY=" }) -replace "^CA_API_KEY=", ""
    }
}
if (-not $CA_API_KEY) {
    $CA_API_KEY = Read-Host "CA_API_KEY nicht gefunden - bitte jetzt eingeben"
}

Write-Host ""
Write-Host "=== 1/6  Login ===" -ForegroundColor Cyan
ibmcloud login --sso -a https://cloud.ibm.com -c $ACCOUNT_ID -r $REGION -g Default

Write-Host ""
Write-Host "=== 2/6  Plugins prüfen ===" -ForegroundColor Cyan
ibmcloud plugin install code-engine        --force 2>$null
ibmcloud plugin install container-registry --force 2>$null

Write-Host ""
Write-Host "=== 3/6  Container Registry - Namespace anlegen ===" -ForegroundColor Cyan
ibmcloud cr login
ibmcloud cr namespace-add $NAMESPACE 2>$null

Write-Host ""
Write-Host "=== 4/6  Docker Image bauen & pushen ===" -ForegroundColor Cyan
docker build -t $IMAGE_NAME .
docker push $IMAGE_NAME

Write-Host ""
Write-Host "=== 5/6  Code Engine Project & App deployen ===" -ForegroundColor Cyan
ibmcloud ce project create --name $CE_PROJECT 2>$null
ibmcloud ce project select --name $CE_PROJECT

# IAM API-Key fuer Registry-Pull erzeugen
$pullKeyJson = ibmcloud iam api-key-create ce-pull-key --output json
$pullKey = ($pullKeyJson | ConvertFrom-Json).apikey
ibmcloud ce registry create --name icr-access --server $REGISTRY --username iamapikey --password $pullKey 2>$null

# App erstellen oder aktualisieren
$appExists = ibmcloud ce application get --name $CE_APP 2>$null
if ($appExists) {
    Write-Host "App existiert bereits - Update wird durchgefuehrt..." -ForegroundColor Yellow
    ibmcloud ce application update --name $CE_APP --image $IMAGE_NAME --env "CA_API_KEY=$CA_API_KEY"
} else {
    ibmcloud ce application create --name $CE_APP --image $IMAGE_NAME --registry-secret icr-access --port 8000 --env "CA_API_KEY=$CA_API_KEY"
}

Write-Host ""
Write-Host "=== 6/6  App-URL abrufen ===" -ForegroundColor Cyan
$APP_URL = ibmcloud ce application get --name $CE_APP --output url

Write-Host ""
Write-Host "Deployment abgeschlossen!" -ForegroundColor Green
Write-Host "Backend-URL: $APP_URL" -ForegroundColor Green
Write-Host ""
Write-Host "Trage diese URL in script.txt (Zeile 92) ein:" -ForegroundColor Yellow
$analyzeUrl = $APP_URL + "/analyze"
Write-Host $analyzeUrl -ForegroundColor Yellow

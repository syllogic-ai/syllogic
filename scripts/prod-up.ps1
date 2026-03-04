#Requires -Version 5.1
<#
.SYNOPSIS
    Start the production stack using prebuilt Docker images.

.DESCRIPTION
    Pulls images from GHCR and starts the production Docker Compose stack.
    Requires Docker Desktop to be running.

.EXAMPLE
    .\scripts\prod-up.ps1
#>

param(
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Show-Usage {
    Write-Host "Usage: prod-up.ps1"
    Write-Host ""
    Write-Host "Starts the production stack using prebuilt Docker images from GHCR."
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Help    Show this help message"
}

if ($Help) {
    Show-Usage
    exit 0
}

# Resolve paths
$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvFile = Join-Path $RootDir "deploy\compose\.env"
$ComposeFile = Join-Path $RootDir "deploy\compose\docker-compose.yml"

# Check for .env file
if (-not (Test-Path $EnvFile)) {
    Write-Host "Missing $EnvFile." -ForegroundColor Red
    Write-Host "Copy deploy\compose\.env.example to deploy\compose\.env and edit it first."
    exit 1
}

# Check for Docker
try {
    $null = docker version 2>&1
} catch {
    Write-Host "Docker is not running or not installed." -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again."
    exit 1
}

# Check APP_VERSION
$AppVersion = "edge"
$EnvContent = Get-Content $EnvFile -ErrorAction SilentlyContinue
foreach ($line in $EnvContent) {
    if ($line -match "^APP_VERSION=(.*)$") {
        $AppVersion = $Matches[1].Trim()
    }
}

if ($AppVersion -eq "edge") {
    Write-Host "WARNING: APP_VERSION=edge is intended for development/testing." -ForegroundColor Yellow
    Write-Host "For production, pin APP_VERSION to a release tag (for example vX.Y.Z)." -ForegroundColor Yellow
    Write-Host ""
}

# Pull images
Write-Host "Pulling prebuilt images (GHCR)..." -ForegroundColor Cyan
docker compose --env-file $EnvFile -f $ComposeFile pull
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to pull images." -ForegroundColor Red
    exit 1
}

# Start stack
Write-Host "Starting production stack..." -ForegroundColor Cyan
docker compose --env-file $EnvFile -f $ComposeFile up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to start stack." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "The app should be available at the URL configured in APP_URL (default: http://localhost:8080)"

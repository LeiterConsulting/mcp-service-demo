# Docker installer and service manager for MCP Service Demo on Windows.

[CmdletBinding()]
param(
    [switch]$Help,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Status,
    [switch]$Logs,
    [switch]$Uninstall,
    [switch]$Build,
    [switch]$Open,
    [switch]$RemoveData,
    [switch]$ForceYes,
    [int]$WebPort = 0,
    [int]$SplunkPort = 0,
    [int]$TicketPort = 0,
    [int]$CatalogPort = 0,
    [string]$ProjectName = "",
    [int]$WaitSeconds = 60
)

$ErrorActionPreference = "Stop"
$Version = "0.9.1"
$AppName = "MCP Service Demo"
$InstallDir = $PSScriptRoot
$EnvFile = Join-Path $InstallDir ".env"
$ComposeCommand = $null
$ComposePrefix = @()

function Write-Info {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Green
}

function Write-WarningMessage {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Yellow
}

function Write-ErrorMessage {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Red
}

function Show-HelpText {
    Write-Host "$AppName v$Version" -ForegroundColor Green
    Write-Host ""
    Write-Info "USAGE:"
    Write-Host "    .\install.ps1 [COMMAND] [OPTIONS]"
    Write-Host ""
    Write-Info "COMMANDS:"
    Write-Host "    (no command)          Prepare, build, and start the complete demo"
    Write-Host "    -Start                Start existing services (build if needed)"
    Write-Host "    -Stop                 Stop services and preserve containers/settings"
    Write-Host "    -Restart              Restart services"
    Write-Host "    -Status               Show service and health status"
    Write-Host "    -Logs                 Follow service logs"
    Write-Host "    -Uninstall            Remove containers and local image; preserve data"
    Write-Host "    -Help                 Show this help message"
    Write-Host ""
    Write-Info "OPTIONS:"
    Write-Host "    -Build                Rebuild images with -Start or -Restart"
    Write-Host "    -Open                 Open the demo in the default browser after startup"
    Write-Host "    -WebPort PORT         Publish the web interface on PORT (default 8100)"
    Write-Host "    -SplunkPort PORT      Publish Splunk MCP on PORT (default 8101)"
    Write-Host "    -TicketPort PORT      Publish Ticket MCP on PORT (default 8102)"
    Write-Host "    -CatalogPort PORT     Publish Catalog MCP on PORT (default 8103)"
    Write-Host "    -ProjectName NAME     Set a persistent Compose project name"
    Write-Host "    -WaitSeconds N        Startup health timeout (default 60)"
    Write-Host "    -RemoveData           With -Uninstall, also remove settings and tickets"
    Write-Host "    -ForceYes             Skip the -RemoveData confirmation"
    Write-Host ""
    Write-Info "EXAMPLES:"
    Write-Host "    .\install.ps1"
    Write-Host "    .\install.ps1 -Open"
    Write-Host "    .\install.ps1 -WebPort 8200 -ProjectName customer-demo"
    Write-Host "    .\install.ps1 -Restart -Build"
    Write-Host "    .\install.ps1 -Logs"
    Write-Host "    .\install.ps1 -Uninstall"
    Write-Host ""
    Write-Info "NOTES:"
    Write-Host "    Docker Desktop or Docker Engine with Compose v2 is recommended."
    Write-Host "    Port and project-name options are saved in .env. Existing .env values"
    Write-Host "    and browser-saved Splunk/LLM settings are otherwise preserved."
}

function Test-PortValue {
    param([string]$Name, [int]$Value)
    if ($Value -lt 0 -or $Value -gt 65535) {
        throw "$Name must be an integer from 1 to 65535."
    }
}

function Test-Options {
    $commands = @($Help, $Start, $Stop, $Restart, $Status, $Logs, $Uninstall) | Where-Object { $_ }
    if ($commands.Count -gt 1) {
        throw "Choose only one command."
    }

    Test-PortValue -Name "-WebPort" -Value $WebPort
    Test-PortValue -Name "-SplunkPort" -Value $SplunkPort
    Test-PortValue -Name "-TicketPort" -Value $TicketPort
    Test-PortValue -Name "-CatalogPort" -Value $CatalogPort

    if ($WaitSeconds -lt 5 -or $WaitSeconds -gt 300) {
        throw "-WaitSeconds must be an integer from 5 to 300."
    }
    if ($ProjectName -and $ProjectName -notmatch '^[a-z0-9][a-z0-9_-]*$') {
        throw "-ProjectName must start with a lowercase letter or digit and contain only lowercase letters, digits, hyphens, or underscores."
    }
    if ($RemoveData -and -not $Uninstall) {
        throw "-RemoveData is only valid with -Uninstall."
    }
}

function Initialize-RuntimeFiles {
    if (-not (Test-Path $EnvFile)) {
        Copy-Item (Join-Path $InstallDir ".env.example") $EnvFile
        Write-Success "Created .env from .env.example"
    }
    $certsPath = Join-Path $InstallDir "certs"
    if (-not (Test-Path $certsPath)) {
        New-Item -Path $certsPath -ItemType Directory | Out-Null
    }
}

function Set-EnvValue {
    param([string]$Key, [string]$Value)

    $lines = @()
    if (Test-Path $EnvFile) {
        $lines = @(Get-Content $EnvFile)
    }
    $found = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index].StartsWith("$Key=")) {
            $lines[$index] = "$Key=$Value"
            $found = $true
        }
    }
    if (-not $found) {
        $lines += "$Key=$Value"
    }
    [System.IO.File]::WriteAllLines(
        $EnvFile,
        [string[]]$lines,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

function Save-Overrides {
    if ($WebPort -gt 0) { Set-EnvValue -Key "DEMO_WEB_PORT" -Value "$WebPort" }
    if ($SplunkPort -gt 0) { Set-EnvValue -Key "SPLUNK_MCP_PORT" -Value "$SplunkPort" }
    if ($TicketPort -gt 0) { Set-EnvValue -Key "TICKET_MCP_PORT" -Value "$TicketPort" }
    if ($CatalogPort -gt 0) { Set-EnvValue -Key "CATALOG_MCP_PORT" -Value "$CatalogPort" }
    if ($ProjectName) { Set-EnvValue -Key "COMPOSE_PROJECT_NAME" -Value $ProjectName }
}

function Get-EnvValue {
    param([string]$Key, [string]$Fallback)

    $result = $null
    foreach ($line in @(Get-Content $EnvFile)) {
        if ($line.StartsWith("$Key=")) {
            $result = $line.Substring($Key.Length + 1).Trim('"').Trim("'")
        }
    }
    if ([string]::IsNullOrWhiteSpace($result)) { return $Fallback }
    return $result
}

function Initialize-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker was not found. Install Docker Desktop or Docker Engine, then run this installer again."
    }

    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker is installed but its engine is not running. Start Docker and try again."
    }

    & docker compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        $script:ComposeCommand = "docker"
        $script:ComposePrefix = @("compose")
        return
    }

    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        $script:ComposeCommand = "docker-compose"
        $script:ComposePrefix = @()
        Write-WarningMessage "Using legacy docker-compose; Docker Compose v2 is recommended."
        return
    }
    throw "Docker Compose was not found. Install the Compose plugin and try again."
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    Push-Location $InstallDir
    try {
        $arguments = $script:ComposePrefix + $ComposeArgs
        & $script:ComposeCommand @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose exited with code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

function Get-ComposeOutput {
    param([string[]]$ComposeArgs)
    Push-Location $InstallDir
    try {
        $arguments = $script:ComposePrefix + $ComposeArgs
        $output = & $script:ComposeCommand @arguments 2>$null
        if ($LASTEXITCODE -ne 0) { return "" }
        return ($output | Out-String).Trim()
    } finally {
        Pop-Location
    }
}

function Get-WebUrl {
    $port = Get-EnvValue -Key "DEMO_WEB_PORT" -Fallback "8100"
    return "http://127.0.0.1:$port"
}

function Wait-DemoHealth {
    $containerId = Get-ComposeOutput -ComposeArgs @("ps", "-q", "demo")
    if (-not $containerId) {
        Write-ErrorMessage "The demo container was not created."
        Invoke-Compose -ComposeArgs @("logs", "--tail", "80", "demo")
        throw "Demo startup failed."
    }

    $elapsed = 0
    while ($elapsed -lt $WaitSeconds) {
        $health = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId 2>$null | Out-String).Trim()
        if ($health -eq "healthy") {
            Write-Success "Demo is healthy."
            return
        }
        if ($health -in @("unhealthy", "exited", "dead")) {
            Write-ErrorMessage "Demo entered state: $health"
            Invoke-Compose -ComposeArgs @("logs", "--tail", "80", "demo")
            throw "Demo startup failed."
        }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }

    Write-ErrorMessage "Demo did not become healthy within $WaitSeconds seconds."
    Invoke-Compose -ComposeArgs @("logs", "--tail", "80", "demo")
    throw "Demo startup timed out."
}

function Show-Ready {
    $url = Get-WebUrl
    Write-Host ""
    Write-Success "$AppName is ready."
    Write-Info "Web interface: $url"
    Write-Info "Setup: use the gear menu to configure Splunk, the LLM, and audience."
    Write-Info "Logs: .\install.ps1 -Logs"
    if ($Open) { Start-Process $url }
}

function Install-Demo {
    Write-Info "Building and starting the complete MCP demo..."
    Invoke-Compose -ComposeArgs @("up", "--detach", "--build", "--remove-orphans")
    Wait-DemoHealth
    Show-Ready
}

function Start-Demo {
    Write-Info "Starting the MCP demo..."
    $arguments = @("up", "--detach", "--remove-orphans")
    if ($Build) { $arguments += "--build" }
    Invoke-Compose -ComposeArgs $arguments
    Wait-DemoHealth
    Show-Ready
}

function Stop-Demo {
    Write-Info "Stopping the MCP demo..."
    Invoke-Compose -ComposeArgs @("stop")
    Write-Success "Services stopped. Settings and ticket data were preserved."
}

function Restart-Demo {
    Write-Info "Restarting the MCP demo..."
    if ($Build) {
        Invoke-Compose -ComposeArgs @("up", "--detach", "--build", "--force-recreate", "--remove-orphans")
    } else {
        Invoke-Compose -ComposeArgs @("restart")
    }
    Wait-DemoHealth
    Show-Ready
}

function Show-DemoStatus {
    Invoke-Compose -ComposeArgs @("ps")
    $containerId = Get-ComposeOutput -ComposeArgs @("ps", "-q", "demo")
    if (-not $containerId) {
        Write-WarningMessage "Demo is not running."
        exit 1
    }
    $health = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId 2>$null | Out-String).Trim()
    if ($health -eq "healthy") {
        Write-Success "Demo is healthy: $(Get-WebUrl)"
        return
    }
    Write-WarningMessage "Demo health: $health"
    exit 1
}

function Uninstall-Demo {
    $arguments = @("down", "--remove-orphans", "--rmi", "local")
    if ($RemoveData) {
        if (-not $ForceYes) {
            Write-WarningMessage "This will permanently remove this Compose project's tickets and encrypted Splunk/LLM settings."
            $confirmation = Read-Host "Type REMOVE to continue"
            if ($confirmation -ne "REMOVE") {
                Write-Info "Uninstall cancelled."
                return
            }
        }
        $arguments += "--volumes"
    }

    Invoke-Compose -ComposeArgs $arguments
    if ($RemoveData) {
        Write-Success "Containers, local image, and this project's persistent demo data were removed."
    } else {
        Write-Success "Containers and local image were removed. Settings and ticket data were preserved."
    }
    Write-Info "The cloned source and .env remain in $InstallDir"
}

try {
    Test-Options
    if ($Help) {
        Show-HelpText
        exit 0
    }

    Initialize-RuntimeFiles
    Save-Overrides
    Initialize-Docker

    if ($Start) { Start-Demo }
    elseif ($Stop) { Stop-Demo }
    elseif ($Restart) { Restart-Demo }
    elseif ($Status) { Show-DemoStatus }
    elseif ($Logs) { Invoke-Compose -ComposeArgs @("logs", "--follow", "--tail", "150") }
    elseif ($Uninstall) { Uninstall-Demo }
    else { Install-Demo }
} catch {
    Write-ErrorMessage $_.Exception.Message
    exit 1
}

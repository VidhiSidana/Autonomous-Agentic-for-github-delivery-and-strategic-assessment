# ==============================================================================
# Samsung PRISM Unified Engineering Agent - Windows PowerShell Setup Script
# ==============================================================================
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "=== Samsung PRISM Engineering Agent Setup (Windows) ===" -ForegroundColor Cyan
Write-Host "Project Directory: $ProjectRoot"

# 1. Check Python version (>= 3.11 required)
$PythonBin = $null
foreach ($cmd in @("python", "py -3.14", "py -3.13", "py -3.12", "py -3.11")) {
    try {
        $verCheck = & ($cmd.Split()[0]) ($cmd.Split()[1..($cmd.Split().Length-1)]) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($verCheck -match "^3\.(1[1-9])") {
            $PythonBin = $cmd
            Write-Host "[OK] Found compatible Python: $cmd (v$verCheck)" -ForegroundColor Green
            break
        }
    } catch {
        # continue checking
    }
}

if (-not $PythonBin) {
    Write-Error "Python 3.11 or higher is required. Please install Python 3.11+ from https://python.org"
    exit 1
}

# 2. Virtual Environment Setup
$VenvDir = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment at $VenvDir..."
    & ($PythonBin.Split()[0]) ($PythonBin.Split()[1..($PythonBin.Split().Length-1)]) -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
Write-Host "[OK] Virtual environment ready: $VenvDir" -ForegroundColor Green

# 3. Install Package and Dependencies
Write-Host "Installing package in editable mode..."
& $VenvPip install --upgrade pip
& $VenvPip install -e $ProjectRoot

# 4. Smoke Test CLI Entry Point
Write-Host "Verifying 'prism-agent' CLI entry point..."
$AgentExe = Join-Path $VenvDir "Scripts\prism-agent.exe"
if (Test-Path $AgentExe) {
    & $AgentExe --version
    Write-Host "[OK] CLI entry point verified successfully." -ForegroundColor Green
} else {
    & $VenvPython -m agent.main --version
    Write-Host "[OK] Module execution verified successfully." -ForegroundColor Green
}

# 5. Check Local LLM (Ollama)
Write-Host "Checking Ollama daemon..."
try {
    $ollamaCheck = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop
    Write-Host "[OK] Ollama is active on http://localhost:11434" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Ollama daemon is not responding on http://localhost:11434." -ForegroundColor Yellow
    Write-Host "          Start Ollama with: ollama serve"
}

# 6. Check REA / Reverse Engineering Prerequisites
Write-Host "Checking REA prerequisites..."
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = & node -v
    Write-Host "  Node.js: $nodeVer"
} else {
    Write-Host "  Node.js: Not found"
}

if ((Get-Command ghidra -ErrorAction SilentlyContinue) -or ($env:GHIDRA_INSTALL_DIR)) {
    Write-Host "  Ghidra: Installed"
} else {
    Write-Host "  Ghidra: Not installed (agent will use verified pefile + Capstone fallback)"
}

Write-Host ""
Write-Host "=== Setup Complete! ===" -ForegroundColor Cyan
Write-Host "To activate the environment:"
Write-Host "  $VenvDir\Scripts\Activate.ps1"
Write-Host "To run tests:"
Write-Host "  python -m unittest discover -s tests -p 'test_*.py' -t ."
Write-Host "To run the agent:"
Write-Host "  prism-agent --help"


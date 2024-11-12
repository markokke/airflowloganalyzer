# PowerShell Script for Windows 11 Linting Setup

# Enable color output
$Green = "$([char]0x1b)[32m"
$Blue = "$([char]0x1b)[34m"
$Reset = "$([char]0x1b)[0m"

Write-Host "${Blue}Setting up Python virtual environment...${Reset}"

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

# Activate virtual environment
Write-Host "${Blue}Activating virtual environment...${Reset}"
.\.venv\Scripts\Activate.ps1

# Install required packages
Write-Host "${Blue}Installing linting packages...${Reset}"
python -m pip install --upgrade pip
pip install black flake8 pylint isort pre-commit

# Create requirements-dev.txt if it doesn't exist
if (-not (Test-Path "requirements-dev.txt")) {
    Write-Host "${Blue}Creating requirements-dev.txt...${Reset}"
    @"
black==23.12.1
flake8==7.0.0
pylint==3.0.3
isort==5.13.2
pre-commit==3.6.0
"@ | Out-File -FilePath "requirements-dev.txt" -Encoding UTF8
}

# Create run_linters.bat
Write-Host "${Blue}Creating linter batch file...${Reset}"
@"
@echo off
call .venv\Scripts\activate.bat
python run_linters.py
pause
"@ | Out-File -FilePath "run_linters.bat" -Encoding UTF8

# Set up pre-commit if git is initialized
if (Test-Path ".git") {
    Write-Host "${Blue}Setting up pre-commit hooks...${Reset}"
    pre-commit install
}

Write-Host "${Green}Setup complete! You can now run 'run_linters.bat' to lint your code.${Reset}"

# Show usage instructions
Write-Host "`nUsage:"
Write-Host "${Blue}1. To activate the virtual environment:${Reset}"
Write-Host "   .\.venv\Scripts\Activate.ps1"
Write-Host "${Blue}2. To run the linters:${Reset}"
Write-Host "   .\run_linters.bat"
Write-Host "${Blue}3. Git commits will now automatically run the linters${Reset}"
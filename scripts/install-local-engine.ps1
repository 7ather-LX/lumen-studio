# Manual local-engine installer for developers.
# The packaged app performs the same steps from the "Models" screen.
param(
    [ValidateSet("auto", "cuda", "cpu")]
    [string]$Variant = "auto",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $venv = Join-Path $root ".venv\Scripts\python.exe"
    $Python = if (Test-Path $venv) { $venv } else { "python" }
}

if ($Variant -eq "auto") {
    $Variant = if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { "cuda" } else { "cpu" }
}
$index = if ($Variant -eq "cuda") { "https://download.pytorch.org/whl/cu128" } else { "https://download.pytorch.org/whl/cpu" }

Write-Host "Installing PyTorch ($Variant) into $Python"
& $Python -m pip install --upgrade torch torchvision --index-url $index
if ($LASTEXITCODE -ne 0) { throw "PyTorch installation failed" }

Write-Host "Installing Diffusers stack"
& $Python -m pip install --upgrade "diffusers>=0.31" "transformers>=4.44" "accelerate>=1.0" "safetensors>=0.4"
if ($LASTEXITCODE -ne 0) { throw "Diffusers installation failed" }

Write-Host "Verifying"
& $Python -c "import torch, diffusers; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'diffusers', diffusers.__version__)"

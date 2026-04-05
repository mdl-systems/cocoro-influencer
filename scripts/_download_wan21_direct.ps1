# Wan 2.1 I2V 14B-480P 直接ダウンロード
# HuggingFace APIを使わず、直接URLでダウンロード

$baseUrl = "https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/resolve/main"
$targetDir = "F:\ComfyUI\models\diffusion_models\Wan2.1-I2V-14B-480P"
$ProgressPreference = 'SilentlyContinue'

New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

$files = @(
    "diffusion_pytorch_model-00001-of-00007.safetensors",
    "diffusion_pytorch_model-00002-of-00007.safetensors",
    "diffusion_pytorch_model-00003-of-00007.safetensors",
    "diffusion_pytorch_model-00004-of-00007.safetensors",
    "diffusion_pytorch_model-00005-of-00007.safetensors",
    "diffusion_pytorch_model-00006-of-00007.safetensors",
    "diffusion_pytorch_model-00007-of-00007.safetensors",
    "diffusion_pytorch_model.safetensors.index.json",
    "config.json"
)

$total = $files.Count
$i = 0

foreach ($file in $files) {
    $i++
    $outPath = Join-Path $targetDir $file
    
    if (Test-Path $outPath) {
        $size = [math]::Round((Get-Item $outPath).Length / 1GB, 2)
        if ($size -gt 0.1) {
            Write-Host "[$i/$total] SKIP (${size}GB exists): $file"
            continue
        }
    }
    
    Write-Host "[$i/$total] Downloading: $file"
    $url = "$baseUrl/$file"
    
    try {
        Invoke-WebRequest -Uri $url -OutFile $outPath -UseBasicParsing
        $size = [math]::Round((Get-Item $outPath).Length / 1GB, 2)
        Write-Host "  OK (${size}GB)"
    } catch {
        Write-Host "  FAILED: $_"
    }
}

Write-Host ""
Write-Host "=== Downloaded files ==="
Get-ChildItem $targetDir -File | Select-Object @{N="GB";E={[math]::Round($_.Length/1GB,2)}},Name | Sort-Object GB -Desc

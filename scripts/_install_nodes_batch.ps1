# ComfyUI カスタムノード一括インストール
$customNodesDir = "F:\ComfyUI\custom_nodes"

$nodes = @(
    @{ Name = "ComfyUI_Comfyroll_CustomNodes"; Repo = "https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git" },
    @{ Name = "ComfyUI-Impact-Pack"; Repo = "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git" },
    @{ Name = "comfyui_controlnet_aux"; Repo = "https://github.com/Fannovel16/comfyui_controlnet_aux.git" },
    @{ Name = "ComfyUI-KJNodes"; Repo = "https://github.com/kijai/ComfyUI-KJNodes.git" },
    @{ Name = "ComfyUI-WanVideoWrapper"; Repo = "https://github.com/kijai/ComfyUI-WanVideoWrapper.git" },
    @{ Name = "ComfyUI-LivePortraitKJ"; Repo = "https://github.com/kijai/ComfyUI-LivePortraitKJ.git" },
    @{ Name = "ComfyUI_IPAdapter_plus"; Repo = "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git" },
    @{ Name = "ComfyUI-Advanced-ControlNet"; Repo = "https://github.com/Kosinkadink/ComfyUI-Advanced-ControlNet.git" },
    @{ Name = "ComfyUI-CogVideoXWrapper"; Repo = "https://github.com/kijai/ComfyUI-CogVideoXWrapper.git" }
)

$total = $nodes.Count
$i = 0

foreach ($node in $nodes) {
    $i++
    $targetDir = Join-Path $customNodesDir $node.Name
    
    if (Test-Path $targetDir) {
        Write-Host "[$i/$total] SKIP (exists): $($node.Name)"
    } else {
        Write-Host "[$i/$total] CLONE: $($node.Name)"
        git clone $node.Repo $targetDir 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0 -or (Test-Path $targetDir)) {
            Write-Host "  OK"
        } else {
            Write-Host "  FAILED"
        }
    }
}

Write-Host ""
Write-Host "=== Installed Nodes ==="
Get-ChildItem $customNodesDir -Directory -Name | Where-Object { $_ -ne "__pycache__" }

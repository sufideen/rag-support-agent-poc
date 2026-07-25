# Run from: C:\Users\sufyandg\source\repos\rag-support-agent-poc
#
# Provisions Python (venv + requirements.txt) on the disposable vm-rag-test VM
# via `az vm run-command invoke`, since the VM has no public IP and no
# SSH/Bastion access. Both requirements.txt and provision-test-vm-python.sh
# are base64-packaged locally and decoded on the VM, because run-command has
# no file-copy channel of its own.
#
# Usage:
#   .\infra\scripts\provision-test-vm-python.ps1 -ResourceGroup <rg> [-VmName vm-rag-test]

param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [string]$VmName = "vm-rag-test"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$requirementsPath = Join-Path $repoRoot "requirements.txt"
$provisionScriptPath = Join-Path $PSScriptRoot "provision-test-vm-python.sh"

# Force LF regardless of local git/checkout line-ending settings — these run
# through bash on the VM, and a CRLF-mangled `set -euo pipefail` line fails
# with "pipefail\r: invalid option name".
function Get-Utf8BytesWithLf([string]$Path) {
    $text = (Get-Content -Path $Path -Raw) -replace "`r`n", "`n"
    return [System.Text.Encoding]::UTF8.GetBytes($text)
}

$requirementsB64 = [Convert]::ToBase64String((Get-Utf8BytesWithLf $requirementsPath))
$provisionScriptB64 = [Convert]::ToBase64String((Get-Utf8BytesWithLf $provisionScriptPath))

# Passed as separate --scripts arguments (one per line), not a single
# multi-line string — on Windows, az is a .cmd wrapper, and a single argument
# containing embedded newlines gets mangled going through cmd.exe's argument
# handling, silently producing an empty script.
$remoteScriptLines = @(
    "echo $requirementsB64 | base64 -d > /tmp/requirements.txt"
    "echo $provisionScriptB64 | base64 -d > /tmp/provision-test-vm-python.sh"
    "bash /tmp/provision-test-vm-python.sh"
)

az vm run-command invoke `
    --resource-group $ResourceGroup `
    --name $VmName `
    --command-id RunShellScript `
    --scripts $remoteScriptLines

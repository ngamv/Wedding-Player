param(
    [ValidatePattern('^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$Heure = '09:15'
)

$ErrorActionPreference = 'Stop'
$Projet = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $Projet '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = & py -3.12 -c 'import sys; print(sys.executable)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 requis.' }
}
$Nom = 'ORION - Brief CEO'
if (Get-ScheduledTask -TaskName $Nom -ErrorAction SilentlyContinue) {
    throw 'La tache existe deja. Modifiez son horaire dans le Planificateur de taches.'
}
$Action = New-ScheduledTaskAction -Execute $Python -WorkingDirectory $Projet -Argument '-m backend.ceo_digest'
$Declencheur = New-ScheduledTaskTrigger -Daily -At $Heure
$Utilisateur = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $Utilisateur -LogonType Interactive
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName $Nom -Action $Action -Trigger $Declencheur -Principal $Principal -Settings $Settings | Out-Null
Write-Output "Brief CEO programme a $Heure, heure du PC."

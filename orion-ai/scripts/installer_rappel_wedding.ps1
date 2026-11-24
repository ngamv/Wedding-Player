param(
    [ValidatePattern('^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$Heure = '09:00'
)
$ErrorActionPreference = 'Stop'
$Projet = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = & py -3.12 -c 'import sys; print(sys.executable)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 requis.' }
$Rapport = Join-Path $Projet 'memory\wedding-rappels.json'
$Nom = 'ORION Wedding - Rappels'
if (Get-ScheduledTask -TaskName $Nom -ErrorAction SilentlyContinue) {
    throw 'Ce rappel existe deja. Changez son horaire dans le Planificateur de taches.'
}
$Action = New-ScheduledTaskAction -Execute $Python -WorkingDirectory $Projet -Argument ('-m backend.wedding_digest --jours 7 --sortie "{0}"' -f $Rapport)
$Declencheur = New-ScheduledTaskTrigger -Daily -At $Heure
$Utilisateur = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $Utilisateur -LogonType Interactive
Register-ScheduledTask -TaskName $Nom -Action $Action -Trigger $Declencheur -Principal $Principal | Out-Null
Write-Output ('Rappel programme. Rapport : ' + $Rapport)

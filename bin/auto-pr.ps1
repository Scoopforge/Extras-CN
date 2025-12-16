#Requires -Version 5.1
param(
    # overwrite upstream param
    [String]$upstream = 'scoopforge/main-plus:main'
)

if (!$env:SCOOP_HOME) { $env:SCOOP_HOME = Convert-Path (scoop prefix scoop) }
$autopr = "$env:SCOOP_HOME/bin/auto-pr.ps1"
$dir = "$PSScriptRoot/../bucket"
& $autopr -Dir $dir -Upstream $Upstream @Args

if (!$env:SCOOP_HOME) { $env:SCOOP_HOME = Convert-Path (scoop prefix scoop) }
$formatjson = "$env:SCOOP_HOME/bin/formatjson.ps1"
$path = "$PSScriptRoot/../bucket"
& $formatjson -Dir $path @Args

param(
    [string]$TimelinePath = "content/timeline.json",
    [string]$OutputDirectory = "artifacts/audio",
    [string]$VoiceName = "Microsoft Heami Desktop",
    [int]$Rate = 0
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$timeline = Get-Content -Raw -Encoding UTF8 $TimelinePath | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

foreach ($segment in $timeline.segments) {
    $fileName = "segment-{0:D2}.wav" -f [int]$segment.id
    $outputPath = Join-Path $OutputDirectory $fileName
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try {
        $synth.SelectVoice($VoiceName)
        $synth.Rate = $Rate
        $synth.Volume = 100
        $synth.SetOutputToWaveFile($outputPath)
        $synth.Speak([string]$segment.text)
    }
    finally {
        $synth.Dispose()
    }
    Write-Output $outputPath
}

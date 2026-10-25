# Pulpit Binder booth test: can a program jump a running PowerPoint show and see which slide is up?
# Nothing is changed in the file.
#   1. Open the Sunday deck in PowerPoint and start the slide show (F5) as usual.
#   2. Right-click this file and choose "Run with PowerShell". Type a slide number when asked.
#   3. The show should jump to that slide. Then click through the show for about 20 seconds;
#      this window prints each slide as it changes. It stays open until you press Enter.
param([int]$Slide = 0, [int]$WatchSeconds = 20)

function Finish($msg) { if ($msg) { Write-Host $msg }; Write-Host ""; Read-Host "Press Enter to close this window" | Out-Null; exit }

try {
  try { $app = [Runtime.InteropServices.Marshal]::GetActiveObject("PowerPoint.Application") }
  catch { Finish "PowerPoint is not open (or it is open as a different user, such as 'Run as administrator'). Open PowerPoint and try again." }

  if ($app.SlideShowWindows.Count -lt 1) { Finish "PowerPoint is open but no slide show is running. Press F5 in PowerPoint, then run this again." }
  $view = $app.SlideShowWindows.Item(1).View
  $total = $app.SlideShowWindows.Item(1).Presentation.Slides.Count
  Write-Host ("Show found. On slide {0} of {1}." -f $view.CurrentShowPosition, $total)

  if ($Slide -le 0) { $typed = Read-Host "Which slide number should I jump to? (press Enter to skip)"; if ($typed -match '^\d+$') { $Slide = [int]$typed } }
  if ($Slide -gt 0) {
    if ($Slide -gt $total) { Finish "That deck only has $total slides." }
    $view.GotoSlide($Slide)
    Write-Host "Asked PowerPoint to go to slide $Slide. Look at the projector window."
  }

  Write-Host "Watching for $WatchSeconds seconds. Click through the show now."
  $last = -1; $end = (Get-Date).AddSeconds($WatchSeconds)
  while ((Get-Date) -lt $end) {
    $pos = $app.SlideShowWindows.Item(1).View.CurrentShowPosition
    if ($pos -ne $last) { Write-Host ("{0:HH:mm:ss}  slide {1}" -f (Get-Date), $pos); $last = $pos }
    Start-Sleep -Milliseconds 200
  }
  Finish "Done."
}
catch { Finish ("Something went wrong: " + $_.Exception.Message) }

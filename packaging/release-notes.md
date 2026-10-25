## Install

1. Download **SDM-Setup-<version>.exe** below and run it. It installs for your Windows account
   only and needs no administrator rights. Windows SmartScreen may warn that the publisher is
   unknown (SDM isn't code-signed): choose **More info**, then **Run anyway**.
2. SDM's welcome assistant connects your browsers.
3. Get the browser extension:
   - Chrome, Brave and other Chromium browsers: unzip **sdm-chromium-<version>.zip** to a folder
     you'll keep, open `chrome://extensions`, turn on Developer mode and choose Load unpacked.
   - Edge: from Microsoft Edge Add-ons, or the same way as Chrome.
   - Firefox: from Firefox Add-ons.

Optional, for converting and video pages (both free; then restart SDM):
`winget install Gyan.FFmpeg` and `winget install yt-dlp.yt-dlp`. Video pages are off until
you turn them on in Tools > Settings > Media.

No installer wanted? **SDM-<version>-portable.zip** is the same program as a folder: unzip it
and run `SDM.exe`.

Check a download: `Get-FileHash .\SDM-Setup-<version>.exe` in PowerShell must print the
checksum listed below.

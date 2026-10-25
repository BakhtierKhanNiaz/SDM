## Install

1. Download **SDM-Setup-<version>.exe** below and run it. It installs for your Windows account
   only and needs no administrator rights. Windows SmartScreen may warn that the publisher is
   unknown (SDM isn't code-signed): choose **More info**, then **Run anyway**.
2. SDM's welcome assistant connects your browsers. For each one, press **Add to Chrome** (or
   Edge, Brave) and follow the three steps it shows: the extension comes with SDM, so there's
   nothing else to download. Later: **Help > Add the browser extension**.
3. Optional: in the extension's panel, tick **Show the SDM button on videos**.
4. Firefox: from Firefox Add-ons (Firefox 128 or newer).

Optional, for converting and video pages (both free; then restart SDM):
`winget install Gyan.FFmpeg` and `winget install yt-dlp.yt-dlp`. Video pages are off until
you turn them on in Tools > Settings > Media.

No installer wanted? **SDM-<version>-portable.zip** is the same program as a folder: unzip it
and run `SDM.exe`. **sdm-chromium-<version>.zip** is the extension on its own.

Check a download: `Get-FileHash .\SDM-Setup-<version>.exe` in PowerShell must print the
checksum listed below.

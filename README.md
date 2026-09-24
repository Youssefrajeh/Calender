# Calendar wallpaper for Lively

Files: `index.html` (the wallpaper), `gcal_server.py` (Google Calendar bridge), `LivelyInfo.json`, `LivelyProperties.json`.

## 1. One-time Google setup (free)
1. Go to https://console.cloud.google.com, create a project.
2. **APIs & Services > Library**: enable **Google Calendar API**.
3. **OAuth consent screen**: External, add yourself under **Test users** (stay in Testing mode).
4. **Credentials > Create credentials > OAuth client ID > Desktop app**. Download the JSON.
5. Save it as `D:\Calender\client_secret.json`.

## 2. Sign in
```
python D:\Calender\gcal_server.py
```
Your browser opens, sign in and allow access. A `token.json` is saved; the helper then keeps running on `127.0.0.1:8765`.
(In Testing mode Google may expire the token after 7 days; re-run with `--login` if events stop loading.)

## 3. Add to Lively
Lively > **+** > **Open** > select `D:\Calender\index.html` > Set as wallpaper.
For clicking to work: Lively **Settings > Wallpaper > Wallpaper input** = *Mouse and keyboard* (typing into the "Add event" box needs keyboard).

## 4. Start helper at login
Put a shortcut to this in `shell:startup`:
```
pythonw.exe D:\Calender\gcal_server.py
```

## Notes
- Shows all calendars ticked in Google Calendar; new events go to your primary calendar; only writable events show a delete "x".
- The helper only accepts requests from `file://`/localhost pages, and only listens on 127.0.0.1. `client_secret.json` and `token.json` are credentials; don't share them.

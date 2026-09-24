# Calendar wallpaper for Lively

Files: `index.html` (the wallpaper), `gcal_server.py` (Google Calendar bridge), `LivelyInfo.json`, `LivelyProperties.json`.

## 1. One-time Google setup (free)
1. Go to https://console.cloud.google.com, create a project.
2. **APIs & Services > Library**: enable **Google Calendar API**.
3. **OAuth consent screen**: External, add yourself under **Test users** (stay in Testing mode).
4. **Credentials > Create credentials > OAuth client ID > Desktop app**. Download the JSON.
5. Save it as `D:\Calender\client_secret.json`.

## 2. Start the helper and sign in
```
python D:\Calender\gcal_server.py
```
Then click **Sign in with Google** on the wallpaper. Your normal browser opens; allow access. A `token.json` is saved and events appear. (Or run `python gcal_server.py --login` to sign in from the terminal.)
(In Testing mode Google may expire the token after 7 days; just click the button again.)

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

## Hosted version (Vercel)
`api/cal.py` and `api/auth.py` are Vercel serverless functions. Use a **Web application** OAuth client with redirect URI `https://YOUR-DOMAIN/api/auth`, and set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in Vercel.
Open the site in Chrome/Edge, click **Sign in with Google**, copy the wallpaper link it shows (`/?key=...`) and paste it into Lively as a URL. Google blocks sign-in inside Lively itself. The key in the link is your personal token: keep it private.

# Bridge Dashboard

Live dashboard app served by FastAPI and Nginx on an Oracle VM.

## Local files

- `server.py`
- `index.html`
- `script.js`
- `style.css`
- `bridge-logo.png`
- `ercot_history.json`
- `isone_history.json`
- `miso_history.json`

## Production URL

`https://bridgeenergydash.home.kg/`

## Server update flow

1. Push code changes to GitHub.
2. SSH into the Oracle VM.
3. Pull the latest changes.
4. Restart the app service:

```bash
sudo systemctl restart bridge-dashboard
```



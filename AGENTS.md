# Bridge Dashboard Agent Guide

This file is for AI coding agents working in this repository.

## Identity and access assumptions

Assume the human maintainer using this repo:

- has access to this repository locally
- has GitHub access to the repo
- is working in the GitHub repo `Gabe-Mirsky/bridge-dashboard`
- is an Oracle Cloud Identity Domain Administrator in the relevant Oracle account
- has the SSH private key needed to log into the Oracle VM

Important access nuance:

- GitHub access controls code changes
- Oracle access plus the SSH key controls server-level fixes
- domain and DNS access may be separate from Oracle and may be managed elsewhere

Do not assume domain registrar access unless the human confirms it.

## Project purpose

This repo powers the Bridge Markets Dashboard, a four-quadrant live display site:

- Q1: Power Markets
- Q2: Market Snapshot
- Q3: Oil and Fuels
- Q4: Headlines and Weather

The site is a small FastAPI app that serves one HTML page plus static assets and several JSON API endpoints.

## Repo identity

- Repo name: `bridge-dashboard`
- GitHub remote: `https://github.com/Gabe-Mirsky/bridge-dashboard.git`
- Production URL: `https://bridgeenergydash.home.kg/`

## Hosting and operations overview

Production hosting is on an Oracle Cloud VM.

Known production details:

- VM user: `ubuntu`
- App directory on VM: `/home/ubuntu/bridge-dashboard`
- App service name: `bridge-dashboard`
- Reverse proxy: `nginx`
- Python app entrypoint: `server.py`
- TLS certificate tooling: `certbot`
- Public site domain: `bridgeenergydash.home.kg`
- Public IP historically documented for the site: `132.145.208.19`

Plain-English infrastructure chain:

1. The domain points to the public IP
2. `nginx` receives browser traffic
3. `nginx` forwards requests to FastAPI on the VM
4. FastAPI serves the dashboard shell and JSON endpoints
5. `script.js` fills the quadrants by calling those endpoints

## Deployment flow and interplay

Normal production flow:

1. Code is pushed to GitHub `main`
2. GitHub triggers the webhook endpoint on the live server
3. The live server runs `deploy-webhook.sh`
4. The Oracle VM pulls latest `main`
5. The `bridge-dashboard` service restarts
6. The live site updates

Important:

- pushes to `main` may go live automatically
- branch-first work is safer for risky changes
- local file changes do not affect production until pushed and deployed

## Local vs live debugging

This distinction matters a lot:

- local repo files show what is in the local checkout
- the live website depends on what is currently deployed on Oracle
- local JSON history files do not guarantee the live server has the same current state
- background refresh jobs and server logs that matter for live issues run on Oracle, not in the local repo

If something is wrong only on the live site:

1. inspect the code locally
2. inspect the live logs on Oracle
3. inspect the live JSON/history files on Oracle if relevant

If a problem involves:

- stale data
- auto-deploy
- FastAPI background refresh
- service crashes
- `nginx`
- HTTPS

then Oracle-side debugging is usually required.

## Operational authority the AI should understand

Because the human maintainers have repo access, Oracle admin identity access, and the SSH key, they can potentially do all of the following if needed:

- change code and push updates
- SSH into the VM
- pull the latest repo on the VM
- restart the app service
- inspect `systemd` and app logs
- inspect or edit `nginx` config
- renew or recreate HTTPS certificates
- troubleshoot live data refresh issues on the server

However:

- the AI should not assume permission to make live server changes unless the human asks
- the AI should not assume domain registrar access unless confirmed

## High-level architecture

- Backend: `server.py`
- Frontend markup: `index.html`
- Frontend behavior: `script.js`
- Frontend styling: `style.css`
- Historical electric market storage: `ercot_history.json`, `isone_history.json`, `miso_history.json`
- Deploy helper: `deploy-webhook.sh`
- Repo overview doc for humans: `README.md`

Runtime flow:

1. FastAPI serves `/` from `index.html`
2. FastAPI mounts the repo root at `/static` for CSS, JS, logo, and JSON files
3. The browser loads `script.js`
4. `script.js` fetches backend endpoints on timers and renders the dashboard

## File-by-file map

### `server.py`

Main backend entrypoint. It does 3 jobs:

- serves the frontend
- fetches and reshapes outside data
- handles the GitHub deploy webhook

Main routes:

- `/`: serves `index.html` and adds cache-busting query strings to `style.css` and `script.js`
- `/webhook/github`: receives GitHub push webhooks and launches the deploy script
- `/henry-hub`: returns the next 6 Henry Hub contracts
- `/electric`: returns month-to-date electric market averages for ISO-NE, MISO, and ERCOT
- `/quote/{symbol}`: returns stock, index, metal, or futures quote data for Q2
- `/weather-dashboard`: returns city forecasts and NOAA outlook image info
- `/news`: returns the top 3 filtered CNBC headlines
- `/event-watch`: returns event-watch content used by the frontend
- `/oil-gas-board`: returns gas, diesel, crude, Brent, and spread data for Q3

Important backend caches:

- `cache`
- `news_cache`
- `event_watch_cache`
- `oil_gas_cache`
- `weather_dashboard_cache`
- `ELECTRIC_CACHE`

Important backend note:

- electric market refresh logic writes rolling current/prior month history into the three JSON files
- if the electric JSON files are stale, the issue may be parser drift, fetch failure, or a live server refresh problem
- when debugging electric data, inspect both the parser logic and the live server logs

### `index.html`

This is the base page shell. It contains the header and the 4 quadrant containers:

- `#q1`: Power Markets
- `#q2`: Market Snapshot
- `#q3`: Oil and Fuels
- `#q4`: Headlines and Weather

Most detailed content inside those quadrants is filled in later by `script.js`.

### `script.js`

This is where most frontend behavior lives.

It:

- fetches backend data
- rotates views
- updates timers
- renders HTML into quadrant containers
- manages fullscreen and clock behavior

Important frontend pattern:

- some layout is controlled in `style.css`
- some layout is also built or overwritten directly in `script.js` using generated HTML

If a visual change does not "stick," check both files.

### `style.css`

Main visual theme and layout rules:

- page background
- header styling
- grid layout
- quadrant look and feel
- typography
- panel spacing

Use this first for global styling changes.

### JSON history files

- `isone_history.json`
- `miso_history.json`
- `ercot_history.json`

These store recent daily electric market values used to calculate month-to-date vs prior-month averages.

Important:

- these files may be stale in a local clone
- these files can also become stale on the live server if refresh logic fails
- do not casually delete or reformat them without understanding the electric history logic in `server.py`

## Data sources by quadrant

### Q1: Power Markets

Q1 rotates between Henry Hub natural gas and electric ISO market data.

Henry Hub:

- source: Yahoo Finance via `yfinance`
- backend route: `/henry-hub`
- frontend renderers: `ensureQ1Shell()`, `updateHenryHub()`

Electric:

- sources:
  - ISO-NE day-ahead Internal Hub
  - MISO Illinois Hub day-ahead ex-post
  - ERCOT HB_NORTH day-ahead
- backend builders:
  - `fetch_isone_daily_average()`
  - `fetch_miso_daily_average()`
  - `fetch_ercot_daily_average()`
  - `build_electric()`
- frontend renderer: `updateElectric()`

Important Q1 timer:

- `setInterval(rotateQ1, 20000)` rotates gas vs electric every 20 seconds

### Q2: Market Snapshot

Q2 shows an active large quote plus a categorized ticker grid.

Data source:

- Yahoo Finance via `/quote/{symbol}`

Main frontend pieces:

- `assets` array at the top of `script.js`
- `fetchPrice()`
- `updateAsset()`
- `updateTickerPanel()`
- `refreshAllTickers()`

If you need to add or remove stocks, indices, or metals:

- edit the `assets` array in `script.js`

If you need to change Q2 rotation timing:

- `setInterval(rotateAssets, 5000)`
- `setInterval(updateAsset, 60000)`
- `startTickerCountdown()`

### Q3: Oil and Fuels

Q3 shows:

- average U.S. gasoline
- average U.S. diesel
- WTI crude
- Brent crude
- WTI-Brent spread

Backend route:

- `/oil-gas-board`

Main backend functions:

- `fetch_retail_fuel_averages()`
- `fetch_market_quote()`
- `get_oil_gas_board()`

Frontend renderer:

- `fetchOilGasBoard()`
- `renderOilGasBoard()`

### Q4: Headlines and Weather

Q4 rotates between headlines and weather views.

Headlines:

- source: CNBC RSS
- backend route: `/news`
- ranking logic: `headline_score()`, duplicate filtering, recency filter
- frontend renderer: `updateLatestHeadlines()`, `renderHeadlines()`

Weather:

- source: National Weather Service API and NOAA CPC outlook pages
- backend route: `/weather-dashboard`
- frontend renderers:
  - `renderRegionalWeatherView()`
  - `renderHartfordWeatherView()`
  - `renderOutlookWeatherView()`
  - `renderQ4View()`

Important Q4 timers:

- `NEWS_REFRESH_INTERVAL = 60000`
- `WEATHER_REFRESH_INTERVAL = 15 * 60 * 1000`
- `Q4_ROTATE_INTERVAL = 20000`

## Common edit guide

### Change a title or static label

Check `index.html` first.

Examples:

- main dashboard title
- section shell labels already written into the HTML

If the label is injected later by JavaScript, edit `script.js` instead.

### Add or remove a stock in Q2

Edit the `assets` array near the top of `script.js`.

Each entry looks like:

```js
{ name: "Apple", symbol: "AAPL", category: "Big Stocks" }
```

Valid categories currently expected by the UI:

- `Indices`
- `Metals`
- `Big Stocks`

If you add a new category, you must also update `updateTickerPanel()`.

### Change quadrant rotation timing

Edit the timer constants or `setInterval(...)` calls in `script.js`.

Common ones:

- Q1 gas/electric rotation: `rotateQ1`
- Q2 featured asset rotation: `rotateAssets`
- Q4 headlines/weather rotation: `Q4_ROTATE_INTERVAL`

### Change weather cities

Edit `WEATHER_LOCATIONS` in `server.py`.

If the UI wording also needs to change, update the weather render functions in `script.js`.

### Change headline behavior

Backend logic is in `get_news()` and `headline_score()` in `server.py`.

Use backend changes for:

- source feeds
- scoring rules
- deduping
- time window

Use frontend changes for:

- display format
- truncation
- styling

### Change electric hubs or market labels

Backend data collection and averages are in `server.py`.
Frontend labels and fallbacks are in `updateElectric()` in `script.js`.

If changing hub names, verify both layers.

### Change Q3 labels or notes

Most Q3 content is assembled in `get_oil_gas_board()` in `server.py` and rendered in `renderOilGasBoard()` in `script.js`.

### Change the theme or spacing

Start in `style.css`.

If a quadrant uses generated inline styles, also inspect the matching render function in `script.js`.

## Data-source notes

This dashboard depends on external websites and APIs. If one area breaks unexpectedly, suspect source-format drift first.

Known source types:

- Yahoo Finance via `yfinance`
- NWS API
- NOAA CPC pages and images
- CNBC RSS
- EIA fuel page
- ISO / market file downloads for electric data

When fixing a broken feed:

1. identify the backend route feeding that quadrant
2. inspect the fetch/parser function in `server.py`
3. keep frontend changes minimal unless the response shape changed

## Deployment notes

- production host is an Oracle Cloud VM behind `nginx`
- HTTPS domain is `https://bridgeenergydash.home.kg/`
- pushes to `main` may auto-deploy

Agent safety rule:

- avoid pushing directly to `main` unless explicitly asked
- prefer a branch-first workflow for risky changes
- avoid making live Oracle changes unless the human explicitly wants server-side help

## Good first debugging checklist

If asked to change something, locate it in this order:

1. `index.html` for page shell and hardcoded labels
2. `script.js` for rendering, timers, rotation, and generated markup
3. `style.css` for layout and visual styling
4. `server.py` for data shape, source fetching, deployment, and backend logic

If a change "does not appear" after editing:

1. check whether the HTML is being regenerated by JavaScript
2. check whether the data comes from a backend endpoint instead of hardcoded frontend text
3. check whether cache or refresh timers are delaying the visible update
4. if the issue is only on the live site, check Oracle logs and live deployment state

## Live-debug checklist

If the live site is wrong but local code looks correct, likely next steps are on Oracle:

1. SSH into the VM
2. go to `/home/ubuntu/bridge-dashboard`
3. inspect the current files and JSON history there
4. inspect logs for the `bridge-dashboard` service
5. restart the service if needed

Useful Oracle-side checks typically include:

- `git pull`
- `sudo systemctl status bridge-dashboard --no-pager`
- `sudo systemctl restart bridge-dashboard`
- `sudo journalctl -u bridge-dashboard -n 200 --no-pager`

## Suggested cleanup opportunities

These are not required for every task, but they are worth knowing:

- reduce inline HTML/CSS generation in `script.js` if maintainability becomes a problem
- consider splitting `server.py` and `script.js` into smaller modules if the app keeps growing
- keep `AGENTS.md` updated whenever hosting, access assumptions, or deployment flow changes

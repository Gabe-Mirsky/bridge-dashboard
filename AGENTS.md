# Bridge Dashboard Agent Guide

This file is for AI coding agents working in this repository.

## Project purpose

This repo powers the Bridge Markets Dashboard, a four-quadrant live display site:

- Q1: Power Markets
- Q2: Market Snapshot
- Q3: Oil and Fuels
- Q4: Headlines and Weather

The site is a small FastAPI app that serves one HTML page plus static assets and several JSON API endpoints.

## High-level architecture

- Backend: `server.py`
- Frontend markup: `index.html`
- Frontend behavior: `script.js`
- Frontend styling: `style.css`
- Historical electric market storage: `ercot_history.json`, `isone_history.json`, `miso_history.json`
- Deploy helper: `deploy-webhook.sh`

Runtime flow:

1. FastAPI serves `/` from `index.html`.
2. FastAPI mounts the repo root at `/static` for CSS, JS, logo, and JSON files.
3. The browser loads `script.js`.
4. `script.js` fetches backend endpoints on timers and renders the dashboard.

Production flow:

1. Code is pushed to GitHub `main`.
2. GitHub triggers the webhook endpoint.
3. The server runs `deploy-webhook.sh`.
4. The Oracle VM pulls latest `main` and restarts the app.

Important: changes pushed to `main` may go live automatically.

## File-by-file map

### `server.py`

Main backend entrypoint. It does 3 jobs:

- Serves the frontend
- Fetches and reshapes outside data
- Handles the GitHub deploy webhook

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

Important backend gotcha:

- `server.py` currently contains duplicate definitions for `electric_background_worker`, `start_electric_background`, and `/electric`.
- In Python, the later definitions win.
- If changing electric endpoint behavior, edit the later `/electric` block, or clean up the duplicates first.

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

- Some layout is controlled in `style.css`
- Some layout is also built or overwritten directly in `script.js` using inline styles and generated HTML

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

Do not casually delete or reformat them without understanding the electric history logic in `server.py`.

## Data sources by quadrant

### Q1: Power Markets

Q1 rotates between Henry Hub natural gas and electric ISO market data.

Henry Hub:

- Source: Yahoo Finance via `yfinance`
- Backend route: `/henry-hub`
- Frontend renderers: `ensureQ1Shell()`, `updateHenryHub()`

Electric:

- Sources:
  - ISO-NE day-ahead Internal Hub
  - MISO Illinois Hub day-ahead ex-post
  - ERCOT HB_NORTH day-ahead
- Backend builders:
  - `fetch_isone_daily_average()`
  - `fetch_miso_daily_average()`
  - `fetch_ercot_daily_average()`
  - `build_electric()`
- Frontend renderer: `updateElectric()`

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

- Source: CNBC RSS
- Backend route: `/news`
- Ranking logic: `headline_score()`, duplicate filtering, recency filter
- Frontend renderer: `updateLatestHeadlines()`, `renderHeadlines()`

Weather:

- Source: National Weather Service API and NOAA CPC outlook pages
- Backend route: `/weather-dashboard`
- Frontend renderers:
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

1. Identify the backend route feeding that quadrant
2. Inspect the fetch/parser function in `server.py`
3. Keep frontend changes minimal unless the response shape changed

## Deployment notes

- Production host is an Oracle Cloud VM behind `nginx`
- HTTPS domain is `https://bridgeenergydash.home.kg/`
- Pushes to `main` may auto-deploy

Agent safety rule:

- Avoid pushing directly to `main` unless explicitly asked
- Prefer a branch-first workflow for risky changes

## Good first debugging checklist

If asked to change something, locate it in this order:

1. `index.html` for page shell and hardcoded labels
2. `script.js` for rendering, timers, rotation, and generated markup
3. `style.css` for layout and visual styling
4. `server.py` for data shape, source fetching, and backend logic

If a change "does not appear" after editing:

1. Check whether the HTML is being regenerated by JavaScript
2. Check whether the data comes from a backend endpoint instead of hardcoded frontend text
3. Check whether cache or refresh timers are delaying the visible update

## Suggested cleanup opportunities

These are not required for every task, but they are worth knowing:

- Remove duplicate electric route/background-worker definitions in `server.py`
- Reduce inline HTML/CSS generation in `script.js` if maintainability becomes a problem
- Consider splitting `server.py` and `script.js` into smaller modules if the app keeps growing

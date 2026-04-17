/* =========================================================
   BRIDGE DASHBOARD — script.js (FULL)
   Fix: Q2 title-row stays pinned top; price stays centered (fullscreen-safe)
   NOTE: Layout, timers, rotation, ticker grid, animations preserved.
   ========================================================= */

/* =========================================================
   ASSET CONFIGURATION
   ========================================================= */

const assets = [
  // Indices
  { name: "S&P 500", symbol: "^GSPC", category: "Indices" },
  { name: "Dow", symbol: "^DJI", category: "Indices" },
  { name: "Nasdaq", symbol: "^IXIC", category: "Indices" },

  // Metals
  { name: "Gold", symbol: "GC=F", category: "Metals" },
  { name: "Silver", symbol: "SI=F", category: "Metals" },
  { name: "Copper", symbol: "HG=F", category: "Metals" },

  // Big Stocks
  { name: "Apple", symbol: "AAPL", category: "Big Stocks" },
  { name: "Microsoft", symbol: "MSFT", category: "Big Stocks" },
  { name: "Nvidia", symbol: "NVDA", category: "Big Stocks" },
  { name: "Amazon", symbol: "AMZN", category: "Big Stocks" },
  { name: "Google", symbol: "GOOGL", category: "Big Stocks" },
  { name: "Meta", symbol: "META", category: "Big Stocks" }
];

let tickerData = {};
let currentIndex = 0;
let henryHubPrevious = {};
let q1Mode = "gas";
let electricPrevious = {};
let electricInFlight = false;
let q1TransitionInFlight = false;
const Q1_FADE_MS = 350;
let latestHenryHubHtml = "";
let latestElectricHtml = "";

/* =========================================================
   LAYOUT INITIALIZATION
   ========================================================= */

function initTopRightQuadrantLayout() {
  const q2 = document.getElementById("q2");
  if (!q2) return;

  // If already built, do not rebuild DOM, but DO re-apply layout styles.
  const mainWrapExisting = document.getElementById("main-display");
  const tickerWrapExisting = document.getElementById("ticker-panel");

  // Build wrappers once
  if (!mainWrapExisting || !tickerWrapExisting) {
    // IMPORTANT: Preserve the entire title-row so CSS flex keeps title + asset on one line
    const titleRow = q2.querySelector(".title-row");
    const assetName = document.getElementById("asset-name");
    const q2Title = q2.querySelector(".q2-title");

    // If someone edited HTML and removed title-row, rebuild it safely
    let ensuredTitleRow = titleRow;
    if (!ensuredTitleRow) {
      ensuredTitleRow = document.createElement("div");
      ensuredTitleRow.className = "title-row";

      if (q2Title) ensuredTitleRow.appendChild(q2Title);
      if (assetName) ensuredTitleRow.appendChild(assetName);
    }

    const price = document.getElementById("price");
    const change = document.getElementById("change");

    const mainWrap = document.createElement("div");
    mainWrap.id = "main-display";

    // NEW: center wrapper for price/change so title stays top (fullscreen-safe)
    const centerWrap = document.createElement("div");
    centerWrap.id = "main-center";

    if (price) centerWrap.appendChild(price);
    if (change) centerWrap.appendChild(change);

    if (ensuredTitleRow) mainWrap.appendChild(ensuredTitleRow);
    mainWrap.appendChild(centerWrap);

    const tickerWrap = document.createElement("div");
    tickerWrap.id = "ticker-panel";

    const tickerContent = document.createElement("div");
    tickerContent.id = "ticker-content";

    const refreshTimer = document.createElement("div");
    refreshTimer.id = "ticker-refresh-timer";

    tickerWrap.appendChild(tickerContent);
    tickerWrap.appendChild(refreshTimer);

    q2.innerHTML = "";
    q2.appendChild(mainWrap);
    q2.appendChild(tickerWrap);
  }

  // If Q2 already exists from previous load, ensure price/change are inside #main-center
  const mainWrap = document.getElementById("main-display");
  if (mainWrap) {
    let centerWrap = document.getElementById("main-center");
    if (!centerWrap) {
      centerWrap = document.createElement("div");
      centerWrap.id = "main-center";

      const price = document.getElementById("price");
      const change = document.getElementById("change");

      if (price) centerWrap.appendChild(price);
      if (change) centerWrap.appendChild(change);

      mainWrap.appendChild(centerWrap);
    } else {
      // If someone moved nodes around, re-home them
      const price = document.getElementById("price");
      const change = document.getElementById("change");
      if (price && price.parentElement !== centerWrap) centerWrap.appendChild(price);
      if (change && change.parentElement !== centerWrap) centerWrap.appendChild(change);
    }
  }

  // Re-apply layout styles every time
  q2.style.display = "flex";
  q2.style.flexDirection = "column";
  q2.style.justifyContent = "flex-start";
  q2.style.alignItems = "stretch";
  q2.style.gap = "12px";

  const tickerWrap = document.getElementById("ticker-panel");
  const refreshTimer = document.getElementById("ticker-refresh-timer");
  const centerWrap = document.getElementById("main-center");

  // UPDATED: Title pinned top, price block centered in remaining space
  if (mainWrap) {
    mainWrap.style.flex = "0.9 1 0";
    mainWrap.style.display = "flex";
    mainWrap.style.flexDirection = "column";
    mainWrap.style.justifyContent = "flex-start"; // ✅ title stays top
    mainWrap.style.alignItems = "stretch";        // let title-row keep its own layout
    mainWrap.style.minHeight = "0";
  }

  if (centerWrap) {
    centerWrap.style.flex = "0 0 auto";
    centerWrap.style.display = "flex";
    centerWrap.style.flexDirection = "column";
    centerWrap.style.justifyContent = "flex-start";
    centerWrap.style.alignItems = "center";
    centerWrap.style.gap = "2px";
    centerWrap.style.paddingTop = "2px";
    centerWrap.style.minHeight = "0";
  }

  if (tickerWrap) {
    tickerWrap.style.flex = "1.2 1 0";
    tickerWrap.style.padding = "0 12px 8px 12px";
    tickerWrap.style.boxSizing = "border-box";
    tickerWrap.style.display = "flex";
    tickerWrap.style.flexDirection = "column";
    tickerWrap.style.justifyContent = "space-between";
    tickerWrap.style.minHeight = "0";
  }

  if (refreshTimer) {
    refreshTimer.style.fontSize = "11px";
    refreshTimer.style.opacity = "0.55";
    refreshTimer.style.textAlign = "right";
    refreshTimer.style.marginTop = "8px";
    refreshTimer.style.paddingRight = "4px";
  }
}

/* =========================================================
   DATA FETCHING
   ========================================================= */

async function fetchPrice(symbol) {
  try {
    const response = await fetch(
      `/quote/${encodeURIComponent(symbol)}`
    );
    return await response.json();
  } catch (error) {
    console.log("Fetch error:", error);
    return null;
  }
}

/* =========================================================
   Q1 — GAS / ELECTRIC (HENRY HUB VIEW)
   ========================================================= */

const HENRY_API = "/henry-hub";

function ensureQ1Shell(modeTitleText) {
  const q1 = document.getElementById("q1");
  if (!q1) return null;

  const inner = q1.querySelector(".quad-inner");
  if (!inner) return null;

  inner.style.display = "flex";
  inner.style.flexDirection = "column";
  inner.style.height = "100%";

  if (!inner.querySelector("#q1-shell")) {
    inner.innerHTML = `
      <div id="q1-shell" style="display:flex;flex-direction:column;height:100%;">
        <div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:center;margin-bottom:10px;">
          <div class="quad-title" style="margin-bottom:0;justify-self:start;">
            Power Markets
          </div>
          <div id="q1-mode-title" style="font-size:20px;letter-spacing:2px;text-transform:uppercase;opacity:0.7;font-weight:500;justify-self:center;transition:opacity ${Q1_FADE_MS}ms ease;"></div>
          <div></div>
        </div>
        <div id="q1-fade-content" style="display:flex;flex-direction:column;flex:1;opacity:1;transition:opacity ${Q1_FADE_MS}ms ease;"></div>
      </div>
    `;
  }

  const modeTitle = inner.querySelector("#q1-mode-title");
  if (modeTitle) modeTitle.textContent = modeTitleText;

  const fadeContent = inner.querySelector("#q1-fade-content");
  return fadeContent || null;
}

async function updateHenryHub() {
  try {
    const res = await fetch(HENRY_API, { cache: "no-store" });
    const data = await res.json();

    const content = ensureQ1Shell("Henry Hub Futures");
    if (!content) return;

    let html = `
      <div style="
          height:1px;
          background:rgba(255,255,255,0.08);
          margin:12px 0 18px 0;
      "></div>
    `;

    if (data && Array.isArray(data.contracts) && data.contracts.length > 0) {

      html += `
        <div style="
            display:grid;
            grid-template-columns:repeat(3, minmax(0, 1fr));
            column-gap:18px;
            align-items:center;
            font-size:14px;
            font-weight:700;
            letter-spacing:1px;
            text-transform:uppercase;
            opacity:0.9;
            border-bottom:1px solid rgba(255,255,255,0.15);
            padding-bottom:6px;
            margin-bottom:8px;
        ">
          <div>Contract Month</div>
          <div style="text-align:center;">Settle ($/MMBtu)</div>
          <div style="text-align:right;">Daily Change ($, %)</div>
        </div>

        <div style="
            display:flex;
            flex-direction:column;
            justify-content:space-evenly;
            flex:1;
        ">
      `;

      data.contracts.slice(0, 6).forEach(c => {

        const price = Number(c?.price ?? 0);
        const change = Number(c?.change ?? 0);
        const percent = Number(c?.percent ?? 0);

        const isUp = change >= 0;
        const arrow = isUp ? "▲" : "▼";
        const color = isUp ? "#00ff7f" : "#ff4c4c";

        html += `
          <div style="
              display:grid;
              grid-template-columns:repeat(3, minmax(0, 1fr));
              column-gap:18px;
              align-items:center;
              font-size:21px;
              padding:6px 4px;
              font-variant-numeric:tabular-nums;
          ">
              <div style="font-weight:600;">
                ${c?.month ?? "--"}
              </div>

              <div style="text-align:center; font-size:inherit;">
                $${price.toFixed(3)}
              </div>

              <div style="
                  text-align:right;
                  color:${color};
                  font-size:inherit;
              ">
                <span style="margin-right:6px;">${arrow}</span>
                $${Math.abs(change).toFixed(3)} 
                (${Math.abs(percent).toFixed(2)}%)
              </div>
          </div>
        `;
      });

      html += `</div>`;

    } else {

      html += `
        <div style="
            flex:1;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:18px;
            opacity:0.6;
        ">
          No gas data available
        </div>
      `;
    }

    content.innerHTML = html;

  } catch (err) {
    console.log("Henry Hub fetch failed:", err);
  }
}

async function updateElectric() {
  if (electricInFlight) return;
  electricInFlight = true;

  try {
    const content = ensureQ1Shell("Electric");
    if (!content) return;

    let html = `
      <div style="height:1px;background:rgba(255,255,255,0.08);margin:12px 0 18px 0;"></div>

      <div style="
          display:grid;
          grid-template-columns:repeat(4, minmax(0, 1fr));
          column-gap:18px;
          align-items:center;
          font-size:14px;
          font-weight:700;
          letter-spacing:1px;
          text-transform:uppercase;
          opacity:0.95;
          color:#ffffff;
          border-bottom:1px solid rgba(255,255,255,0.15);
          padding-bottom:6px;
          margin-bottom:8px;
      ">
        <div>ISO</div>
        <div>Trading Hub</div>
        <div style="text-align:center;">MTD Avg DA ($/MWh)</div>
        <div style="text-align:right;">MoM Change ($, %)</div>
      </div>
    `;

    const res = await fetch("/electric", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP status " + res.status);

    let data;
    try {
      data = await res.json();
    } catch {
      const raw = await res.text();
      console.log("Electric raw response:", raw);
      throw new Error("Invalid JSON response");
    }

    if (!data || !Array.isArray(data.markets) || data.markets.length === 0) {
      html += `
        <div style="flex:1;display:flex;align-items:center;justify-content:center;opacity:0.65;font-size:18px;">
          Electric data unavailable
        </div>
      `;
      latestElectricHtml = html;
      content.innerHTML = html;
      return;
    }

    html += `<div style="display:flex;flex-direction:column;justify-content:space-evenly;flex:1;">`;
    data.markets.forEach(m => {
      const name = m?.name ?? "--";
      const price = Number(m?.price ?? 0);
      const change = Number(m?.change ?? 0);
      const percent = Number(m?.percent ?? 0);
      let iso = name;
      let hub = "--";

      if (typeof m?.iso === "string" && m.iso.trim()) iso = m.iso.trim();
      if (typeof m?.hub === "string" && m.hub.trim()) hub = m.hub.trim();

      if (hub === "--") {
        const match = name.match(/^(.*?)\s*\((.*?)\)\s*$/);
        if (match) {
          iso = match[1].trim();
          hub = match[2].trim();
        }
      }

      if (hub === "--") {
        if (/ISO[\s-]?NE|ISO New England/i.test(name)) {
          iso = "ISO-NE";
          hub = "Internal Hub";
        } else if (/MISO/i.test(name)) {
          iso = "MISO";
          hub = "Illinois Hub";
        } else if (/ERCOT/i.test(name)) {
          iso = "ERCOT";
          hub = "HB North";
        }
      }

      const isUp = change >= 0;
      const color = isUp ? "#00ff7f" : "#ff4c4c";
      const arrow = isUp ? "▲" : "▼";
      const deltaDollars = `$${Math.abs(change).toFixed(2)}`;
      const deltaPercent = `${Math.abs(percent).toFixed(2)}%`;

      html += `
        <div style="display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));column-gap:18px;align-items:center;font-size:21px;padding:6px 4px;font-variant-numeric:tabular-nums;">
          <div style="font-weight:600;font-size:inherit;">${iso}</div>
          <div style="font-weight:600;font-size:inherit;">${hub}</div>
          <div style="text-align:center;font-size:inherit;">$${price.toFixed(2)}</div>
          <div style="text-align:right;color:${color};font-size:inherit;">
            <span style="margin-right:6px;">${arrow}</span>${deltaDollars} (${deltaPercent})
          </div>
        </div>
      `;
    });

    html += `</div>`;
    latestElectricHtml = html;
    content.innerHTML = html;

  } catch (err) {
    console.log("Electric fetch failed:", err);

    const content = ensureQ1Shell("Electric");
    if (content) {
      const fallbackHtml = `
        <div style="height:1px;background:rgba(255,255,255,0.08);margin:12px 0 18px 0;"></div>
        <div style="flex:1;display:flex;align-items:center;justify-content:center;opacity:0.65;font-size:18px;">
          Electric data unavailable
        </div>
      `;
      latestElectricHtml = fallbackHtml;
      content.innerHTML = fallbackHtml;
    }
  } finally {
    electricInFlight = false;
  }
}

async function buildHenryHubHtmlForRotation() {
  if (latestHenryHubHtml) return latestHenryHubHtml;
  const res = await fetch(HENRY_API, { cache: "no-store" });
  const data = await res.json();

  let html = `
    <div style="
        height:1px;
        background:rgba(255,255,255,0.08);
        margin:12px 0 18px 0;
    "></div>
  `;

  if (data && Array.isArray(data.contracts) && data.contracts.length > 0) {
    html += `
      <div style="
          display:grid;
          grid-template-columns:repeat(3, minmax(0, 1fr));
          column-gap:18px;
          align-items:center;
          font-size:14px;
          font-weight:700;
          letter-spacing:1px;
          text-transform:uppercase;
          opacity:0.9;
          border-bottom:1px solid rgba(255,255,255,0.15);
          padding-bottom:6px;
          margin-bottom:8px;
      ">
        <div>Contract Month</div>
        <div style="text-align:center;">Settle ($/MMBtu)</div>
        <div style="text-align:right;">Daily Change ($, %)</div>
      </div>
      <div style="
          display:flex;
          flex-direction:column;
          justify-content:space-evenly;
          flex:1;
      ">
    `;

    data.contracts.slice(0, 6).forEach(c => {
      const price = Number(c?.price ?? 0);
      const change = Number(c?.change ?? 0);
      const percent = Number(c?.percent ?? 0);
      const isUp = change >= 0;
      const arrow = isUp ? "&#9650;" : "&#9660;";
      const color = isUp ? "#00ff7f" : "#ff4c4c";

      html += `
        <div style="
            display:grid;
            grid-template-columns:repeat(3, minmax(0, 1fr));
            column-gap:18px;
            align-items:center;
            font-size:21px;
            padding:6px 4px;
            font-variant-numeric:tabular-nums;
        ">
            <div style="font-weight:600;">${c?.month ?? "--"}</div>
            <div style="text-align:center; font-size:inherit;">$${price.toFixed(3)}</div>
            <div style="text-align:right;color:${color};font-size:inherit;">
              <span style="margin-right:6px;">${arrow}</span>
              $${Math.abs(change).toFixed(3)} (${Math.abs(percent).toFixed(2)}%)
            </div>
        </div>
      `;
    });

    html += `</div>`;
  } else {
    html += `
      <div style="
          flex:1;
          display:flex;
          align-items:center;
          justify-content:center;
          font-size:18px;
          opacity:0.6;
      ">
        No gas data available
      </div>
    `;
  }

  latestHenryHubHtml = html;
  return html;
}

async function buildElectricHtmlForRotation() {
  if (latestElectricHtml) return latestElectricHtml;
  let html = `
    <div style="height:1px;background:rgba(255,255,255,0.08);margin:12px 0 18px 0;"></div>
    <div style="
        display:grid;
        grid-template-columns:repeat(4, minmax(0, 1fr));
        column-gap:18px;
        align-items:center;
        font-size:14px;
        font-weight:700;
        letter-spacing:1px;
        text-transform:uppercase;
        opacity:0.95;
        color:#ffffff;
        border-bottom:1px solid rgba(255,255,255,0.15);
        padding-bottom:6px;
        margin-bottom:8px;
    ">
      <div>ISO</div>
      <div>Trading Hub</div>
      <div style="text-align:center;">MTD Avg DA ($/MWh)</div>
      <div style="text-align:right;">MoM Change ($, %)</div>
    </div>
  `;

  const res = await fetch("/electric", { cache: "no-store" });
  if (!res.ok) throw new Error("HTTP status " + res.status);
  const data = await res.json();

  if (!data || !Array.isArray(data.markets) || data.markets.length === 0) {
    html += `
      <div style="flex:1;display:flex;align-items:center;justify-content:center;opacity:0.65;font-size:18px;">
        Electric data unavailable
      </div>
    `;
    return html;
  }

  html += `<div style="display:flex;flex-direction:column;justify-content:space-evenly;flex:1;">`;
  data.markets.forEach(m => {
    const name = m?.name ?? "--";
    const price = Number(m?.price ?? 0);
    const change = Number(m?.change ?? 0);
    const percent = Number(m?.percent ?? 0);
    let iso = name;
    let hub = "--";

    if (typeof m?.iso === "string" && m.iso.trim()) iso = m.iso.trim();
    if (typeof m?.hub === "string" && m.hub.trim()) hub = m.hub.trim();

    if (hub === "--") {
      const match = name.match(/^(.*?)\s*\((.*?)\)\s*$/);
      if (match) {
        iso = match[1].trim();
        hub = match[2].trim();
      }
    }

    if (hub === "--") {
      if (/ISO[\s-]?NE|ISO New England/i.test(name)) {
        iso = "ISO-NE";
        hub = "Internal Hub";
      } else if (/MISO/i.test(name)) {
        iso = "MISO";
        hub = "Illinois Hub";
      } else if (/ERCOT/i.test(name)) {
        iso = "ERCOT";
        hub = "HB North";
      }
    }

    const isUp = change >= 0;
    const color = isUp ? "#00ff7f" : "#ff4c4c";
    const arrow = isUp ? "â–²" : "â–¼";
    const arrowHtml = isUp ? "&#9650;" : "&#9660;";
    const arrowFixed = isUp ? "&#9650;" : "&#9660;";
    const deltaDollars = `$${Math.abs(change).toFixed(2)}`;
    const deltaPercent = `${Math.abs(percent).toFixed(2)}%`;

    html += `
      <div style="display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));column-gap:18px;align-items:center;font-size:21px;padding:6px 4px;font-variant-numeric:tabular-nums;">
        <div style="font-weight:600;font-size:inherit;">${iso}</div>
        <div style="font-weight:600;font-size:inherit;">${hub}</div>
        <div style="text-align:center;font-size:inherit;">$${price.toFixed(2)}</div>
        <div style="text-align:right;color:${color};font-size:inherit;">
          <span style="margin-right:6px;">${arrowFixed}</span>${deltaDollars} (${deltaPercent})
        </div>
      </div>
    `;
  });

  html += `</div>`;
  latestElectricHtml = html;
  return html;
}


/* =========================================================
   MAIN ROTATING DISPLAY
   ========================================================= */

async function updateAsset() {
  const asset = assets[currentIndex];
  const data = await fetchPrice(asset.symbol);

  if (!data || data.price == null || data.price === 0) {
    console.log("Bad data received:", data);
    return;
  }

  const price = Number(data.price);
  const change = Number(data.change);
  const changeDollar = Number(data.change_dollar ?? 0);

  tickerData[asset.symbol] = { name: asset.name, price, change, changeDollar };

  const nameEl = document.getElementById("asset-name");
  if (nameEl) nameEl.textContent = asset.name;

  const isPositive = change >= 0;
  const arrow = isPositive ? "▲" : "▼";
  const color = isPositive ? "#00ff7f" : "#ff4c4c";

  const formattedPrice = price.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });

  const priceEl = document.getElementById("price");
  if (priceEl) {
    priceEl.innerHTML = `
      <span>$${formattedPrice}</span>
      <span style="color:${color}; margin-left:1px; font-size:0.6em;">
        ${arrow} $${Math.abs(changeDollar).toFixed(2)} (${Math.abs(change).toFixed(2)}%)
      </span>
    `;
  }

  // Clear old change line since it's now inline
  const changeEl = document.getElementById("change");
  if (changeEl) changeEl.textContent = "";
}

async function rotateAssets() {
  const assetEl = document.getElementById("asset-name");
  const priceEl = document.getElementById("price");
  if (!assetEl || !priceEl) return;

  // Fade stock name and price/change together.
  assetEl.style.transition = "opacity 0.5s ease";
  priceEl.style.transition = "opacity 0.5s ease";
  assetEl.style.opacity = 0;
  priceEl.style.opacity = 0;

  setTimeout(async () => {
    currentIndex = (currentIndex + 1) % assets.length;
    await updateAsset();
    assetEl.style.opacity = 1;
    priceEl.style.opacity = 1;
  }, 500);
}

async function rotateQ1() {
  if (q1TransitionInFlight) return;
  q1TransitionInFlight = true;

  const nextMode = q1Mode === "gas" ? "electric" : "gas";
  const nextModeTitleText = nextMode === "gas" ? "Henry Hub Futures" : "Electric";
  const nextHtmlPromise = nextMode === "gas"
    ? (latestHenryHubHtml ? Promise.resolve(latestHenryHubHtml) : buildHenryHubHtmlForRotation())
    : (latestElectricHtml ? Promise.resolve(latestElectricHtml) : buildElectricHtmlForRotation());

  const currentModeTitle = document.getElementById("q1-mode-title");
  const currentContent = document.getElementById("q1-fade-content");
  if (currentModeTitle) currentModeTitle.style.opacity = "0";
  if (currentContent) {
    currentContent.style.opacity = "0";
    await new Promise(resolve => setTimeout(resolve, Q1_FADE_MS));
  }

  q1Mode = nextMode;
  const nextHtml = await nextHtmlPromise;
  const nextTarget = ensureQ1Shell(nextModeTitleText);
  if (nextTarget) nextTarget.innerHTML = nextHtml;

  const nextModeTitle = document.getElementById("q1-mode-title");
  const nextContent = document.getElementById("q1-fade-content");
  if (nextModeTitle) nextModeTitle.style.opacity = "0";
  if (nextContent) {
    nextContent.style.opacity = "0";
    requestAnimationFrame(() => {
      nextContent.style.opacity = "1";
      if (nextModeTitle) nextModeTitle.style.opacity = "0.7";
    });
  } else if (nextModeTitle) {
    nextModeTitle.style.opacity = "0.7";
  }

  if (nextMode === "gas") {
    updateHenryHub();
  } else {
    updateElectric();
  }

  q1TransitionInFlight = false;
}

setInterval(rotateQ1, 20000); // rotate every 20 seconds
/* =========================================================
   TICKER GRID (CATEGORIZED)
   ========================================================= */

function updateTickerPanel() {
  const panel = document.getElementById("ticker-content");
  if (!panel) return;

  const grouped = {
    "Indices": [],
    "Metals": [],
    "Big Stocks": []
  };

  assets.forEach(asset => {
    if (grouped[asset.category]) grouped[asset.category].push(asset);
  });

  function renderGroup(title, items) {
    let rows = "";

    items.forEach(asset => {
      const data = tickerData[asset.symbol];

      const price = data
        ? data.price.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
          })
        : "--";

      const change = data ? data.change : 0;
      const changeDollar = data ? (data.changeDollar ?? 0) : 0;
      const isPositive = change >= 0;
      const arrow = data ? (isPositive ? "▲" : "▼") : "";
      const color = data ? (isPositive ? "#00ff7f" : "#ff4c4c") : "#666";
      const percent = data ? `${arrow} $${Math.abs(changeDollar).toFixed(2)} (${Math.abs(change).toFixed(2)}%)` : "--";

      rows += `
        <div
          class="ticker-row"
          data-symbol="${asset.symbol}"
          style="display:flex; justify-content:space-between; align-items:center; font-size:13px; line-height:1.05; padding:1px 3px; border-radius:4px;"
        >
          <span>${asset.name}</span>
          <div style="display:flex; align-items:center; gap:6px;">
            <span class="ticker-price">$${price}</span>
            <span class="ticker-percent" style="color:${color}">
              ${percent}
            </span>
          </div>
        </div>
      `;
    });

    return `
      <div style="margin-bottom:8px;">
        <div
          style="
            font-size:12px;
            font-weight:600;
            letter-spacing:1px;
            padding:3px 0;
            margin-bottom:4px;
            border-top:1px solid rgba(255,255,255,0.08);
            border-bottom:1px solid rgba(255,255,255,0.08);
            color:#bbbbbb;
          "
        >
          ${title}
        </div>
        <div style="display:flex; flex-direction:column; gap:3px;">
          ${rows}
        </div>
      </div>
    `;
  }

  panel.innerHTML = `
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; height:100%; min-height:0;">
      <div style="display:flex; flex-direction:column; justify-content:space-between; min-height:0;">
        ${renderGroup("Indices", grouped["Indices"])}
        ${renderGroup("Metals", grouped["Metals"])}
      </div>
      <div style="display:flex; flex-direction:column; justify-content:flex-start; min-height:0;">
        ${renderGroup("Big Stocks", grouped["Big Stocks"])}
      </div>
    </div>
  `;
}

/* =========================================================
   GLOBAL REFRESH
   ========================================================= */

async function refreshAllTickers() {
  const newData = { ...tickerData };

  // PRELOAD everything first
  for (let asset of assets) {
    const data = await fetchPrice(asset.symbol);

    if (data && data.price != null && data.price !== 0) {
      newData[asset.symbol] = {
        name: asset.name,
        price: Number(data.price),
        change: Number(data.change),
        changeDollar: Number(data.change_dollar ?? 0)
      };
    }
  }

  // UPDATE only after all data is ready
  assets.forEach(asset => {
    const oldData = tickerData[asset.symbol];
    const updated = newData[asset.symbol];
    if (!updated) return;

    const row = document.querySelector(`.ticker-row[data-symbol="${asset.symbol}"]`);
    if (!row) return;

    const priceEl = row.querySelector(".ticker-price");
    const percentEl = row.querySelector(".ticker-percent");
    if (!priceEl || !percentEl) return;

    const priceChanged = !oldData || updated.price !== oldData.price;
    const changeChanged = !oldData || updated.change !== oldData.change;

    if (priceChanged || changeChanged) {
      const isUp = !oldData || updated.price >= oldData.price;

      row.classList.remove("flash-up", "flash-down");
      void row.offsetWidth;
      row.classList.add(isUp ? "flash-up" : "flash-down");
    }

    const formattedPrice = updated.price.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });

    const isPositive = updated.change >= 0;
    const arrow = isPositive ? "▲" : "▼";
    const color = isPositive ? "#00ff7f" : "#ff4c4c";

    priceEl.textContent = `$${formattedPrice}`;
    percentEl.textContent = `${arrow} $${Math.abs(updated.changeDollar ?? 0).toFixed(2)} (${Math.abs(updated.change).toFixed(2)}%)`;
    percentEl.style.color = color;
  });

  tickerData = newData;
}

let tickerInterval = null;
let secondsRemaining = 60;
let isRefreshing = false;

function startTickerCountdown() {
  const el = document.getElementById("ticker-refresh-timer");
  if (!el) return;

  tickerInterval = setInterval(async () => {
    if (isRefreshing) return;

    el.textContent = `Refresh in ${secondsRemaining}s`;
    secondsRemaining--;

    if (secondsRemaining < 0) {
      clearInterval(tickerInterval);

      isRefreshing = true;
      el.textContent = "Refreshing...";

      await refreshAllTickers();

      secondsRemaining = 60;
      isRefreshing = false;

      startTickerCountdown();
    }
  }, 1000);
}

/* =========================================================
   EVENT WATCH (STATIC DISPLAY)
   ========================================================= */

const EVENT_API = "/event-watch";
const EVENT_REFRESH_INTERVAL = 60000; // 1 minute

async function fetchEventWatch() {
  try {
    const res = await fetch(EVENT_API, { cache: "no-store" });
    const data = await res.json();
    if (!data || data.error) return;

    renderEventWatch(data);

  } catch (e) {
    console.log("Event Watch fetch failed");
  }
}

/** Fallback: make a slug readable and strip giant numeric tails */
function sanitizeSlugTitle(slug) {
  if (!slug) return "Unknown Event";

  let title = String(slug).replace(/[-_]+/g, " ").trim();

  // Remove a long tail of IDs: " ... 227 967 547 688 589 ..."
  title = title.replace(/(?:\s+\d{2,}){3,}\s*$/g, "").trim();

  // Collapse extra spaces
  title = title.replace(/\s{2,}/g, " ");

  // Title Case
  title = title.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());

  return title || "Unknown Event";
}

function renderEventWatch(data) {
  /* =============================
   DOUGHCON DISPLAY
  ============================= */
  document.querySelectorAll(".legend-item").forEach(el => {
    el.style.background = "transparent";
  });

  const active = document.querySelector(`.level-${data.doughcon}`);
  if (active) active.style.background = "rgba(255,255,255,0.08)";

  const doughEl = document.getElementById("doughcon-indicator");
  if (doughEl && data && data.doughcon !== undefined && data.doughcon !== null) {
    const level = Number(data.doughcon);
    const colors = {
      1: "#ff0000",
      2: "#ff5c00",
      3: "#ffae00",
      4: "#00c853",
      5: "#2196f3"
    };
    doughEl.textContent = `DOUGHCON ${level}`;
    doughEl.style.color = colors[level] || "#ffffff";
  }

  const container = document.getElementById("event-watch-content");
  if (!container) return;

  let html = "";

  /* =============================
     TOP TWO SPIKES
  ============================= */

  if (data.spike && data.spike.length > 0) {
    const topTwo = data.spike.slice(0, 2);
    html += `<div class="event-spike-row">`;

    topTwo.forEach(spike => {
      const distance = spike.distance != null
        ? `${Number(spike.distance).toFixed(2)} mi`
        : "";

      html += `
        <div class="spike-item">
          <div class="spike-name">
            ${(spike.place || "").replace(/\s*\(.*?\)/g, "")}
            <span style="opacity:0.6; font-size:14px; margin-left:8px;">
              ${distance}
            </span>
          </div>
          <div class="spike-percent">
            <span class="spike-arrow"></span>
            <span class="spike-value">
              ${spike.percentage != null ? spike.percentage : "--"}%
            </span>
            <span class="spike-label">Spike</span>
          </div>
        </div>
      `;
    });

    html += `</div>`;
  }

  /* =============================
     TOP 3 MARKETS
  ============================= */

  if (data.top_markets && data.top_markets.length > 0) {
    html += `<div class="event-markets">`;

    data.top_markets.slice(0, 3).forEach(market => {
      const pct = market.price != null ? Math.round(market.price * 100) : "--";

      // ✅ Prefer label, then backend title, fallback to cleaned slug
      const title =
        ((market.label && String(market.label).trim()) ||
        (market.title && String(market.title).trim()) ||
        sanitizeSlugTitle(market.slug))
        .replace(/\?\s*$/, ""); // remove trailing question mark

      const region = market.region
        ? market.region
            .replace(/_/g, " ")
            .toLowerCase()
            .replace(/\b\w/g, c => c.toUpperCase())
        : "";

      const image = market.image
        ? `<img src="${market.image}" class="market-image" />`
        : `<div class="market-image" style="background:#222;"></div>`;

      html += `
        <div class="market-row">
          <div class="market-left">
            ${image}
            <div class="market-question">
              ${title}
              <span class="market-region">${region}</span>
            </div>
          </div>
          <div class="market-price">
            ${pct}%
          </div>
        </div>
      `;
    });

    html += `</div>`;
  }

  container.innerHTML = html;
}

/* =========================================================
   Q3 - OIL / GAS SNAPSHOT
   ========================================================= */

const OIL_GAS_API = "/oil-gas-board";
const OIL_GAS_REFRESH_INTERVAL = 60000; // 1 minute

async function fetchOilGasBoard() {
  try {
    const res = await fetch(OIL_GAS_API, { cache: "no-store" });
    const data = await res.json();
    if (!data) {
      renderOilGasBoardError("No data returned from /oil-gas-board.");
      return;
    }
    if (data.error) {
      renderOilGasBoardError(data.error);
      return;
    }
    renderOilGasBoard(data);
  } catch (e) {
    console.log("Oil / Gas board fetch failed", e);
    renderOilGasBoardError("Fetch to /oil-gas-board failed.");
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function changeClass(change) {
  if (change == null || Number(change) === 0) return "flat";
  return Number(change) > 0 ? "up" : "down";
}

function renderChangeText(change, changeText) {
  const safeText = escapeHtml(String(changeText || "").replace(/^([+-])/, ""));

  if (change == null || Number(change) === 0) {
    return safeText;
  }

  const arrow = Number(change) > 0 ? "▲" : "▼";
  return `<span style="margin-right:6px;">${arrow}</span>${safeText}`;
}

function renderEnergyRows(rows) {
  return rows.map(row => `
    <div class="energy-row">
      <div class="energy-row-left">
        <div class="energy-label">${escapeHtml(row.label)}</div>
        <div class="energy-meta">${escapeHtml(row.meta || "").replace(/\s*\|\s*/g, "<br>")}</div>
      </div>
      <div class="energy-row-right">
        <div class="energy-value">${escapeHtml(row.value)}</div>
        <div class="energy-change ${changeClass(row.change)}">${renderChangeText(row.change, row.changeText)}</div>
      </div>
    </div>
  `).join("");
}

function renderOilGasBoard(data) {
  const container = document.getElementById("oil-gas-board");
  if (!container) return;

  const leftRows = Array.isArray(data.left_column) ? data.left_column : [];
  const rightRows = Array.isArray(data.right_column) ? data.right_column : [];

  container.innerHTML = `
    <div class="energy-card energy-card-left">
      <div class="energy-card-header">
        <div class="energy-card-title">Retail Fuel Averages</div>
        <div class="energy-card-note">Week over week</div>
      </div>
      <div class="energy-rows">
        ${renderEnergyRows(leftRows)}
      </div>
    </div>
    <div class="energy-card energy-card-right">
      <div class="energy-card-header">
        <div class="energy-card-title">Oil Futures</div>
        <div class="energy-card-note">${escapeHtml(data.right_card_note || "Front Month")}</div>
      </div>
      <div class="energy-rows">
        ${renderEnergyRows(rightRows)}
      </div>
    </div>
  `;
}

function renderOilGasBoardError(message) {
  const container = document.getElementById("oil-gas-board");
  if (!container) return;

  container.innerHTML = `
    <div class="energy-card" style="grid-column: 1 / -1;">
      <div class="energy-card-header">
        <div class="energy-card-title">Data Unavailable</div>
        <div class="energy-card-note">Q3 Debug</div>
      </div>
      <div class="energy-rows">
        <div class="energy-row">
          <div class="energy-row-left">
            <div class="energy-label">The oil / gas board did not load.</div>
            <div class="energy-meta">${escapeHtml(message || "Unknown error")}</div>
          </div>
          <div class="energy-row-right">
            <div class="energy-value">--</div>
            <div class="energy-change flat">Check /oil-gas-board</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

/* =========================================================
   NEWS (Q4)
   ========================================================= */

const NEWS_REFRESH_INTERVAL = 60000; // 1 minute
const NEWS_API = "/news";
const WEATHER_DASHBOARD_API = "/weather-dashboard";
const WEATHER_REFRESH_INTERVAL = 15 * 60 * 1000;
const Q4_ROTATE_INTERVAL = 20000;
const Q4_TRANSITION_MS = 350;
const Q4_VIEWS = [
  { type: "headlines" },
  { type: "weather", key: "hartford", label: "Hartford Focus" },
  { type: "weather", key: "regional", label: "Regional 7-Day" },
  { type: "weather", key: "outlook", label: "NOAA Outlooks" }
];

let weatherDashboardData = null;
let currentQ4ViewIndex = 0;
let q4TransitionInFlight = false;

async function fetchLatestHeadlines() {
  try {
    const res = await fetch(NEWS_API, { cache: "no-store" });
    return await res.json();
  } catch (err) {
    console.log("News fetch error:", err);
    return null;
  }
}

function renderHeadlines(headlines) {
  for (let i = 0; i < 3; i++) {
    const el = document.getElementById(`headline-${i + 1}`);
    if (!el) continue;

    const item = headlines[i];
    el.classList.remove("show");

    setTimeout(() => {
      if (!item) {
        el.innerHTML = "";
        return;
      }

      const safeTitle = item.title ?? "";
      const safeUrl = item.url ?? "#";
      const safeTime = item.time ?? "";

      el.innerHTML = `
        ${safeTime ? `<span class="news-time">${safeTime}</span>` : ""}
        <a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeTitle}</a>
      `;

      el.classList.add("show");
    }, 150);
  }
}

async function updateLatestHeadlines() {
  const data = await fetchLatestHeadlines();
  if (!data || !Array.isArray(data.headlines)) return;
  renderHeadlines(data.headlines);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function shortenSummary(value, maxLength = 60) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

function truncateSummary(value, maxLength = 60) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
}

function legacyWeatherIcon(shortForecast) {
  const forecast = String(shortForecast ?? "").toLowerCase();

  if (forecast.includes("thunder")) {
    return { symbol: "⛈", className: "storm", label: "Storm" };
  }
  if (forecast.includes("snow") || forecast.includes("sleet") || forecast.includes("flurr")) {
    return { symbol: "❄", className: "snow", label: "Snow" };
  }
  if (forecast.includes("rain") || forecast.includes("shower") || forecast.includes("drizzle")) {
    return { symbol: "☂", className: "rain", label: "Rain" };
  }
  if (forecast.includes("partly sunny") || forecast.includes("partly cloudy") || forecast.includes("mostly sunny")) {
    return { symbol: "⛅", className: "partly", label: "Partly sunny" };
  }
  if (forecast.includes("cloud") || forecast.includes("overcast")) {
    return { symbol: "☁", className: "cloud", label: "Cloudy" };
  }
  if (forecast.includes("fog") || forecast.includes("mist") || forecast.includes("haze")) {
    return { symbol: "〰", className: "fog", label: "Fog" };
  }
  if (forecast.includes("wind") || forecast.includes("breezy")) {
    return { symbol: "🌀", className: "wind", label: "Windy" };
  }

  return { symbol: "☀", className: "sun", label: "Sunny" };
}

function getWeatherIcon(shortForecast) {
  const forecast = String(shortForecast ?? "").toLowerCase();

  if (forecast.includes("thunder")) {
    return { symbol: "\u26c8", className: "storm", label: "Storm" };
  }
  if (forecast.includes("snow") || forecast.includes("sleet") || forecast.includes("flurr")) {
    return { symbol: "\u2744", className: "snow", label: "Snow" };
  }
  if (forecast.includes("rain") || forecast.includes("shower") || forecast.includes("drizzle")) {
    return { symbol: "\u{1F327}", className: "rain", label: "Rain" };
  }
  if (forecast.includes("partly sunny") || forecast.includes("partly cloudy") || forecast.includes("mostly sunny")) {
    return { symbol: "\u26c5", className: "partly", label: "Partly sunny" };
  }
  if (forecast.includes("cloud") || forecast.includes("overcast")) {
    return { symbol: "\u2601", className: "cloud", label: "Cloudy" };
  }
  if (forecast.includes("fog") || forecast.includes("mist") || forecast.includes("haze")) {
    return { symbol: "\u3030", className: "fog", label: "Fog" };
  }
  if (forecast.includes("wind") || forecast.includes("breezy")) {
    return { symbol: "\u{1F300}", className: "wind", label: "Windy" };
  }

  return { symbol: "\u2600", className: "sun", label: "Sunny" };
}

async function fetchWeatherDashboard() {
  try {
    const res = await fetch(WEATHER_DASHBOARD_API, { cache: "no-store" });
    return await res.json();
  } catch (err) {
    console.log("Weather dashboard fetch error:", err);
    return null;
  }
}

function renderRegionalWeatherView(data) {
  const cities = data?.regional?.cities ?? [];
  if (!cities.length) {
    return `<div class="weather-empty">Regional weather is temporarily unavailable.</div>`;
  }

  return `
    <div class="weather-view weather-grid-two">
      ${cities.map(city => `
        <div class="weather-city-panel">
          <div class="weather-city-header">
            <div class="weather-city-name">${escapeHtml(city.city)}</div>
          </div>
          <div class="weather-day-list">
            ${(city.days ?? []).slice(0, 7).map(day => {
              const icon = getWeatherIcon(day.summary);
              return `
              <div class="weather-day-row">
                <div class="weather-day-name">${escapeHtml(day.name)}</div>
                <div class="weather-day-temp">${escapeHtml(day.temperature_display)}</div>
                <div class="weather-day-icon weather-mini-icon weather-mini-icon-${escapeHtml(icon.className)}" aria-label="${escapeHtml(icon.label)}" title="${escapeHtml(icon.label)}">${escapeHtml(icon.symbol)}</div>
                <div class="weather-day-summary">${escapeHtml(truncateSummary(day.summary, 70))}</div>
              </div>
            `;
            }).join("")}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderHartfordWeatherView(data) {
  const current = data?.hartford?.current;
  const periods = data?.hartford?.extended ?? [];

  if (!current) {
    return `<div class="weather-empty">Hartford weather is temporarily unavailable.</div>`;
  }

  const currentIcon = getWeatherIcon(current.short_forecast);

  return `
    <div class="weather-view weather-hartford-layout">
      <div class="weather-hartford-today">
        <div class="weather-panel-title">Hartford Today</div>
        <div class="weather-hartford-current-temp">${escapeHtml(current.temperature_display)}</div>
        <div class="weather-hartford-current-name">${escapeHtml(current.name)}</div>
        <div class="weather-hartford-current-brief">
          <div class="weather-mini-icon weather-mini-icon-${escapeHtml(currentIcon.className)}" aria-label="${escapeHtml(currentIcon.label)}" title="${escapeHtml(currentIcon.label)}">${escapeHtml(currentIcon.symbol)}</div>
          <div class="weather-hartford-current-summary">${escapeHtml(current.short_forecast)}</div>
        </div>
        <div class="weather-hartford-current-detail">${escapeHtml(current.detail)}</div>
      </div>
      <div class="weather-city-panel">
        <div class="weather-panel-title">Hartford Extended</div>
        <div class="weather-mini-grid">
          ${periods.slice(0, 8).map(period => {
            const icon = getWeatherIcon(period.short_forecast);
            return `
            <div class="weather-mini-card">
              <div class="weather-mini-icon weather-mini-icon-${escapeHtml(icon.className)}" aria-label="${escapeHtml(icon.label)}" title="${escapeHtml(icon.label)}">${escapeHtml(icon.symbol)}</div>
              <div class="weather-mini-name">${escapeHtml(period.name)}</div>
              <div class="weather-mini-temp">${escapeHtml(period.temperature_display)}</div>
              <div class="weather-mini-summary">${escapeHtml(truncateSummary(period.short_forecast, 28))}</div>
            </div>
          `;
          }).join("")}
        </div>
      </div>
    </div>
  `;
}

function renderOutlookWeatherView(data) {
  const outlooks = data?.outlooks ?? [];
  if (!outlooks.length) {
    return `<div class="weather-empty">NOAA outlooks are temporarily unavailable.</div>`;
  }

  return `
    <div class="weather-view weather-outlook-grid">
      ${outlooks.map(outlook => `
        <div class="weather-outlook-card">
          <div class="weather-outlook-name">${escapeHtml(outlook.label)}</div>
          ${outlook.image_url ? `
            <div class="weather-outlook-image-wrap">
              <img
                class="weather-outlook-image"
                src="${escapeHtml(outlook.image_url)}"
                alt="${escapeHtml(outlook.label)}"
              >
            </div>
          ` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function buildWeatherViewHtml(viewKey, data) {
  if (!data) {
    return `<div class="weather-loading">Loading official weather and NOAA outlooks...</div>`;
  }

  if (data.error) {
    return `<div class="weather-empty">${escapeHtml(`Weather data unavailable: ${data.error}`)}</div>`;
  }

  if (viewKey === "regional") return renderRegionalWeatherView(data);
  if (viewKey === "hartford") return renderHartfordWeatherView(data);
  return renderOutlookWeatherView(data);
}

function renderQ4View() {
  const headlinesShell = document.getElementById("q4-headlines-shell");
  const weatherShell = document.getElementById("q4-weather-shell");
  const stage = document.getElementById("weather-rotator");
  const label = document.getElementById("weather-view-label");
  if (!headlinesShell || !weatherShell || !stage || !label) return;

  const view = Q4_VIEWS[currentQ4ViewIndex];

  headlinesShell.classList.remove("active");
  weatherShell.classList.remove("active");

  if (view.type === "headlines") {
    headlinesShell.classList.add("active");
    return;
  }

  weatherShell.classList.add("active");
  label.textContent = view.label;
  stage.innerHTML = buildWeatherViewHtml(view.key, weatherDashboardData);
}

async function updateWeatherDashboard() {
  const data = await fetchWeatherDashboard();
  if (!data) return;
  weatherDashboardData = data;
  const currentView = Q4_VIEWS[currentQ4ViewIndex];
  if (currentView.type === "weather") {
    renderQ4View();
  }
}

async function rotateQ4View() {
  const headlinesShell = document.getElementById("q4-headlines-shell");
  const weatherShell = document.getElementById("q4-weather-shell");
  if (!headlinesShell || !weatherShell || q4TransitionInFlight) return;

  q4TransitionInFlight = true;

  const activeShell = headlinesShell.classList.contains("active") ? headlinesShell : weatherShell;
  activeShell.style.opacity = "0";

  await new Promise(resolve => setTimeout(resolve, Q4_TRANSITION_MS));

  activeShell.style.opacity = "1";
  currentQ4ViewIndex = (currentQ4ViewIndex + 1) % Q4_VIEWS.length;
  renderQ4View();

  q4TransitionInFlight = false;
}

/* =========================================================
   CLOCK (Date + Time)
   ========================================================= */

function startClock() {
  setInterval(() => {
    const el = document.getElementById("clock");
    if (!el) return;

    const now = new Date();

    const date = now.toLocaleDateString(undefined, {
      weekday: "long",
      month: "long",
      day: "numeric"
    });

    const time = now.toLocaleTimeString();

    el.textContent = `${date} • ${time}`;
  }, 1000);
}

/* =========================================================
   FULLSCREEN TOGGLE (SAFE ADDITION)
   ========================================================= */

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(err => {
      console.log("Fullscreen error:", err);
    });
  } else {
    document.exitFullscreen();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("fullscreen-toggle");
  if (btn) btn.addEventListener("click", toggleFullscreen);
});

document.addEventListener("keydown", (e) => {
  if (e.key && e.key.toLowerCase() === "f") toggleFullscreen();
});

// When fullscreen changes, re-apply layout so Q2 is always correct
document.addEventListener("fullscreenchange", () => {
  initTopRightQuadrantLayout();
});

/* =========================================================
   BOOT SEQUENCE
   ========================================================= */

initTopRightQuadrantLayout();
startClock();

updateAsset();
updateTickerPanel();      // build empty grid first
refreshAllTickers();      // then fill it
startTickerCountdown();

updateHenryHub(); // initial load
setInterval(() => {
  if (q1TransitionInFlight) return;
  if (q1Mode === "gas") updateHenryHub();
  if (q1Mode === "electric") updateElectric();
}, 60000);

updateLatestHeadlines();
setInterval(updateLatestHeadlines, NEWS_REFRESH_INTERVAL);

updateWeatherDashboard();
setInterval(updateWeatherDashboard, WEATHER_REFRESH_INTERVAL);
renderQ4View();
setInterval(rotateQ4View, Q4_ROTATE_INTERVAL);

fetchOilGasBoard();
setInterval(fetchOilGasBoard, OIL_GAS_REFRESH_INTERVAL);

setInterval(rotateAssets, 5000);
setInterval(updateAsset, 60000);

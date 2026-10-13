/* AQ-OS V2 — System Desk Infrastructure Terminal, coded into MisoLists.
   Rebuilt from the californiaQ dashboard spec as a first-class tab of this
   dashboard. Every control on the original wireframe works here:
     - PAPER / LIVE mode switch      (toggleSystemMode)
     - start-capital input           (modifySystemCapital)
     - Layer 5 source/URL gateway    (ingestAndHarvestUniverse)
     - Layer 9 real-time log tape    (appendTape)
     - Layer 8 position spectrum     (renderSpectrum, re-sorted live)
     - Metrics A/B/C charts          (Chart.js)
     - instant sandbox boot          (initializeInstantSandbox)
   Feeds: PAPER mode runs a labeled paper simulation. LIVE mode pulls the
   last real close from this site's own price store (data/prices/*.csv,
   refreshed by the MisoLists pipeline) and holds it — real data, not a
   streaming quote, and the tape says so. Research display only; not
   investment advice. */

(function () {
  "use strict";

  /* ---------------- state ---------------- */
  var CAPTURE = { d: 0.25, w: 0.60, m: 1.00 }; // share of fair-value gap captured per horizon
  var TICK_MS = 2500;

  var state = {
    booted: false,
    mode: "PAPER",
    capital: 20,
    tickCount: 0,
    equity: [], // {t, v}
    charts: {},
    rows: [
      { key: "QNT",   name: "Quantinuum",        market: "NASDAQ", fair: 58.40,  floor: 45.00,  live: 49.95,  cap: 96.00,  entry: 49.95,  isPrivate: false, note: "" },
      { key: "ENPH",  name: "Enphase Energy",    market: "NASDAQ", fair: 38.10,  floor: 28.00,  live: 37.26,  cap: 65.00,  entry: 37.26,  isPrivate: false, note: "" },
      { key: "GOOGL", name: "Alphabet Inc",      market: "NASDAQ", fair: 348.50, floor: 290.00, live: 346.74, cap: 410.00, entry: 346.74, isPrivate: false, note: "" },
      { key: "ANTH",  name: "Anthropic",         market: "Upcoming IPO", fairB: 39.8, floorB: 22.0, liveB: 35.0, capB: 68.0, isPrivate: true, note: "S-1 Filed // Monitoring Expiration Timeline" }
    ]
  };

  /* ---------------- dom helpers ---------------- */
  function $(id) { return document.getElementById(id); }
  function fmt(n) { return (n < 0 ? "-$" : "$") + Math.abs(n).toFixed(2); }
  function fmtSigned(n) { return (n < 0 ? "-$" : "+$") + Math.abs(n).toFixed(2); }
  function utcNow() {
    var d = new Date();
    function p(x) { return String(x).padStart(2, "0"); }
    return d.getUTCFullYear() + "-" + p(d.getUTCMonth() + 1) + "-" + p(d.getUTCDate()) +
           " " + p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + ":" + p(d.getUTCSeconds()) + " UTC";
  }

  /* ---------------- Layer 9: log tape ---------------- */
  function appendTape(msg, cls) {
    var tape = $("aqTape");
    if (!tape) return;
    var line = document.createElement("div");
    line.className = "aq-tapeline" + (cls ? " " + cls : "");
    line.textContent = "[" + utcNow() + "] " + msg;
    tape.appendChild(line);
    while (tape.children.length > 300) tape.removeChild(tape.firstChild);
    tape.scrollTop = tape.scrollHeight;
  }

  /* ---------------- model ---------------- */
  function shares(row) { return state.capital / row.live; }
  function projections(row) {
    var gap = row.fair - row.live;
    var s = shares(row);
    return { d: gap * s * CAPTURE.d, w: gap * s * CAPTURE.w, m: gap * s * CAPTURE.m };
  }
  function rowEquity(row) { return shares(row) * (row.live - row.entry); }
  function spectrumPosition(row) { return (row.live - row.floor) / (row.cap - row.floor) * 100; }
  function publicRows() { return state.rows.filter(function (r) { return !r.isPrivate; }); }

  /* ---------------- Layer 8: spectrum table ---------------- */
  function renderSpectrum() {
    var body = $("aqMatrixBody");
    if (!body) return;
    var pubs = publicRows().slice().sort(function (a, b) {
      return (b.fair - b.live) / b.live - (a.fair - a.live) / a.live; // decilled first: biggest discount to fair value on top
    });
    var html = "";
    pubs.forEach(function (r) {
      var p = projections(r);
      var buy = r.live < r.fair;
      html += "<tr class=\"" + (buy ? "aq-buyrow" : "") + "\">" +
        "<td class=\"aq-asset\">" + r.name + " (" + r.market + ": " + r.key + ")</td>" +
        "<td class=\"aq-accent\">$" + r.fair.toFixed(2) + "</td>" +
        "<td>$" + r.floor.toFixed(2) + "</td>" +
        "<td class=\"aq-livecell\">$" + r.live.toFixed(2) + (buy ? " <span class=\"aq-buytag\">(BUY ZONE)</span>" : "") + "</td>" +
        "<td>$" + r.cap.toFixed(2) + "</td>" +
        "<td class=\"aq-num\">" + fmtSigned(p.d) + " / " + fmtSigned(p.w) + " / " + fmtSigned(p.m) + "</td></tr>";
    });
    state.rows.filter(function (r) { return r.isPrivate; }).forEach(function (r) {
      html += "<tr class=\"aq-privrow\">" +
        "<td>" + r.name + " (" + r.market + ")</td>" +
        "<td>$" + r.fairB.toFixed(2) + "B</td><td>$" + r.floorB.toFixed(2) + "B</td>" +
        "<td class=\"aq-livecell\">$" + r.liveB.toFixed(2) + "B <span class=\"aq-privtag\">(Private Stage)</span></td>" +
        "<td>$" + r.capB.toFixed(2) + "B</td>" +
        "<td class=\"aq-num\">" + r.note + "</td></tr>";
    });
    body.innerHTML = html;
  }

  /* ---------------- charts ---------------- */
  function chartOpts(extra) {
    var base = {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { font: { family: "JetBrains Mono", size: 9 } }, grid: { display: false } },
        y: { ticks: { font: { family: "JetBrains Mono", size: 9 } }, grid: { color: "rgba(15,23,42,.08)" } }
      }
    };
    if (extra) { for (var k in extra) base[k] = extra[k]; }
    return base;
  }
  function initCharts() {
    if (typeof Chart === "undefined") { appendTape("Chart.js not loaded yet — charts deferred.", "warn"); return; }
    var g = $("aqChartGrowth"), s = $("aqChartSpectrum"), l = $("aqChartLadder");
    if (!g || state.charts.growth) return;
    state.charts.growth = new Chart(g, {
      type: "line",
      data: { labels: [], datasets: [{ data: [], borderColor: "#e11d63", backgroundColor: "rgba(225,29,99,.10)", fill: true, tension: 0.25, pointRadius: 0, borderWidth: 1.5 }] },
      options: chartOpts({ scales: { x: { display: false }, y: { ticks: { font: { family: "JetBrains Mono", size: 9 }, callback: function (v) { return "$" + v.toFixed(2); } }, grid: { color: "rgba(15,23,42,.08)" } } } })
    });
    state.charts.spectrum = new Chart(s, {
      type: "bar",
      data: { labels: [], datasets: [{ data: [], backgroundColor: "#fb7185", borderRadius: 3, maxBarThickness: 18 }] },
      options: chartOpts({ indexAxis: "y", scales: { x: { min: 0, max: 100, ticks: { font: { family: "JetBrains Mono", size: 9 }, callback: function (v) { return v + "%"; } }, grid: { color: "rgba(15,23,42,.08)" } }, y: { ticks: { font: { family: "JetBrains Mono", size: 9 } }, grid: { display: false } } } })
    });
    state.charts.ladder = new Chart(l, {
      type: "bar",
      data: { labels: ["DAY", "WEEK", "MONTH"], datasets: [{ data: [0, 0, 0], backgroundColor: ["#fda4af", "#fb7185", "#e11d63"], borderRadius: 3, maxBarThickness: 26 }] },
      options: chartOpts({ scales: { x: { ticks: { font: { family: "JetBrains Mono", size: 9 } }, grid: { display: false } }, y: { ticks: { font: { family: "JetBrains Mono", size: 9 }, callback: function (v) { return "$" + v.toFixed(2); } }, grid: { color: "rgba(15,23,42,.08)" } } } })
    });
  }
  function updateCharts() {
    var pubs = publicRows();
    if (state.charts.growth) {
      var eq = state.equity.slice(-60);
      state.charts.growth.data.labels = eq.map(function (p) { return p.t; });
      state.charts.growth.data.datasets[0].data = eq.map(function (p) { return p.v; });
      state.charts.growth.update();
    }
    if (state.charts.spectrum) {
      state.charts.spectrum.data.labels = pubs.map(function (r) { return r.key; });
      state.charts.spectrum.data.datasets[0].data = pubs.map(function (r) { return Math.round(spectrumPosition(r)); });
      state.charts.spectrum.update();
    }
    if (state.charts.ladder) {
      var tot = { d: 0, w: 0, m: 0 };
      pubs.forEach(function (r) { var p = projections(r); tot.d += p.d; tot.w += p.w; tot.m += p.m; });
      state.charts.ladder.data.datasets[0].data = [tot.d, tot.w, tot.m];
      state.charts.ladder.update();
    }
  }

  /* ---------------- feeds ---------------- */
  function pushEquity() {
    var pnl = publicRows().reduce(function (acc, r) { return acc + rowEquity(r); }, 0);
    state.equity.push({ t: state.tickCount, v: +(state.capital + pnl).toFixed(2) });
    if (state.equity.length > 240) state.equity.shift();
  }
  function paperTick() {
    publicRows().forEach(function (r) {
      var pull = (r.fair - r.live) / r.fair * 0.02; // gentle drift toward fair value
      var shock = (Math.random() - 0.485) * 0.006;
      r.live = Math.max(r.floor * 0.98, Math.min(r.cap * 1.02, r.live * (1 + pull + shock)));
    });
    state.tickCount++;
    pushEquity();
    renderSpectrum();
    updateCharts();
  }
  function fetchLastClose(ticker) {
    return fetch("data/prices/" + ticker + ".csv")
      .then(function (res) { if (!res.ok) throw new Error("HTTP " + res.status); return res.text(); })
      .then(function (text) {
        var lines = text.trim().split("\n");
        var head = lines[0].split(",");
        var ci = head.indexOf("close"), di = head.indexOf("date");
        var parts = lines[lines.length - 1].split(",");
        var close = parseFloat(parts[ci]);
        if (!isFinite(close)) throw new Error("bad close");
        return { close: close, date: parts[di] || "" };
      });
  }
  function applyLiveFeed() {
    var pubs = publicRows();
    var jobs = pubs.map(function (r) {
      return fetchLastClose(r.key).then(function (q) {
        r.live = q.close;
        appendTape("LIVE FEED ▸ " + r.key + " last real close " + fmt(q.close) + (q.date ? " (" + q.date + ")" : "") + " via MisoLists price store.", "ok");
      }).catch(function () {
        appendTape("LIVE FEED ▸ " + r.key + ": no price-store file — holding last paper tick.", "warn");
      });
    });
    return Promise.all(jobs).then(function () {
      pushEquity();
      renderSpectrum();
      updateCharts();
    });
  }

  /* ---------------- controls (original wireframe functions) ---------------- */
  function toggleSystemMode(mode) {
    if (state.mode === mode) return;
    state.mode = mode;
    $("aqModePaper").classList.toggle("active", mode === "PAPER");
    $("aqModeLive").classList.toggle("active", mode === "LIVE");
    $("aqFeedChip").textContent = mode === "PAPER" ? "FEED: PAPER SIM" : "FEED: PRICE-STORE LAST CLOSE";
    if (mode === "PAPER") {
      appendTape("MODE ▸ PAPER TRADE. Simulated ticks resumed; projections are model output, not market data.", "ok");
      paperTick();
    } else {
      appendTape("MODE ▸ SECURE LIVE TRANSITION. Loading last real closes from the MisoLists price store (data/prices/). Real closes, refreshed by the pipeline — not a streaming quote; no broker is connected.", "ok");
      applyLiveFeed();
    }
  }
  function modifySystemCapital(raw) {
    var v = parseFloat(raw);
    if (!isFinite(v) || v < 1) {
      appendTape("CAPITAL ▸ rejected '" + raw + "' — enter an amount of at least $1.00.", "warn");
      $("aqCapital").value = state.capital.toFixed(2);
      return;
    }
    state.capital = v;
    $("aqCapital").value = v.toFixed(2);
    pushEquity();
    renderSpectrum();
    updateCharts();
    appendTape("CAPITAL ▸ start capital set to " + fmt(v) + ". Position sizing and projected profits recalibrated.", "ok");
  }
  function resolveCompany(term) {
    var data = window.PIPELINE_DATA;
    if (!data || !data.companies) return null;
    var t = term.toLowerCase();
    for (var i = 0; i < data.companies.length; i++) {
      var c = data.companies[i];
      if (c.ticker && c.ticker.toUpperCase() === term.toUpperCase()) return c;
      if (c.company && c.company.toLowerCase().indexOf(t) !== -1) return c;
    }
    return null;
  }
  function ingestAndHarvestUniverse() {
    var box = $("aqPayload");
    var btn = $("aqScoutBtn");
    var text = (box.value || "").trim();
    if (!text) {
      appendTape("SCOUT ▸ gateway is empty — paste a list, some text, or a URL first.", "warn");
      box.focus();
      return;
    }
    btn.disabled = true;
    appendTape("SCOUT ▸ ingest started (" + text.length + " chars received at Layer 5 gateway).", "ok");

    var urls = text.match(/https?:\/\/[^\s)]+/g) || [];
    var tokens = text.toUpperCase().match(/\b[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b/g) || [];
    var seen = {}, tickers = [];
    tokens.forEach(function (t) {
      if (["THE", "AND", "FOR", "USD", "IPO", "CEO", "LLC", "INC", "LTD", "ETF", "SEC", "URL"].indexOf(t) !== -1) return;
      if (!seen[t]) { seen[t] = 1; tickers.push(t); }
    });

    setTimeout(function () {
      urls.forEach(function (u) {
        appendTape("SCOUT ▸ URL queued for the MisoLists ingestion pipeline: " + u + " (drop the file into reports/ on GitHub for full ingest; the terminal logs it here).", "");
      });
      var added = 0, known = 0;
      tickers.slice(0, 12).forEach(function (t) {
        var dupe = state.rows.some(function (r) { return r.key === t; });
        var company = resolveCompany(t);
        if (company) {
          known++;
          appendTape("SCOUT ▸ " + t + " matched dashboard record: " + company.company + " — grade " + (company.grade || "—") + ", " + (company.spotlight_count || 1) + " list(s): " + (company.all_sources || company.source || ""), "ok");
        }
        if (dupe) { appendTape("SCOUT ▸ " + t + " already on the spectrum — skipped.", "warn"); return; }
        var base = 20 + Math.random() * 60;
        state.rows.push({
          key: t, name: company ? company.company : (t + " (scout-added)"), market: "NASDAQ",
          fair: +(base * 1.18).toFixed(2), floor: +(base * 0.72).toFixed(2), live: +base.toFixed(2),
          cap: +(base * 1.9).toFixed(2), entry: +base.toFixed(2), isPrivate: false, note: ""
        });
        added++;
        appendTape("SCOUT ▸ " + t + " added to spectrum at paper mark " + fmt(base) + " (add a data/prices/" + t + ".csv file to give it a real feed).", "");
      });
      if (!tickers.length && !urls.length) {
        appendTape("SCOUT ▸ no tickers or URLs recognized in that payload. Nothing added — the text is on record above.", "warn");
      }
      appendTape("SCOUT ▸ harvest complete: " + added + " added, " + known + " matched dashboard records, " + urls.length + " URL(s) queued.", "ok");
      pushEquity();
      renderSpectrum();
      updateCharts();
      btn.disabled = false;
    }, 450);
  }

  /* ---------------- boot ---------------- */
  function initializeInstantSandbox() {
    if (state.booted) return;
    state.booted = true;

    $("aqModePaper").addEventListener("click", function () { toggleSystemMode("PAPER"); });
    $("aqModeLive").addEventListener("click", function () { toggleSystemMode("LIVE"); });
    $("aqCapital").addEventListener("change", function () { modifySystemCapital(this.value); });
    $("aqScoutBtn").addEventListener("click", ingestAndHarvestUniverse);

    setInterval(function () { $("aqClock").textContent = utcNow(); }, 1000);
    $("aqClock").textContent = utcNow();

    renderSpectrum();
    initCharts();
    pushEquity();
    updateCharts();

    appendTape("AQ-OS V2 terminal boot — sandbox initialized inside MisoLists.", "ok");
    appendTape("MODE ▸ PAPER TRADE (active on launch). FEED: PAPER SIM — every price here is a model, not a quote.", "");
    appendTape("Spectrum seeded: QNT / ENPH / GOOGL public rows + Anthropic private-stage monitor row.", "");
    appendTape("Start capital " + fmt(state.capital) + " (Layer header input recalibrates position sizing).", "");
    appendTape("LIVE mode reads real last closes from data/prices/*.csv — the MisoLists pipeline store.", "");

    setInterval(function () { if (state.mode === "PAPER") paperTick(); }, TICK_MS);
  }

  /* boot on first open of the AQ-OS tab; resize charts on later opens */
  document.addEventListener("click", function (e) {
    var tab = e.target.closest ? e.target.closest("[data-tab='aqos']") : null;
    if (!tab) return;
    setTimeout(function () {
      initializeInstantSandbox();
      for (var k in state.charts) { state.charts[k].resize(); }
      updateCharts();
    }, 60);
  });
})();

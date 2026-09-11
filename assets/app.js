/* The Upper Tier */
(function () {
  'use strict';
  const D = window.PIPELINE_DATA || {};
  const companies = D.companies || [];
  const themeToggle = document.querySelector('[data-theme-toggle]');
  const html = document.documentElement;

  // ---- Theme ----
  let theme = html.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light');
  function applyTheme(t) {
    html.setAttribute('data-theme', t);
    if (themeToggle) themeToggle.innerHTML = t === 'dark'
      ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
      : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  }
  applyTheme(theme);
  themeToggle && themeToggle.addEventListener('click', () => { theme = theme === 'dark' ? 'light' : 'dark'; applyTheme(theme); rebuildCharts(); });

  // ---- Helpers ----
  const $ = s => document.querySelector(s);
  const esc = s => (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
  const num = v => (v == null || v === '' || isNaN(v)) ? null : Number(v);
  const probNum = p => { if (!p) return null; const m = String(p).match(/(\d+(\.\d+)?)/); return m ? Number(m[1]) : null; };
  const fmtDate = s => { if (!s) return '—'; try { const d = new Date(s); if (isNaN(d)) return s; return d.toLocaleDateString('en-US', { year:'numeric', month:'short', day:'2-digit' }); } catch { return s; } };
  const fmtBytes = b => b > 1e6 ? (b/1e6).toFixed(1)+' MB' : b > 1e3 ? (b/1e3).toFixed(0)+' KB' : b+' B';

  // ---- Event code → plain-language label (Primary Event / Thematic Probability) ----
  // Codes (e.g. E14) map to the thematic driver they reference in the source briefings.
  const EVENT_MAP = {
    'E1':  'US–China tech competition',
    'E3':  'Health security',
    'E4':  'Food systems',
    'E6':  'Counterspace / ASAT',
    'E7':  'Nuclear proliferation',
    'E9':  'Armed conflict',
    'E10': 'Cyber',
    'E11': 'International order fragmentation',
    'E12': 'Climate strains',
    'E14': 'AI disruption',
    'E15': 'Societal fragmentation',
    'E17': 'Pandemic / biosecurity',
    'E21': 'Russia asymmetric reliance',
    'E22': 'African market persistence',
    'E26': 'Gray-zone competition'
  };
  const eventLabel = code => { if (!code || code === 'N/A') return 'No primary theme'; const d = EVENT_MAP[code]; return d ? `${code} · ${d}` : code; };

  function toast(msg) {
    const t = $('#toast'); t.textContent = msg; t.classList.add('show');
    clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2200);
  }

  // ---- Header meta ----
  $('#refresh-time').textContent = D.generated_at ? new Date(D.generated_at).toLocaleString('en-US', { month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit' }) : '—';
  $('#source-count').textContent = (D.lineage || []).length;

  // ---- KPIs ----
  const scores = companies.map(c => num(c.total_score)).filter(v => v != null).sort((a,b)=>a-b);
  const median = scores.length ? (scores.length % 2 ? scores[(scores.length-1)/2] : (scores[scores.length/2-1]+scores[scores.length/2])/2) : 0;
  const probs = companies.map(c => probNum(c.thematic_probability)).filter(v => v != null);
  const avgProb = probs.length ? Math.round(probs.reduce((a,b)=>a+b,0)/probs.length) : 0;
  const sectors = [...new Set(companies.map(c => (c.sector||'').split(' / ')[0]).filter(Boolean))];
  const aCount = companies.filter(c => c.grade === 'A').length;
  $('#kpi-total').textContent = companies.length;
  $('#kpi-a').textContent = aCount;
  $('#kpi-a-pct').textContent = `${Math.round(aCount/companies.length*100)}% of pipeline`;
  $('#kpi-median').textContent = Math.round(median);
  $('#kpi-thematic').textContent = avgProb + '%';
  $('#kpi-sectors').textContent = sectors.length;

  // ---- Filters ----
  const grades = ['A','B','C','D','F'].filter(g => companies.some(c => c.grade === g));
  const gradeSel = $('#filter-grade');
  grades.forEach(g => { const o = document.createElement('option'); o.value = g; o.textContent = 'Grade ' + g; gradeSel.appendChild(o); });
  const sectorSel = $('#filter-sector');
  sectors.sort().forEach(s => { const o = document.createElement('option'); o.value = s; o.textContent = s; sectorSel.appendChild(o); });
  const events = [...new Set(companies.map(c => c.primary_event).filter(Boolean))].sort();
  const eventSel = $('#filter-event');
  events.forEach(e => { const o = document.createElement('option'); o.value = e; o.textContent = eventLabel(e); eventSel.appendChild(o); });

  function filtered() {
    const q = $('#search').value.trim().toLowerCase();
    const g = gradeSel.value, sec = sectorSel.value, ev = eventSel.value;
    return companies.filter(c => {
      if (g && c.grade !== g) return false;
      if (sec && !(c.sector||'').startsWith(sec)) return false;
      if (ev && c.primary_event !== ev) return false;
      if (q) {
        const hay = [c.company, c.sector, c.primary_event, c.source, c.category, c.notes, c.funding_stage].filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  // ---- Render colored table (Master Pipeline Tracker, 2nd tab) ----
  function renderColored(rows) {
    const tb = $('#table-colored tbody'); tb.innerHTML = '';
    if (!rows.length) { tb.innerHTML = '<tr><td colspan="10" class="muted" style="text-align:center;padding:2rem">No entities match the current filters.</td></tr>'; return; }
    const frag = document.createDocumentFragment();
    rows.forEach(c => {
      const tr = document.createElement('tr');
      const fs = esc(c.funding_stage||'');
      const ticker = fs.match(/\(([A-Z0-9: ]+)\)/);
      tr.innerHTML = `
        <td>${esc(c.company)}${ticker?`<div class="ticker">${ticker[1]}</div>`:''}</td>
        <td>${c.primary_event?`<span class="theme-chip" title="${esc(eventLabel(c.primary_event))}">${esc(eventLabel(c.primary_event))}</span>`:'—'}</td>
        <td><span class="prob">${esc(c.thematic_probability||'—')}</span></td>
        <td>${esc(c.category||'—')}</td>
        <td class="cell-stage">${fs}</td>
        <td class="cell-date">${fmtDate(c.ipo_date)}</td>
        <td>${esc(c.sector||'—')}</td>
        <td class="notes" title="${esc(c.source||'')}">${esc(c.source||'—')}</td>
        <td class="notes" title="${esc(c.notes||'')}">${esc(c.notes||'')}</td>
        <td>${c.historical_flag==='Yes'?'<span class="flag-yes">Yes</span>':'<span class="flag-no">No</span>'}</td>`;
      frag.appendChild(tr);
    });
    tb.appendChild(frag);
  }

  // ---- Render graded table ----
  function renderGraded(rows) {
    const tb = $('#table-graded tbody'); tb.innerHTML = '';
    if (!rows.length) { tb.innerHTML = '<tr><td colspan="11" class="muted" style="text-align:center;padding:2rem">No entities match the current filters.</td></tr>'; return; }
    const frag = document.createDocumentFragment();
    const sorted = [...rows].sort((a,b)=>(num(b.total_score)||0)-(num(a.total_score)||0));
    sorted.forEach(c => {
      const tr = document.createElement('tr');
      const total = num(c.total_score);
      const bar = (v, mx) => { const n = num(v); if (n==null) return '<span class="muted">—</span>'; const pct = Math.max(0, Math.min(100, Math.abs(n)/mx*100)); const neg = n<0; return `<div class="score-bar"><div class="score-track"><div class="score-fill" style="width:${pct}%;${neg?'background:var(--grade-d-fg)':''}"></div></div><span class="score-val">${n}</span></div>`; };
      tr.innerHTML = `
        <td>${esc(c.company)}</td>
        <td>${c.grade?`<span class="grade-badge grade-${c.grade}">${c.grade}</span>`:'—'}</td>
        <td class="num">${total!=null?total:'—'}</td>
        <td>${bar(c.stage_score,25)}</td>
        <td>${bar(c.financial_score,30)}</td>
        <td>${bar(c.capital_score,20)}</td>
        <td>${bar(c.market_score,15)}</td>
        <td>${bar(c.risk_adj,15)}</td>
        <td>${esc(c.sector||'—')}</td>
        <td class="notes" title="${esc(c.stage_rationale||'')}">${esc(c.stage_rationale||'')}</td>
        <td class="notes" title="${esc(c.financial_rationale||'')}">${esc(c.financial_rationale||'')}</td>`;
      frag.appendChild(tr);
    });
    tb.appendChild(frag);
  }

  // ---- Methodology (Graded, 2nd tab) ----
  function renderMethodology() {
    const wrap = $('#methodology-body');
    const lines = D.methodology || [];
    let html2 = '';
    lines.forEach(raw => {
      const ln = String(raw).trim();
      if (!ln) return;
      if (/^TITLE:/i.test(ln)) html2 += `<div class="meth-title">${esc(ln.replace(/^TITLE:\s*/i,''))}</div>`;
      else if (/^FORMULA:/i.test(ln)) html2 += `<p class="meth-line"><strong>${esc(ln)}</strong></p>`;
      else if (/^Range:/i.test(ln)) html2 += `<p class="meth-line meth-section">${esc(ln)}</p>`;
      else if (/^\d+\./.test(ln)) html2 += `<p class="meth-line meth-section">${esc(ln)}</p>`;
      else if (/^[a-z]\)/i.test(ln) || /^[+~-]/.test(ln)) html2 += `<p class="meth-line" style="padding-left:1rem">${esc(ln)}</p>`;
      else if (/^(WHAT WAS|WHY|HOW TO)/.test(ln)) html2 += `<p class="meth-line meth-section">${esc(ln)}</p>`;
      else html2 += `<p class="meth-line">${esc(ln)}</p>`;
    });
    wrap.innerHTML = html2;

    // colored summary
    const sum = $('#colored-summary-body'); let sh = '';
    (D.colored_summary||[]).forEach(row => {
      const k = row[0], v = row[1];
      if (!k && !v) return;
      sh += `<div class="sum-row">${k?`<div class="sum-key">${esc(k)}</div>`:''}${v?`<div class="sum-val">${esc(v)}</div>`:''}</div>`;
    });
    sum.innerHTML = sh || '<p class="muted">No summary recorded.</p>';
  }

  // ---- Lineage ----
  function renderLineage() {
    const tb = $('#table-lineage tbody'); tb.innerHTML = '';
    (D.lineage||[]).forEach(f => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><strong>${esc(f.name)}</strong></td><td class="ticker">${esc(f.sha256)}…</td><td>${fmtBytes(f.size)}</td><td>${f.ingested_at?new Date(f.ingested_at).toLocaleString('en-US'):'—'}</td>`;
      tb.appendChild(tr);
    });
    // knowledge base cards
    const kb = $('#kb-grid'); kb.innerHTML = '';
    const cards = [
      { title: 'Executive Briefing (PDF)', meta: `${D.pdf_pages} pages · Global IGO/NGO horizon analysis` },
      { title: '50 World Orgs Dataset', meta: `55 sheets · master overview + deep dives` },
      { title: 'IC Future Scenarios 2026', meta: `${(D.ic_sheets||[]).length} sheets · DNI/NIE forecasts` },
      { title: 'Master Tracker (Colored)', meta: `2 tabs · thematic pipeline view` },
      { title: 'Master Tracker (Graded)', meta: `2 tabs · scored methodology` },
    ];
    cards.forEach(c => { const d=document.createElement('div'); d.className='kb-card'; d.innerHTML=`<div class="kb-title">${esc(c.title)}</div><div class="kb-meta">${esc(c.meta)}</div>`; kb.appendChild(d); });
  }

  // ---- Charts ----
  let chartGrade, chartTheme;
  function chartColors() { return getComputedStyle(document.documentElement).cssPropertySupported ? null : null; }
  function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function rebuildCharts() {
    const grid = cssVar('--color-border');
    const muted = cssVar('--color-text-muted');
    const accent = cssVar('--accent');
    const ticks = { color: muted, font: { family: 'DM Sans', size: 11 } };
    Chart.defaults.font.family = 'DM Sans';
    Chart.defaults.color = muted;

    // grade dist
    const gdata = ['A','B','C','D','F'].map(g => companies.filter(c=>c.grade===g).length);
    const gColors = ['--grade-a-fg','--grade-b-fg','--grade-c-fg','--grade-d-fg','--grade-f-fg'].map(v => cssVar(v));
    const totalGraded = gdata.reduce((a,b)=>a+b,0);
    const valueLabelPlugin = {
      id: 'valueLabels',
      afterDatasetsDraw(chart) {
        const { ctx } = chart;
        const ds = chart.data.datasets[0];
        ctx.save();
        ctx.font = '600 12px DM Sans';
        ctx.fillStyle = cssVar('--color-text');
        ctx.textAlign = 'center';
        chart.getDatasetMeta(0).data.forEach((bar, i) => {
          const v = ds.data[i];
          ctx.fillText(String(v), bar.x, bar.y - 6);
        });
        ctx.restore();
      }
    };
    if (chartGrade) chartGrade.destroy();
    chartGrade = new Chart($('#chart-grade'), {
      type: 'bar',
      plugins: [valueLabelPlugin],
      data: { labels: ['A','B','C','D','F'], datasets: [{ data: gdata, backgroundColor: gColors, borderRadius: 6, maxBarThickness: 54 }] },
      options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 22 } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => c.parsed.y + ' entities (' + Math.round(c.parsed.y/totalGraded*100) + '%)' } } }, scales: { x: { grid: { display: false }, ticks }, y: { beginAtZero: true, grid: { color: grid }, ticks } } }
    });

    // theme distribution (top themes by avg prob)
    const themeMap = {};
    companies.forEach(c => { if (!c.primary_event) return; if (!themeMap[c.primary_event]) themeMap[c.primary_event] = { count: 0, probs: [] }; themeMap[c.primary_event].count++; const p = probNum(c.thematic_probability); if (p!=null) themeMap[c.primary_event].probs.push(p); });
    const themes = Object.entries(themeMap).map(([k,v]) => ({ k, count: v.count, avg: v.probs.length ? Math.round(v.probs.reduce((a,b)=>a+b,0)/v.probs.length) : 0 })).sort((a,b)=>b.count-a.count).slice(0,10);
    if (chartTheme) chartTheme.destroy();
    chartTheme = new Chart($('#chart-theme'), {
      type: 'bar',
      data: { labels: themes.map(t=>eventLabel(t.k)), datasets: [{ label: 'Entities', data: themes.map(t=>t.count), backgroundColor: accent, borderRadius: 5, maxBarThickness: 26 }] },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: c => { const t = themes[c.dataIndex]; return `Avg correlation: ${t.avg}%`; } } } }, scales: { x: { beginAtZero: true, grid: { color: grid }, ticks }, y: { grid: { display: false }, ticks: { ...ticks, font: { family: 'Inter', size: 11 }, autoSkip: false } } } }
    });
  }

  // ---- Tabs ----
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      $('#tab-' + tab.dataset.tab).classList.add('active');
      const showControls = ['colored','graded'].includes(tab.dataset.tab);
      $('#controls').style.display = showControls ? '' : 'none';
    });
  });

  // ---- Render + filter wiring ----
  function refresh() {
    const rows = filtered();
    $('#result-count').textContent = `${rows.length} of ${companies.length} entities`;
    renderColored(rows);
    renderGraded(rows);
  }
  ['#search','#filter-grade','#filter-sector','#filter-event'].forEach(sel => {
    document.querySelector(sel).addEventListener('input', refresh);
  });

  // ---- Export ----
  function download(filename, content, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url); toast('Exported ' + filename);
  }
  $('#export-csv').addEventListener('click', () => {
    const rows = filtered();
    const cols = ['company','grade','total_score','primary_event','thematic_probability','sector','category','funding_stage','ipo_date','source','historical_flag'];
    const head = cols.join(',');
    const body = rows.map(r => cols.map(c => `"${String(r[c]??'').replace(/"/g,'""')}"`).join(',')).join('\n');
    download('pipeline.csv', head+'\n'+body, 'text/csv');
  });
  $('#export-json').addEventListener('click', () => {
    download('pipeline.json', JSON.stringify(filtered(), null, 2), 'application/json');
  });

  // ---- Event legend ----
  function renderEventLegend() {
    const wrap = $('#event-legend'); if (!wrap) return;
    const used = [...new Set(companies.map(c => c.primary_event).filter(v => v && v !== 'N/A'))];
    const codes = used.filter(c => EVENT_MAP[c]).sort((a,b)=>parseInt(a.slice(1))-parseInt(b.slice(1)));
    wrap.innerHTML = codes.map(c => `<span class="leg-item"><span class="leg-code">${esc(c)}</span><span class="leg-desc">${esc(EVENT_MAP[c])}</span></span>`).join('');
  }

  // ---- Disclaimer dismiss ----
  const dclose = $('#disclaimer-close');
  if (dclose) dclose.addEventListener('click', () => { const b = $('#disclaimer-banner'); if (b) b.style.display = 'none'; });

  // ---- Init ----
  renderMethodology();
  renderLineage();
  renderEventLegend();
  rebuildCharts();
  refresh();
})();

import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./terminal.css";

const API_URL = import.meta.env.VITE_API_BASE_URL || "";
const AUCTIONS = [["epex_60", "EPEX SPOT GB | 60 MIN | 09:20 UTC"], ["n2ex_60", "N2EX | 60 MIN | 09:50 UTC"], ["epex_30", "EPEX SPOT GB | 30 MIN | 15:30 UTC"]];
const number = (value, digits = 0) => value == null ? "--" : Number(value).toLocaleString("en-GB", { maximumFractionDigits: digits });
const mwh = (value) => value == null ? "--" : `${number(value, 1)} MWh`;
const mw = (value) => value == null ? "--" : `${number(value)} MW`;
const isoDate = (date) => date.toISOString().slice(0, 10);
const tomorrow = () => isoDate(new Date(Date.now() + 86400000));
const dateText = (value) => new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)).toUpperCase();
const stamp = (value) => new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }).format(new Date(value)).toUpperCase();
const clock = (value) => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }).format(new Date(value));

function Pane({ title, children, className = "" }) {
  return <section className={`pane ${className}`}><header className="pane-title">[ {title} ]</header>{children}</section>;
}

function DateSelector({ label, start, end, onChange, single = false, allowAll = false, availableDays }) {
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => new Date(`${start === "all" ? "2026-01-01" : start}T00:00:00Z`));
  const monthStart = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth(), 1));
  const daysInMonth = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + 1, 0)).getUTCDate();
  const offset = (monthStart.getUTCDay() + 6) % 7;
  const display = single ? (start === "all" ? "ALL SELECTED DATES" : dateText(start)) : `${dateText(start)} > ${dateText(end)}`;
  const usable = (day) => !availableDays || availableDays.includes(day);
  const choose = (day) => {
    if (single) { onChange(day); setOpen(false); return; }
    if (!start || (end && start !== end)) onChange(day, day);
    else if (day < start) { onChange(day, start); setOpen(false); }
    else { onChange(start, day); setOpen(false); }
  };
  const selected = (day) => single ? day === start : day >= start && day <= end;
  return <div className="date-select">
    <span>{label}</span>
    <button type="button" className="command-input" onClick={() => setOpen(!open)} aria-expanded={open}><b>▮</b>{display}<i>⌄</i></button>
    {open && <div className="terminal-calendar" role="dialog" aria-label={`${label} calendar`}>
      <div className="calendar-top"><button type="button" onClick={() => setMonth(new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() - 1, 1)))}>‹</button><b>{month.toLocaleString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" }).toUpperCase()}</b><button type="button" onClick={() => setMonth(new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + 1, 1)))}>›</button><button type="button" onClick={() => setOpen(false)}>×</button></div>
      {allowAll && <button type="button" className="all-dates" onClick={() => { onChange("all"); setOpen(false); }}>[ ALL SELECTED DATES ]</button>}
      <div className="calendar-days">{["MO", "TU", "WE", "TH", "FR", "SA", "SU"].map((day) => <span key={day}>{day}</span>)}</div>
      <div className="calendar-grid">{Array.from({ length: offset }, (_, i) => <i key={`blank-${i}`} />)}{Array.from({ length: daysInMonth }, (_, index) => {
        const day = `${month.getUTCFullYear()}-${String(month.getUTCMonth() + 1).padStart(2, "0")}-${String(index + 1).padStart(2, "0")}`;
        return <button type="button" key={day} className={`${selected(day) ? "selected" : ""} ${!single && (day === start || day === end) ? "edge" : ""}`} onClick={() => choose(day)} disabled={!usable(day)}>{String(index + 1).padStart(2, "0")}</button>;
      })}</div>
      {!single && <footer>{dateText(start)} {">"} {dateText(end)}</footer>}
    </div>}
  </div>;
}

function Metric({ label, value, note, direction }) {
  return <div className="metric"><span>{label}</span><strong className={direction || ""}>{value}</strong><small>{note}</small></div>;
}

function Profile({ rows, onSelect }) {
  const [hover, setHover] = useState(null);
  const values = rows.flatMap((row) => [row.actual_mw, row.forecast_mw]).filter((value) => value != null);
  const top = Math.max(1000, ...values) * 1.08;
  const w = 900, h = 222, p = { l: 54, r: 10, t: 12, b: 27 };
  const x = (index) => p.l + (index / Math.max(rows.length - 1, 1)) * (w - p.l - p.r);
  const y = (value) => p.t + (h - p.t - p.b) * (1 - value / top);
  const path = (field) => rows.map((row, index) => row[field] == null ? "" : `${index ? "L" : "M"}${x(index)},${y(row[field])}`).join(" ");
  const selectFromPointer = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const viewX = ((event.clientX - bounds.left) / bounds.width) * w;
    const ratio = Math.max(0, Math.min(1, (viewX - p.l) / (w - p.l - p.r)));
    setHover(Math.round(ratio * Math.max(rows.length - 1, 0)));
  };
  return <div className="chart"><svg viewBox={`0 0 ${w} ${h}`} aria-label="Actual and forecast wind generation" onMouseMove={selectFromPointer} onMouseLeave={() => setHover(null)} onClick={() => hover != null && onSelect(rows[hover])}><line x1={p.l} y1={h - p.b} x2={w - p.r} y2={h - p.b} /><path className="actual" d={path("actual_mw")} /><path className="forecast" d={path("forecast_mw")} />{hover != null && <><line className="crosshair" x1={x(hover)} y1={p.t} x2={x(hover)} y2={h - p.b} />{rows[hover].actual_mw != null && <circle className="actual-point" cx={x(hover)} cy={y(rows[hover].actual_mw)} r="3" />}{rows[hover].forecast_mw != null && <circle className="forecast-point" cx={x(hover)} cy={y(rows[hover].forecast_mw)} r="3" />}</>}</svg><div className="chart-key">ACTUAL <b /> FORECAST | MOVE ACROSS CHART FOR PRODUCT READOUT</div>{hover != null && <div className="chart-readout">{clock(rows[hover].start_time)} UTC<br />ACTUAL {mw(rows[hover].actual_mw)}<br />FORECAST {mw(rows[hover].forecast_mw)}<br />ERROR {mwh(rows[hover].signed_error_mwh)}</div>}</div>;
}

function ProductCompleteness({ data, quality, setQuality, qualityDate, setQualityDate, visibleRows, qualityRows, pageSize, qualityPage, setQualityPage, pageCount }) {
  const sourceBlock = (row) => {
    if (row.forecast_mw == null) return "--";
    const sourceStart = clock(row.forecast_source_start_time);
    const sourceEnd = clock(new Date(new Date(row.forecast_source_start_time).getTime() + 3600000).toISOString());
    const isSecondHalf = row.product_minutes === 30 && new Date(row.start_time).getUTCMinutes() === 30;
    return isSecondHalf ? `SAME ${sourceStart}-${sourceEnd} BLOCK ↑` : `${sourceStart}-${sourceEnd} | ${mw(row.forecast_mw)}`;
  };
  return <Pane title="AUCTION PRODUCT COMPLETENESS">
    <div className="quality-toolbar"><div className="status-filters">{["all", "matched", "source_allocated", "forecast_only", "actual_only", "missing"].map((filter) => <button key={filter} className={quality === filter ? "active" : ""} onClick={() => setQuality(filter)}>[ {filter.replace("_", " ").toUpperCase()} ]</button>)}</div><DateSelector label="PRODUCT DATE" start={qualityDate} onChange={setQualityDate} single allowAll availableDays={data.daily.map((day) => day.date)} /></div>
    {data.auction.product_minutes === 30 && <div className="coverage-line">EACH TWO 30-MINUTE PRODUCTS SHARE ONE PUBLISHED HOURLY FORECAST RATE. PRODUCT FORECAST MWh IS THE RATE × 0.5 HOURS.</div>}
    <div className="coverage-line">DIRECT MATCHED {data.coverage.matched} | HOURLY SOURCE ALLOCATED {data.coverage.source_allocated} | FORECAST ONLY {data.coverage.forecast_only} | ACTUAL ONLY {data.coverage.actual_only} | MISSING {data.coverage.missing}</div>
    <div className="table-wrap"><table><thead><tr><th>PRODUCT START</th><th>STATUS</th><th>ACTUAL MWh</th><th>ACTUAL AVAILABLE</th><th>PRODUCT FORECAST MWh</th><th>HOURLY FORECAST SOURCE</th><th>FORECAST PUBLISHED</th><th>ERROR MWh</th></tr></thead><tbody>{visibleRows.map((row) => <tr key={row.start_time}><td>{stamp(row.start_time)} UTC</td><td><span className={`status ${row.status}`}>{row.status.replace("_", " ").toUpperCase()}</span></td><td>{mwh(row.actual_mwh)}</td><td>{row.actual_available_time ? `${stamp(row.actual_available_time)} UTC` : "--"}</td><td>{mwh(row.forecast_mwh)}</td><td>{sourceBlock(row)}</td><td>{row.forecast_publish_time ? `${stamp(row.forecast_publish_time)} UTC` : "--"}</td><td>{mwh(row.signed_error_mwh)}</td></tr>)}</tbody></table></div>
    <footer className="pagination"><span>ROWS {qualityRows.length ? (qualityPage - 1) * pageSize + 1 : 0}-{Math.min(qualityPage * pageSize, qualityRows.length)} OF {qualityRows.length}</span><div><button onClick={() => setQualityPage((page) => Math.max(1, page - 1))} disabled={qualityPage === 1}>‹ PREV</button><b>PAGE {qualityPage}/{pageCount}</b><button onClick={() => setQualityPage((page) => Math.min(pageCount, page + 1))} disabled={qualityPage === pageCount}>NEXT ›</button></div></footer>
  </Pane>;
}

function AuctionForecastBoard({ rows, date, productMinutes, mode, onSelect }) {
  const [copied, setCopied] = useState(false);
  const copyForecastArray = async () => {
    const payload = rows.map((row) => ({ interval_start_utc: row.start_time, interval_end_utc: row.end_time, product_minutes: row.product_minutes, forecast_mw: row.forecast_mw, forecast_mwh: row.forecast_mwh, forecast_published_utc: row.forecast_publish_time, forecast_source_interval_utc: row.forecast_source_start_time, forecast_source_resolution_minutes: row.forecast_source_resolution_minutes }));
    const text = JSON.stringify(payload, null, 2);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const fallback = document.createElement("textarea");
      fallback.value = text;
      document.body.appendChild(fallback);
      fallback.select();
      document.execCommand("copy");
      fallback.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };
  return <Pane title={`${mode === "live" ? "TOMORROW'S" : "DELIVERY"} AUCTION PRODUCT FORECASTS | ${date} | ${productMinutes}-MIN`} className="forecast-board"><div className="forecast-board-note"><span>SOURCE-PUBLISHED FORECAST ENERGY PER PURCHASABLE AUCTION PRODUCT. SELECT A PRODUCT TO AUDIT ITS VINTAGES.</span><button type="button" onClick={copyForecastArray}>[ {copied ? "ARRAY COPIED" : "COPY FORECAST ARRAY"} ]</button></div><div className="forecast-board-grid">{rows.map((row) => <button type="button" key={row.start_time} disabled={row.forecast_mwh == null} onClick={() => onSelect(row)}><span>{clock(row.start_time)}-{clock(row.end_time)} UTC</span><b>{mwh(row.forecast_mwh)}</b><small>{row.forecast_source_resolution_minutes === 60 && productMinutes === 30 ? "HOURLY SOURCE RATE × 0.5H" : "SOURCE FORECAST"}</small></button>)}</div></Pane>;
}

function App() {
  const [startDate, setStartDate] = useState("2026-01-01");
  const [endDate, setEndDate] = useState("2026-01-31");
  const [mode, setMode] = useState("decision");
  const [auction, setAuction] = useState("epex_60");
  const [customCutoff, setCustomCutoff] = useState("");
  const [useCustomCutoff, setUseCustomCutoff] = useState(false);
  const [tab, setTab] = useState("overview");
  const [focusDate, setFocusDate] = useState("2026-01-01");
  const [quality, setQuality] = useState("all");
  const [qualityDate, setQualityDate] = useState("all");
  const [qualityPage, setQualityPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [vintages, setVintages] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const latestRequest = useRef(0);
  const lastBacktest = useRef({ startDate: "2026-01-01", endDate: "2026-01-31", focusDate: "2026-01-01" });
  const load = async () => {
    const requestId = ++latestRequest.current;
    setLoading(true); setError("");
    try {
      const query = new URLSearchParams({ start_date: startDate, end_date: endDate, mode, auction });
      if (useCustomCutoff && customCutoff && mode === "decision") query.set("cutoff_time", customCutoff);
      const response = await fetch(`${API_URL}/api/analysis?${query}`);
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "ANALYSIS SERVICE UNAVAILABLE");
      if (requestId !== latestRequest.current) return;
      setSelected(null);
      setVintages(null);
      setData(body);
      if (!body.daily.some((day) => day.date === focusDate)) setFocusDate(body.daily[0]?.date || startDate);
    } catch (requestError) { if (requestId === latestRequest.current) { setData(null); setError(requestError.message); } } finally { if (requestId === latestRequest.current) setLoading(false); }
  };
  useEffect(() => {
    const debounce = window.setTimeout(load, 250);
    return () => window.clearTimeout(debounce);
  }, [startDate, endDate, mode, auction, useCustomCutoff, customCutoff]);
  useEffect(() => {
    if (!selected) return;
    setVintages(null);
    const query = new URLSearchParams({ start_time: selected.start_time, mode: data?.selection.mode || "decision" });
    if (data?.selection.cutoff_time_utc) query.set("cutoff_time", data.selection.cutoff_time_utc);
    fetch(`${API_URL}/api/vintages?${query}`).then((response) => response.json()).then(setVintages).catch(() => setVintages({ vintages: [] }));
  }, [selected, data]);
  const focusRows = useMemo(() => data?.products.filter((row) => row.start_time.startsWith(focusDate)) || [], [data, focusDate]);
  const qualityRows = useMemo(() => data?.products.filter((row) => (quality === "all" || row.status === quality) && (qualityDate === "all" || row.start_time.startsWith(qualityDate))) || [], [data, quality, qualityDate]);
  const pageSize = 25, pageCount = Math.max(1, Math.ceil(qualityRows.length / pageSize));
  const visibleRows = qualityRows.slice((qualityPage - 1) * pageSize, qualityPage * pageSize);
  useEffect(() => setQualityPage(1), [quality, qualityDate, data]);
  const download = () => {
    const csv = ["interval_start_utc,interval_end_utc,status,product_minutes,actual_mw,actual_mwh,actual_available_utc,forecast_mw,forecast_mwh,forecast_published_utc,forecast_source_resolution_minutes,signed_error_mwh", ...(data?.products || []).map((row) => [row.start_time, row.end_time, row.status, row.product_minutes, row.actual_mw ?? "", row.actual_mwh ?? "", row.actual_available_time ?? "", row.forecast_mw ?? "", row.forecast_mwh ?? "", row.forecast_publish_time ?? "", row.forecast_source_resolution_minutes ?? "", row.signed_error_mwh ?? ""].join(","))].join("\n");
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); link.download = `winddesk-${auction}-${startDate}-${endDate}.csv`; link.click(); URL.revokeObjectURL(link.href);
  };
  const changeMode = (next) => {
    if (next === "live") {
      lastBacktest.current = { startDate, endDate, focusDate };
      const deliveryDate = tomorrow();
      setStartDate(deliveryDate); setEndDate(deliveryDate); setFocusDate(deliveryDate);
    } else if (mode === "live") {
      setStartDate(lastBacktest.current.startDate);
      setEndDate(lastBacktest.current.endDate);
      setFocusDate(lastBacktest.current.focusDate);
    }
    setMode(next);
  };
  const status = data ? "SOURCE ONLINE" : loading ? "QUERYING SOURCE" : "SOURCE ERROR";
  const signed = data?.metrics.signed_error_mwh;
  return <div className="terminal-shell">
    <header className="topbar"><b>WINDDESK//UK</b><span>WIND FORECAST PROCUREMENT TERMINAL</span><span className={data ? "online" : "offline"}>● {status}</span><button type="button" onClick={download} disabled={!data}>[ EXPORT CSV ]</button></header>
    <nav className="tabs">{[["overview", "F1 OVERVIEW"], ["vintages", "F2 VINTAGES"], ["quality", "F3 PRODUCTS"], ["method", "F4 METHOD"]].map(([id, label]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>)}</nav>
    <main>
      <Pane title="QUERY CONTROL" className="query-pane">
        <DateSelector label="DELIVERY WINDOW" start={startDate} end={endDate} onChange={(start, end) => { setStartDate(start); setEndDate(end); }} />
        <label className="field">VIEW MODE<select value={mode} onChange={(event) => changeMode(event.target.value)}><option value="decision">JAN BACKTEST: DECISION TIME</option><option value="latest">BACKTEST: HINDSIGHT LATEST</option><option value="live">LIVE: LATEST API FORECAST</option></select></label>
        <label className="field">PURCHASE AUCTION<select value={auction} onChange={(event) => setAuction(event.target.value)}>{AUCTIONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        {mode === "decision" && <div className="field cutoff-override"><span>DECISION CUTOFF UTC</span><label className="cutoff-toggle"><input type="checkbox" checked={useCustomCutoff} onChange={(event) => setUseCustomCutoff(event.target.checked)} /> CUSTOM OVERRIDE</label>{useCustomCutoff ? <input type="time" value={customCutoff} onChange={(event) => setCustomCutoff(event.target.value)} aria-label="Custom cutoff UTC" /> : <output>{AUCTIONS.find(([id]) => id === auction)?.[1].split("|").at(-1).trim()} AUCTION DEFAULT</output>}</div>}
        <button className="execute" onClick={load} disabled={loading}>{loading ? "UPDATING..." : "↻ REFRESH NOW"}</button>
      </Pane>
      {error && <div className="system-message error">[ ERROR ] {error} <button onClick={load}>RETRY</button></div>}
      {loading && !data && <div className="system-message">[ SYSTEM ] LOADING ELEXON WIND DATA...</div>}
      {data && <Dashboard data={data} mode={mode} focusDate={focusDate} setFocusDate={setFocusDate} tab={tab} setTab={setTab} focusRows={focusRows} selected={selected} setSelected={setSelected} vintages={vintages} quality={quality} setQuality={setQuality} qualityDate={qualityDate} setQualityDate={setQualityDate} visibleRows={visibleRows} qualityRows={qualityRows} pageSize={pageSize} qualityPage={qualityPage} setQualityPage={setQualityPage} pageCount={pageCount} signed={signed} />}
    </main>
    <footer className="statusbar">F1 OVERVIEW | F2 VINTAGES | F3 PRODUCTS | F4 METHOD <span>WINDDESK 2.0 // JAN 2026 BACKTEST DEFAULT + LIVE SOURCE VIEW</span></footer>
  </div>;
}

function Dashboard(props) {
  const { data, mode, focusDate, setFocusDate, tab, setTab, focusRows, selected, setSelected, vintages, quality, setQuality, qualityDate, setQualityDate, visibleRows, qualityRows, pageSize, qualityPage, setQualityPage, pageCount, signed } = props;
  const coverageNote = data.auction.product_minutes === 30 ? `${data.coverage.source_allocated}/${data.coverage.expected_products} HOURLY-ALLOCATED` : `${data.coverage.matched}/${data.coverage.expected_products} DIRECTLY MATCHED`;
  return <>
    <div className="ticker">[ AUCTION ] {data.auction.label} | PRODUCTS {data.auction.product_minutes} MIN | {data.selection.label.toUpperCase()} {data.selection.cutoff_time_utc ? `| CUTOFF ${data.selection.cutoff_time_utc} UTC` : ""} | FOCUS DELIVERY {focusDate} | WINDOW {data.window.start_date} &gt; {data.window.end_date}</div>
    <section className="metrics-grid"><Metric label="WINDOW FORECAST WIND" value={mwh(data.metrics.forecast_energy_mwh)} note={mode === "live" ? "SOURCE-PUBLISHED, NO ACTUALS" : "ANALYTICAL AUCTION PRODUCTS"} /><Metric label="ACTUAL WIND ENERGY" value={mwh(data.metrics.actual_energy_mwh)} note={mode === "live" ? "NOT AVAILABLE IN LIVE VIEW" : "ANALYTICAL AUCTION PRODUCTS"} /><Metric label="SIGNED ENERGY ERROR" value={mwh(signed)} note={signed == null ? "REQUIRES ACTUAL OUTTURN" : signed >= 0 ? "FORECAST ABOVE ACTUAL" : "FORECAST BELOW ACTUAL"} direction={signed == null ? "" : signed >= 0 ? "negative" : "positive"} /><Metric label="TOTAL ABS ERROR" value={mwh(data.metrics.absolute_error_mwh)} note={coverageNote} /><Metric label="OBSERVED ERROR RATE" value={data.metrics.wape_percent == null ? "--" : `${number(data.metrics.wape_percent, 1)}%`} note={mode === "live" ? "REQUIRES ACTUAL OUTTURN" : "HISTORICAL WAPE, NOT A BUFFER"} /></section>
    {data.auction.product_minutes === 30 && <div className="system-message">[ SOURCE RESOLUTION ] WINDFOR IS PUBLISHED HOURLY. EACH 30-MINUTE PRODUCT DISPLAYS THE SAME PUBLISHED HOURLY MW RATE FOR ITS SOURCE HOUR. NO INTERPOLATION OR NEW FORECAST HAS BEEN CREATED.</div>}
    {tab === "overview" && <><AuctionForecastBoard rows={focusRows} date={focusDate} productMinutes={data.auction.product_minutes} mode={mode} onSelect={(row) => { setSelected(row); setTab("vintages"); }} /><section className="terminal-grid overview-grid"><Pane title="DAILY ENERGY ERROR"><div className="day-list">{data.daily.map((day) => <button key={day.date} className={focusDate === day.date ? "selected" : ""} onClick={() => setFocusDate(day.date)}><span>{day.date}</span><i style={{ width: `${Math.min(100, ((day.absolute_error_mwh || 0) / Math.max(...data.daily.map((row) => row.absolute_error_mwh || 1))) * 100)}%` }} /><b>{mwh(day.absolute_error_mwh)} | {day.wape_percent == null ? "--" : `${number(day.wape_percent, 1)}%`}</b></button>)}</div></Pane><Pane title={`AUCTION PRODUCT PROFILE | ${focusDate}`}><Profile rows={focusRows} onSelect={(row) => { setSelected(row); setTab("vintages"); }} /></Pane><Pane title="DECISION READOUT"><div className="readout">{mode === "live" ? <><b className="amber">SOURCE FORECAST VIEW</b><p>This screen shows the latest forecast values published by Elexon for the selected delivery window.</p><p>The dashboard does not suggest a bid volume, add a buffer, or make a trading decision.</p><p>Actual wind output and observed energy error will only exist after delivery.</p></> : <><b className={signed >= 0 ? "negative" : "positive"}>{signed >= 0 ? "FORECAST ABOVE ACTUAL" : "FORECAST BELOW ACTUAL"}</b><p>Across matched {data.auction.product_minutes}-minute products, published forecast wind totalled {mwh(data.metrics.forecast_energy_mwh)} and actual wind totalled {mwh(data.metrics.actual_energy_mwh)}.</p><p>The observed error rate was {data.metrics.wape_percent == null ? "--" : `${number(data.metrics.wape_percent, 1)}%`}: total absolute product error divided by total actual wind energy.</p><p>This describes the selected backtest. It is not a suggested purchase adjustment or buffer.</p><p className="amber">Open F2 to inspect the exact forecast publication history behind an auction product.</p></>}</div></Pane></section></>}
    {tab === "vintages" && <section className="terminal-grid vintage-grid"><Pane title="PRODUCT SELECTOR"><div className="vintage-date-control"><DateSelector label="DELIVERY DATE" start={focusDate} onChange={(value) => { setFocusDate(value); setSelected(null); }} single availableDays={data.daily.map((day) => day.date)} /></div><div className="period-list">{focusRows.filter((row) => row.forecast_mw != null).map((row) => <button key={row.start_time} className={selected?.start_time === row.start_time ? "selected" : ""} onClick={() => setSelected(row)}><span>{stamp(row.start_time)} UTC</span><b className={row.signed_error_mwh >= 0 ? "negative" : "positive"}>{row.signed_error_mwh == null ? "--" : `${row.signed_error_mwh > 0 ? "+" : ""}${mwh(row.signed_error_mwh)}`}</b></button>)}</div></Pane><Pane title="FORECAST VINTAGE AUDIT">{selected ? <div className="vintage-detail"><div className="selected-row"><span>PRODUCT {stamp(selected.start_time)} UTC</span><span>FORECAST {mwh(selected.forecast_mwh)}</span><span>ACTUAL {mwh(selected.actual_mwh)}</span></div><p>Source interval: {selected.forecast_source_start_time ? `${stamp(selected.forecast_source_start_time)} UTC` : "--"}. Source resolution: {selected.forecast_source_resolution_minutes || "--"} minutes.</p>{vintages == null ? <p>LOADING FORECAST RUNS...</p> : vintages.vintages.length ? <table><thead><tr><th>FORECAST PUBLISHED AT</th><th>WIND FORECAST</th><th>DECISION STATUS</th><th>ACTUAL ENERGY</th><th>ACTUAL AVAILABLE</th></tr></thead><tbody>{vintages.vintages.map((row) => <tr key={row.publish_time} className={row.selected ? "selected-vintage" : ""}><td>{stamp(row.publish_time)} UTC</td><td>{mw(row.generation_mw)}</td><td><span className={`status ${row.eligibility}`}>{row.selected ? "SELECTED" : row.eligibility.replaceAll("_", " ").toUpperCase()}</span></td><td>{mwh(selected.actual_mwh)}</td><td>{selected.actual_available_time ? `${stamp(selected.actual_available_time)} UTC` : "--"}</td></tr>)}</tbody></table> : <p>NO VINTAGES RETURNED.</p>}</div> : <p className="readout">SELECT A PRODUCT FROM THE LEFT PANE.</p>}</Pane></section>}
    {tab === "quality" && <ProductCompleteness data={data} quality={quality} setQuality={setQuality} qualityDate={qualityDate} setQualityDate={setQualityDate} visibleRows={visibleRows} qualityRows={qualityRows} pageSize={pageSize} qualityPage={qualityPage} setQualityPage={setQualityPage} pageCount={pageCount} />}
    {tab === "method" && <section className="terminal-grid method-grid"><Pane title="AUCTION GRID"><p>The chosen auction controls product duration and default decision cutoff.</p><p>EPEX 60 and N2EX display 60-minute products.</p><p>EPEX 30 displays 48 half-hour products.</p></Pane><Pane title="SOURCE RESOLUTION"><p>WINDFOR is an hourly source forecast.</p><p>For 30-minute products, its published hourly MW rate is displayed against both half-hours.</p><p>The dashboard does not interpolate or create a new forecast.</p></Pane><Pane title="ENERGY ACCOUNTING"><p>MW is a rate.</p><p>MWh is the rate multiplied by product duration.</p><p>Backtests compare forecast and actual MWh per auction product.</p></Pane><Pane title="SCOPE"><p>FUELHH supplies actual WIND output.</p><p>WINDFOR supplies forecast vintages.</p><p>All timestamps are UTC. The dashboard reports source data and observed history only.</p></Pane></section>}
  </>;
}

createRoot(document.getElementById("root")).render(<App />);

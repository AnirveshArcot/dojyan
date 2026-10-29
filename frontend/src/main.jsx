import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./terminal.css";

const API_URL = import.meta.env.VITE_API_BASE_URL || "";
const DAYS = Array.from(
  { length: 31 },
  (_, index) => `2026-01-${String(index + 1).padStart(2, "0")}`,
);
const CUTOFFS = [
  ["06:00", "CHAPS OPEN"],
  ["08:00", "LSE CASH OPEN"],
  ["09:20", "GB DAY-AHEAD AUCTION"],
  ["16:30", "LSE CASH CLOSE"],
  ["17:40", "CHAPS CUSTOMER DEADLINE"],
];
const number = (value, digits = 0) =>
  value == null
    ? "--"
    : Number(value).toLocaleString("en-GB", { maximumFractionDigits: digits });
const mw = (value) => (value == null ? "--" : `${number(value)} MW`);
const dateText = (value) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  })
    .format(new Date(`${value}T00:00:00Z`))
    .toUpperCase();
const stamp = (value) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  })
    .format(new Date(value))
    .toUpperCase();
const clock = (value) =>
  new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(value));

function Pane({ title, children, className = "" }) {
  return (
    <section className={`pane ${className}`}>
      <header className="pane-title">[ {title} ]</header>
      {children}
    </section>
  );
}

function DateSelector({
  label,
  start,
  end,
  onChange,
  single = false,
  allowAll = false,
  availableDays = DAYS,
}) {
  const [open, setOpen] = useState(false);
  const display = single
    ? start === "all"
      ? "ALL SELECTED DATES"
      : dateText(start)
    : `${dateText(start)} > ${dateText(end)}`;
  const choose = (day) => {
    if (single) {
      onChange(day);
      setOpen(false);
      return;
    }
    if (!start || (end && start !== end)) onChange(day, day);
    else if (day < start) {
      onChange(day, start);
      setOpen(false);
    } else {
      onChange(start, day);
      setOpen(false);
    }
  };
  const selected = (day) =>
    single ? day === start : day >= start && day <= end;
  const edge = (day) => !single && (day === start || day === end);
  return (
    <div className="date-select">
      <span>{label}</span>
      <button
        type="button"
        className="command-input"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <b>▮</b>
        {display}
        <i>⌄</i>
      </button>
      {open && (
        <div
          className="terminal-calendar"
          role="dialog"
          aria-label={`${label} calendar`}
        >
          <div className="calendar-top">
            <b>JAN 2026</b>
            <button type="button" onClick={() => setOpen(false)}>
              ×
            </button>
          </div>
          {allowAll && (
            <button
              type="button"
              className="all-dates"
              onClick={() => {
                onChange("all");
                setOpen(false);
              }}
            >
              [ ALL SELECTED DATES ]
            </button>
          )}
          <div className="calendar-days">
            {["MO", "TU", "WE", "TH", "FR", "SA", "SU"].map((day) => (
              <span key={day}>{day}</span>
            ))}
          </div>
          <div className="calendar-grid">
            {Array.from({ length: 3 }, (_, index) => (
              <i key={index} />
            ))}
            {DAYS.map((day) => (
              <button
                type="button"
                key={day}
                className={`${selected(day) ? "selected" : ""} ${edge(day) ? "edge" : ""}`}
                onClick={() => choose(day)}
                disabled={!availableDays.includes(day)}
              >
                {day.slice(-2)}
              </button>
            ))}
          </div>
          {!single && (
            <footer>
              {dateText(start)}
              {" > "}
              {dateText(end)}
            </footer>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, note, direction }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={direction || ""}>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function Profile({ rows, onSelect }) {
  const [hover, setHover] = useState(null);
  const values = rows
    .flatMap((row) => [row.actual_mw, row.forecast_mw])
    .filter((value) => value != null);
  const top = Math.max(1000, ...values) * 1.08;
  const w = 900,
    h = 222,
    p = { l: 54, r: 10, t: 12, b: 27 };
  const x = (index) =>
    p.l + (index / Math.max(rows.length - 1, 1)) * (w - p.l - p.r);
  const y = (value) => p.t + (h - p.t - p.b) * (1 - value / top);
  const path = (field) =>
    rows
      .map((row, index) =>
        row[field] == null
          ? ""
          : `${index ? "L" : "M"}${x(index)},${y(row[field])}`,
      )
      .join(" ");
  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        aria-label="Actual and forecast wind generation"
      >
        <line x1={p.l} y1={h - p.b} x2={w - p.r} y2={h - p.b} />
        <path className="actual" d={path("actual_mw")} />
        <path className="forecast" d={path("forecast_mw")} />
        {rows.map((row, index) => (
          <rect
            key={row.start_time}
            x={x(index) - 8}
            y={p.t}
            width="16"
            height={h - p.t - p.b}
            onMouseEnter={() => setHover(index)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onSelect(row)}
          />
        ))}
      </svg>
      <div className="chart-key">
        ACTUAL <b /> FORECAST
      </div>
      {hover != null && (
        <div className="chart-readout">
          {clock(rows[hover].start_time)} UTC
          <br />A {mw(rows[hover].actual_mw)}
          <br />F {mw(rows[hover].forecast_mw)}
          <br />Δ{" "}
          {rows[hover].error_mw == null
            ? "--"
            : `${rows[hover].error_mw > 0 ? "+" : ""}${mw(rows[hover].error_mw)}`}
        </div>
      )}
    </div>
  );
}

function App() {
  const [startDate, setStartDate] = useState("2026-01-01");
  const [endDate, setEndDate] = useState("2026-01-31");
  const [mode, setMode] = useState("decision");
  const [cutoff, setCutoff] = useState("09:20");
  const [customCutoff, setCustomCutoff] = useState("12:00");
  const [tab, setTab] = useState("overview");
  const [focusDate, setFocusDate] = useState("2026-01-20");
  const [quality, setQuality] = useState("all");
  const [qualityDate, setQualityDate] = useState("all");
  const [qualityPage, setQualityPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [vintages, setVintages] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        mode,
        cutoff_time: cutoff === "custom" ? customCutoff : cutoff,
      });
      const response = await fetch(`${API_URL}/api/analysis?${query}`);
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.detail || "ANALYSIS SERVICE UNAVAILABLE");
      setData(body);
      if (!body.daily.some((day) => day.date === focusDate))
        setFocusDate(body.daily[0]?.date || startDate);
    } catch (requestError) {
      setData(null);
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, []);
  useEffect(() => {
    if (!selected) return;
    setVintages(null);
    fetch(
      `${API_URL}/api/vintages?start_time=${encodeURIComponent(selected.start_time)}`,
    )
      .then((response) => response.json())
      .then(setVintages)
      .catch(() => setVintages({ vintages: [] }));
  }, [selected]);
  const focusRows = useMemo(
    () =>
      data?.periods.filter((row) => row.start_time.startsWith(focusDate)) || [],
    [data, focusDate],
  );
  const qualityRows = useMemo(
    () =>
      data?.periods.filter(
        (row) =>
          (quality === "all" || row.status === quality) &&
          (qualityDate === "all" || row.start_time.startsWith(qualityDate)),
      ) || [],
    [data, quality, qualityDate],
  );
  const pageSize = 25;
  const pageCount = Math.max(1, Math.ceil(qualityRows.length / pageSize));
  const visibleRows = qualityRows.slice(
    (qualityPage - 1) * pageSize,
    qualityPage * pageSize,
  );
  useEffect(() => setQualityPage(1), [quality, qualityDate, data]);
  const download = () => {
    const rows = data?.periods || [];
    const csv = [
      "interval_start_utc,actual_mw,actual_publish_time_utc,forecast_mw,error_mw,forecast_publish_time_utc,status",
      ...rows.map((row) =>
        [
          row.start_time,
          row.actual_mw ?? "",
          row.actual_publish_time ?? "",
          row.forecast_mw ?? "",
          row.error_mw ?? "",
          row.publish_time ?? "",
          row.status,
        ].join(","),
      ),
    ].join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    link.download = `winddesk-${startDate}-${endDate}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };
  const selectPeriod = (row) => {
    setSelected(row);
    setTab("vintages");
  };
  const status = data
    ? "SOURCE ONLINE"
    : loading
      ? "QUERYING SOURCE"
      : "SOURCE ERROR";
  return (
    <div className="terminal-shell">
      <header className="topbar">
        <b>WINDDESK//UK</b>
        <span>WIND FORECAST PROCUREMENT TERMINAL</span>
        <span className={data ? "online" : "offline"}>● {status}</span>
        <button type="button" onClick={download} disabled={!data}>
          [ EXPORT CSV ]
        </button>
      </header>
      <nav className="tabs">
        <button
          className={tab === "overview" ? "active" : ""}
          onClick={() => setTab("overview")}
        >
          F1 OVERVIEW
        </button>
        <button
          className={tab === "vintages" ? "active" : ""}
          onClick={() => setTab("vintages")}
        >
          F2 VINTAGES
        </button>
        <button
          className={tab === "quality" ? "active" : ""}
          onClick={() => setTab("quality")}
        >
          F3 QUALITY
        </button>
        <button
          className={tab === "method" ? "active" : ""}
          onClick={() => setTab("method")}
        >
          F4 METHOD
        </button>
      </nav>
      <main>
        <Pane title="QUERY CONTROL" className="query-pane">
          <DateSelector
            label="DELIVERY WINDOW"
            start={startDate}
            end={endDate}
            onChange={(start, end) => {
              setStartDate(start);
              setEndDate(end);
            }}
          />
          <label className="field">
            FORECAST BASIS
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value)}
            >
              <option value="decision">DECISION-TIME</option>
              <option value="latest">HINDSIGHT LATEST</option>
            </select>
          </label>
          {mode === "decision" && (
            <label className="field">
              DECISION MOMENT UTC
              <select
                value={cutoff}
                onChange={(event) => setCutoff(event.target.value)}
              >
                {CUTOFFS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {value} | {label}
                  </option>
                ))}
                <option value="custom">CUSTOM TIME</option>
              </select>
              {cutoff === "custom" && (
                <input
                  type="time"
                  value={customCutoff}
                  onChange={(event) => setCustomCutoff(event.target.value)}
                />
              )}
            </label>
          )}
          <button className="execute" onClick={load} disabled={loading}>
            {loading ? "EXECUTING..." : "▶ RUN ANALYSIS"}
          </button>
        </Pane>
        {error && (
          <div className="system-message error">
            [ ERROR ] {error} <button onClick={load}>RETRY</button>
          </div>
        )}
        {loading && !data && (
          <div className="system-message">
            [ SYSTEM ] LOADING ELEXON WIND DATA...
          </div>
        )}
        {data && (
          <>
            <div className="ticker">
              [ POLICY ] {data.selection.label.toUpperCase()} | CUTOFF{" "}
              {data.selection.cutoff_time_utc || "N/A"} UTC | WINDOW{" "}
              {data.window.start_date} &gt; {data.window.end_date} | RETRIEVED{" "}
              {stamp(data.retrieved_at)} UTC
            </div>
            <section className="metrics-grid">
              <Metric
                label="MEAN ABS ERROR"
                value={mw(data.metrics.mae_mw)}
                note="TYPICAL MATCHED INTERVAL"
              />
              <Metric
                label="RMSE"
                value={mw(data.metrics.rmse_mw)}
                note="LARGE MISSES WEIGHTED"
              />
              <Metric
                label="BIAS"
                value={`${data.metrics.bias_mw > 0 ? "+" : ""}${mw(data.metrics.bias_mw)}`}
                note={
                  data.metrics.bias_mw >= 0
                    ? "OVER-CALLED WIND"
                    : "UNDER-CALLED WIND"
                }
                direction={data.metrics.bias_mw >= 0 ? "negative" : "positive"}
              />
              <Metric
                label="WAPE"
                value={
                  data.metrics.wape_percent == null
                    ? "--"
                    : `${number(data.metrics.wape_percent, 1)}%`
                }
                note={`${data.coverage.matched}/${data.coverage.expected_periods} MATCHED`}
              />
            </section>
            {tab === "overview" && (
              <section className="terminal-grid overview-grid">
                <Pane title="DAILY ERROR MAP">
                  <div className="day-list">
                    {data.daily.map((day) => (
                      <button
                        key={day.date}
                        className={focusDate === day.date ? "selected" : ""}
                        onClick={() => setFocusDate(day.date)}
                      >
                        <span>{day.date}</span>
                        <i
                          style={{
                            width: `${Math.min(100, ((day.mae_mw || 0) / Math.max(...data.daily.map((row) => row.mae_mw || 1))) * 100)}%`,
                          }}
                        />
                        <b>{mw(day.mae_mw)}</b>
                      </button>
                    ))}
                  </div>
                </Pane>
                <Pane title={`DELIVERY PROFILE | ${focusDate}`}>
                  <Profile rows={focusRows} onSelect={selectPeriod} />
                </Pane>
                <Pane title="DECISION READOUT">
                  <div className="readout">
                    <b
                      className={
                        data.metrics.bias_mw >= 0 ? "negative" : "positive"
                      }
                    >
                      {data.metrics.bias_mw >= 0
                        ? "OVER-CALLED"
                        : "UNDER-CALLED"}
                    </b>
                    <p>
                      Forecast bias is {number(Math.abs(data.metrics.bias_mw))}{" "}
                      MW across matched intervals.
                    </p>
                    <p>
                      <strong>{data.coverage.actual_only}</strong> actual-only
                      intervals remain visible and are excluded from accuracy
                      metrics.
                    </p>
                    <p className="amber">
                      NEXT: Inspect an interval in F2 to audit available
                      forecast vintages.
                    </p>
                  </div>
                </Pane>
              </section>
            )}
            {tab === "vintages" && (
              <section className="terminal-grid vintage-grid">
                <Pane title="INTERVAL SELECTOR">
                  <div className="vintage-date-control">
                    <DateSelector
                      label="DELIVERY DATE"
                      start={focusDate}
                      onChange={(date) => {
                        setFocusDate(date);
                        setSelected(null);
                      }}
                      single
                      availableDays={data.daily.map((day) => day.date)}
                    />
                  </div>
                  <div className="period-list">
                    {focusRows
                      .filter((row) => row.status === "matched")
                      .map((row) => (
                        <button
                          key={row.start_time}
                          className={
                            selected?.start_time === row.start_time
                              ? "selected"
                              : ""
                          }
                          onClick={() => setSelected(row)}
                        >
                          <span>{stamp(row.start_time)} UTC</span>
                          <b
                            className={
                              row.error_mw > 0 ? "negative" : "positive"
                            }
                          >
                            {row.error_mw > 0 ? "+" : ""}
                            {mw(row.error_mw)}
                          </b>
                        </button>
                      ))}
                  </div>
                </Pane>
                <Pane title="FORECAST VINTAGE AUDIT">
                  {selected ? (
                    <div className="vintage-detail">
                      <div className="selected-row">
                        <span>INTERVAL {stamp(selected.start_time)} UTC</span>
                        <span>ACTUAL {mw(selected.actual_mw)}</span>
                        <span>SELECTED {mw(selected.forecast_mw)}</span>
                      </div>
                      {vintages == null ? (
                        <p>LOADING FORECAST RUNS...</p>
                      ) : vintages.vintages.length ? (
                        <table>
                          <thead>
                            <tr>
                              <th>FORECAST PUBLISHED AT</th>
                              <th>WIND FORECAST</th>
                            </tr>
                          </thead>
                          <tbody>
                            {vintages.vintages.map((row) => (
                              <tr key={row.publish_time}>
                                <td>{stamp(row.publish_time)} UTC</td>
                                <td>{mw(row.generation_mw)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <p>NO ADDITIONAL VINTAGES RETURNED.</p>
                      )}
                    </div>
                  ) : (
                    <p>
                      SELECT A MATCHED DELIVERY INTERVAL FROM THE LEFT PANE.
                    </p>
                  )}
                </Pane>
              </section>
            )}
            {tab === "quality" && (
              <Pane title="DATA COMPLETENESS">
                <div className="quality-toolbar">
                  <div className="status-filters">
                    {[
                      "all",
                      "matched",
                      "forecast_only",
                      "actual_only",
                      "missing",
                    ].map((filter) => (
                      <button
                        key={filter}
                        className={quality === filter ? "active" : ""}
                        onClick={() => setQuality(filter)}
                      >
                        [ {filter.replace("_", " ").toUpperCase()} ]
                      </button>
                    ))}
                  </div>
                  <DateSelector
                    label="INTERVAL DATE"
                    start={qualityDate}
                    onChange={setQualityDate}
                    single
                    allowAll
                  />
                </div>
                <div className="coverage-line">
                  MATCHED {data.coverage.matched} | FORECAST ONLY{" "}
                  {data.coverage.forecast_only} | ACTUAL ONLY{" "}
                  {data.coverage.actual_only} | MISSING {data.coverage.missing}
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>INTERVAL START</th>
                        <th>STATUS</th>
                        <th>ACTUAL MW</th>
                        <th>ACTUAL AVAILABLE</th>
                        <th>FORECAST MW</th>
                        <th>FORECAST PUBLISHED</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRows.map((row) => (
                        <tr key={row.start_time}>
                          <td>{stamp(row.start_time)} UTC</td>
                          <td>
                            <span className={`status ${row.status}`}>
                              {row.status.replace("_", " ").toUpperCase()}
                            </span>
                          </td>
                          <td>{mw(row.actual_mw)}</td>
                          <td>
                            {row.actual_publish_time
                              ? `${stamp(row.actual_publish_time)} UTC`
                              : "--"}
                          </td>
                          <td>{mw(row.forecast_mw)}</td>
                          <td>
                            {row.publish_time
                              ? `${stamp(row.publish_time)} UTC`
                              : "--"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <footer className="pagination">
                  <span>
                    ROWS{" "}
                    {qualityRows.length ? (qualityPage - 1) * pageSize + 1 : 0}-
                    {Math.min(qualityPage * pageSize, qualityRows.length)} OF{" "}
                    {qualityRows.length}
                  </span>
                  <div>
                    <button
                      onClick={() =>
                        setQualityPage((page) => Math.max(1, page - 1))
                      }
                      disabled={qualityPage === 1}
                    >
                      ‹ PREV
                    </button>
                    <b>
                      PAGE {qualityPage}/{pageCount}
                    </b>
                    <button
                      onClick={() =>
                        setQualityPage((page) => Math.min(pageCount, page + 1))
                      }
                      disabled={qualityPage === pageCount}
                    >
                      NEXT ›
                    </button>
                  </div>
                </footer>
              </Pane>
            )}
            {tab === "method" && (
              <section className="terminal-grid method-grid">
                <Pane title="SELECTION POLICY">
                  <p>
                    For each delivery interval, the system selects the newest
                    wind forecast published on or before the configured
                    day-before decision moment.
                  </p>
                  <p>
                    Hindsight mode selects the newest forecast published before
                    delivery and is for comparison only.
                  </p>
                </Pane>
                <Pane title="MATCHING">
                  <p>
                    Actual and forecast values join only on identical UTC
                    interval starts.
                  </p>
                  <p>
                    Unmatched records remain visible in F3 and never become zero
                    generation.
                  </p>
                </Pane>
                <Pane title="METRICS">
                  <p>MAE is the typical absolute miss.</p>
                  <p>RMSE weights larger misses more heavily.</p>
                  <p>Bias is forecast minus actual.</p>
                  <p>
                    WAPE is total absolute error divided by total actual
                    generation.
                  </p>
                </Pane>
                <Pane title="SOURCE">
                  <p>Actuals: Elexon FUELHH, fuel type WIND.</p>
                  <p>Forecasts: Elexon WINDFOR.</p>
                  <p>All timestamps are UTC.</p>
                </Pane>
              </section>
            )}
          </>
        )}
      </main>
      <footer className="statusbar">
        F1 OVERVIEW | F2 VINTAGES | F3 QUALITY | F4 METHOD{" "}
        <span>WINDDESK 1.0 // JANUARY 2026 PILOT</span>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);

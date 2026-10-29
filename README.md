# WindDesk

WindDesk is a day-ahead wind forecast evaluation terminal for a UK electricity procurement team.

It compares the wind forecast that was actually available at a declared decision moment with Elexon national wind actuals.

The pilot is intentionally limited to delivery dates in January 2026.

## Product scope

The dashboard answers four operational questions.

1. How accurate was the forecast available before delivery?
2. Which delivery days and intervals produced the largest forecast misses?
3. Which forecast vintages existed for a particular delivery interval?
4. Is the apparent accuracy based on complete and correctly matched data?

The dashboard does not estimate prices, imbalance charges, demand, or procurement cost.

## Terminal design system

The frontend uses a Bloomberg-inspired terminal presentation adapted for wind-forecast analysis.

### Visual decisions

| Decision | Implementation | Reason |
| --- | --- | --- |
| Canvas | `#000000` globally | Maintains a true terminal ground with no gradients or softened surface colors. |
| Structure and interactive focus | `#00FFFF` cyan | Makes panes, navigation, labels, and active controls scannable without implying a data result. |
| Primary data | `#FFB000` amber | Keeps the core figures and terminal copy legible against black. |
| Positive signal | `#00FF00` green | Reserved for under-calling bias and fully matched data. |
| Negative signal | `#FF0000` red | Reserved for over-calling bias, missing data, and service failures. |
| Separators | `#333333` | Frames every widget and divides panes while remaining subordinate to data. |
| Typography | JetBrains Mono, Fira Code, Consolas, then Courier New | Uses a monospace stack with no proportional fallback. |
| Density | 10px to 12px body copy and 4px to 7px internal spacing | Prioritises visible data and avoids dashboard card padding. |
| Shape | Square corners and 1px borders only | Reinforces a window-manager and terminal visual language. |
| Interaction | A cyan block cursor blinks in date-command controls | Signals input affordance while preserving the compact terminal treatment. |
| Data tables | Compressed rows with numeric columns right-aligned | Makes time-series comparisons faster to scan. |
| Responsive layout | Panes collapse to one column below 700px | Keeps every workflow available on small screens without a separate mobile product. |

The UI deliberately avoids rounded cards, shadows, gradients, decorative imagery, and soft neutral palettes.

### Layout decisions

The top bar reports source state and provides export access.

The F1 to F4 tab bar exposes Overview, Vintages, Data Quality, and Method without hiding primary workflows in a sidebar.

The query pane remains above the analysis so the active delivery window, forecast policy, and decision moment are visible.

The overview uses three panes for daily error selection, a delivery profile, and a procurement-oriented bias readout.

The vintage view pairs an interval list with its audit trail so a user can inspect forecast publication history without changing context.

The data-quality view preserves every expected half-hour and includes filters plus pagination to avoid rendering a long unbounded table.

## Forecast decision moments

Decision-time mode selects the newest forecast published no later than the configured UTC cutoff on the day before delivery.

The default is 09:20 UTC because it aligns the evaluation with the GB day-ahead auction timing.

The named presets are operational reference points rather than an assertion that each is a forecast publication schedule.

| UTC time | Reference point |
| --- | --- |
| 06:00 | CHAPS opens. |
| 08:00 | London cash market opens. |
| 09:20 | GB day-ahead auction. |
| 16:30 | London cash market closes. |
| 17:40 | CHAPS customer-payment deadline. |

Users can select `CUSTOM TIME` to provide any minute-precise UTC cutoff.

Hindsight mode instead selects the newest forecast published before the delivery interval and is clearly labelled as retrospective.

## Data pipeline

```text
Elexon FUELHH                       Elexon WINDFOR
half-hour actual generation         forecast vintages
fuelType = WIND                     publish time + delivery start
          │                                      │
          └──────────────┬───────────────────────┘
                         ▼
               FastAPI retrieval layer
               validate January 2026 window
               parse UTC timestamps
               retain latest actual record
                         │
                         ▼
              forecast selection policy
              decision cutoff or hindsight
                         │
                         ▼
             exact timestamp match by startTime
             preserve unmatched half-hours
                         │
                         ▼
             MAE, RMSE, bias, and WAPE
                         │
                         ▼
      React terminal dashboard and CSV audit export
```

### Retrieval

The backend requests actual generation from Elexon `FUELHH` and retains only `WIND` fuel records.

The backend requests forecast vintages from Elexon `WINDFOR` over a sufficient publication-time window.

All timestamps are normalised to UTC.

### Actual selection

`FUELHH` can expose more than one publication for the same delivery interval.

The pipeline retains the latest valid actual publication for each interval start.

The response retains `actual_publish_time` so the UI and CSV can show when that actual became available.

### Forecast selection

For decision-time mode, a forecast is eligible only if its publication time is at or before the configured day-before delivery cutoff.

For hindsight mode, a forecast is eligible only if it was published at or before its delivery start.

The eligible forecast with the latest publication time wins for each delivery interval.

The selected forecast publication time is preserved as `publish_time`.

### Matching and completeness

Actuals and selected forecasts join only when their UTC interval starts are identical.

No unmatched record is converted to zero generation.

The API creates every expected half-hour in the chosen delivery window and labels it `matched`, `forecast_only`, `actual_only`, or `missing`.

The coverage counts and Data Quality table therefore make hourly forecast coverage versus half-hourly actual coverage explicit.

### Metrics

For matched intervals, forecast error equals forecast MW minus actual MW.

MAE is the mean absolute forecast error.

RMSE is the square root of the mean squared error and gives extra weight to large misses.

Bias is the signed mean forecast error.

WAPE is total absolute error divided by total actual generation.

## API

### `GET /health`

Returns the API liveness status.

### `GET /api/analysis`

Example request:

```text
/api/analysis?start_date=2026-01-01&end_date=2026-01-31&mode=decision&cutoff_time=09:20
```

| Parameter | Meaning |
| --- | --- |
| `start_date` | Inclusive January 2026 delivery-date start. |
| `end_date` | Inclusive January 2026 delivery-date end. |
| `mode` | `decision`, `latest`, or `vintage`. |
| `cutoff_time` | Optional decision cutoff as `HH:MM` UTC. |
| `cutoff_hour` | Backward-compatible whole-hour cutoff. |
| `vintage_time` | Timestamp for explicit vintage mode. |

The response includes the selection contract, aggregate metrics, coverage counts, period records, daily summaries, and retrieval time.

### `GET /api/vintages`

Example request:

```text
/api/vintages?start_time=2026-01-20T12:00:00Z
```

The response lists available forecast vintages for the requested delivery interval.

## Architecture

```text
frontend/
  src/main.jsx         React UI state, terminal panes, data interaction, CSV export
  src/terminal.css     Terminal design system and responsive grid rules
  vite.config.js       Local API proxy configuration

backend/
  app/elexon.py        Elexon HTTP client and payload parsing
  app/analysis.py      Forecast selection, matching, and metrics
  app/main.py          FastAPI routes and response assembly
  tests/               Unit and API tests
```

The separation keeps Elexon parsing, forecast policy, metric calculation, and presentation independently testable.

## Run locally

Docker is the supported full-stack path.

```bash
docker compose up --build
```

Open `http://localhost:5173`.

The web container proxies `/api` and `/health` to the API container.

For local development without Docker, start the API on port 8000 and the Vite frontend on port 5173.

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
```

```bash
cd frontend
npm ci
npm run dev
```

## Verification

Run backend tests:

```bash
backend/.venv/bin/pytest backend/tests
```

Build the frontend:

```bash
cd frontend
npm run build
```

Verify the composed service:

```bash
curl -f http://localhost:5173/health
curl -f "http://localhost:5173/api/analysis?start_date=2026-01-01&end_date=2026-01-01&mode=decision&cutoff_time=09:20"
```

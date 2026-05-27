# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of **standalone administration scripts** for ArcGIS Enterprise (Portal + Server) and ArcGIS Online — service publishing, item/content management, metadata harvesting, geodatabase/SDE administration, and Windows/Linux operational monitoring. It is not an application or installable package: there is no build, no test suite, no linter, and no shared library. Each script is run on its own.

Languages in play: Python (the bulk — `arcpy` + the ArcGIS API for Python `arcgis`), SQL (geodatabase/SDE role & schema admin), PowerShell (`.ps1`), Windows batch (`.bat`), and one R script. Most work lives under `admin/`; `README.md` (repo root), `admin/README.md`, and `Reference/README.md` describe individual scripts.

## Placeholder / de-branded values (read this first)

This repo has been **de-branded**: real organization names, hostnames, database names, and URLs were replaced with generic placeholders, so **scripts will not connect to anything until you re-point them.** The scheme:

| Placeholder in the code | Replace with your… |
|---|---|
| `gis.example.com`, `gis2.example.com` | ArcGIS Enterprise portal/server host(s) |
| `myorg.maps.arcgis.com` | ArcGIS Online org URL |
| `org-app1`, `org-app2`, … | server hostnames |
| `ORG_WS`, `ORG_DB2`, `ORG_*` | SDE / SQL database names (and the `ORG_*_sde.sde` connection files) |
| `ORG`, `ENT` (portal-selector codes) | your internal portal labels |
| `ORG_ARCGIS_MS_CREDS_NAME` (env key), `org_powerautomate_gisemail` (keyring cred) | your real env-var key / Windows Credential Manager entry names |

If you rename the env key or credential here, the corresponding deployed `.env` key and Windows Credential Manager entry must match, or the monitor/email scripts won't find credentials.

## Running scripts

There is no central entry point. Run each script directly **from inside the ArcGIS Pro conda environment (Python 3.11)** — `arcpy` and `pandas` come from that env; extras like `flask`, `keyring`, `python-dotenv`, `rasterio`, `xmltodict` may need `pip install` into a cloned env.

```powershell
python admin\GetAllArcGISServiceMetadata.py
python admin\PublishFromDBToFeatureService.py "C:\path\to\import.csv"   # CSV path is an optional argv
```

- Most scripts have **hardcoded paths and config constants near the top** (output dirs, server paths, toggles like `DEBUG_MODE`, `stageService`, `uploadToServer`). Review and edit these before running on a new machine — they are the primary way behavior is changed, alongside `.env`.
- The LogViewer is the one web app: `python admin\LogViewer\app.py`, then open `http://localhost:5000`. Its **Refresh button re-runs `MonitorArcGISEnterpriseLogs.py` / `WindowsServicesMonitor.py` via subprocess**, which can in turn fire the Power Automate email send — refreshing is not a read-only action.

## Configuration & secrets

- Scripts read config from a `.env` file in the same directory via `python-dotenv`. **Any missing/empty `.env` value falls back to an interactive prompt** (`getpass`), so `.env` is optional convenience, not required.
- **`.env.example` is the tracked template; copy it to `.env` and fill in real values.** `.env` is gitignored (`*.env`); `.env.example` is committed (`!.env.example`). Files ending in `.bat_sample` follow the same copy-without-suffix pattern for batch wrappers.
- No secrets live in code or `.env`: passwords come from interactive prompts or **Windows Credential Manager via `keyring`** (referenced by name — `.env` var `ORG_ARCGIS_MS_CREDS_NAME`; the email integration uses credential `org_powerautomate_gisemail`). The Power Automate endpoint host is read from `POWERAUTOMATE_BASE_URL`.
- `Input/`, `Output/`, `Scratch/`, `Archive/` are gitignored working folders. Scripts create `Output/` on demand and write **timestamped** files (logs, CSVs, JSON) there.

## Authentication patterns

Scripts pick one of these; know which before editing auth code:
- `GIS("pro")` — reuse the running ArcGIS Pro session (interactive use).
- `GIS(portal_url, username, password)` with `getpass()` prompts. Note: the admin username generally **cannot be SSO-enabled**.
- REST token via a `get_token()` helper hitting `/sharing/rest/generateToken` (portal/server) or `https://www.arcgis.com/sharing/rest/generateToken` (AGOL).
- **Windows Credential Manager via `keyring`** — stored creds referenced by name (see Configuration above). No passwords in code or `.env`.

## Cross-script & network-share conventions (important)

- Scripts are **deliberately standalone — no normal `import` between them.** `Reference/` is a copy-paste library, not an importable module; copy the function you need into your script.
- The **one exception**: the monitor scripts (`MonitorArcGISEnterpriseLogs.py`, `WindowsServicesMonitor.py`, `GeoProcesssingToolMonitor/`) reuse `send_email_using_powerautomate.py` by appending a hardcoded network path to `sys.path` and dynamically `importlib.import_module(...)`. That path points at the team's canonical deployed copy on a network (`T:`) share.
- Treat this local checkout as the dev copy; the **scheduled/production copy runs from that `T:` share**. If you change a script that others import or that a scheduled task runs (the monitors, the email helper), the share copy is what actually executes — hardcoded share paths are intentional, not bugs to "clean up."

## Environment specifics

ArcGIS Enterprise lives at the placeholder host `gis.example.com` (portal at `/arcgisportal`, server at `/arcgisserver`); backing machines are referenced as `org-app1` / `org-app2`. CSV-driven bulk scripts (publishing, GDB copy) read their CSV from `admin/Documentation/`.

# arcgis_admin

A collection of **standalone administration scripts** for ArcGIS Enterprise (Portal + Server) and ArcGIS Online: service publishing, item/content management, metadata harvesting, geodatabase/SDE administration, and Windows/Linux operational monitoring.

This is not an application or installable package — there is no build step, test suite, or shared library. Each script runs on its own, typically from inside the ArcGIS Pro Python environment.

> **Heads up — placeholder values.** This repo has been de-branded: organization names, hostnames, database names, and URLs are generic placeholders (`gis.example.com`, `org-app1`, `ORG_WS`, `ORG`/`ENT`, …). **Scripts will not connect to anything until you replace these with your real values** (via `.env` where supported, or by editing the constants near the top of each script). See [CLAUDE.md](CLAUDE.md#placeholder--de-branded-values-read-this-first) for the full placeholder map.

## Repository layout

| Path | Contents |
|---|---|
| `admin/` | The bulk of the scripts — publishing, item/content admin, GDB/SDE tools, server/OS monitoring, conda-env utilities. See **[admin/README.md](admin/README.md)**. |
| `admin/LogViewer/` | Flask web viewer for the CSV log files written by `MonitorArcGISEnterpriseLogs.py`. |
| `admin/GeoProcesssingToolMonitor/` | Geoprocessing-job watcher with a `.bat` wrapper. |
| `admin/PythonEnvironmentDetector/` | ArcGIS geoprocessing tool that reports the active Python environment. |
| `admin/Documentation/` | Sample CSVs for the CSV-driven bulk scripts. |
| `Reference/` | Copy-paste snippet library (not imported anywhere). See **[Reference/README.md](Reference/README.md)**. |
| `WorldPopDownload.py` | Standalone: downloads & mosaics WorldPop population rasters. |
| `LinuxFileTransfer.bat` | Standalone: helper for transferring files to/from a Linux host. |

## Prerequisites

- **ArcGIS Pro** with its conda Python environment (Python 3.11) — provides `arcpy` and the ArcGIS API for Python (`arcgis`), plus `pandas`.
- Some scripts need extra packages not in the stock ArcGIS env. Install into a **cloned** conda env (don't modify the base ArcGIS env):
  ```powershell
  pip install python-dotenv keyring flask rasterio xmltodict tqdm requests
  ```
- SQL scripts (`admin/*.sql`) run against the SDE/SQL Server database via `sqlcmd` or a SQL client.

## Configuration

Scripts that take configuration read it from a `.env` file in the same directory via `python-dotenv`.

1. Copy the template and fill in real values:
   ```powershell
   copy admin\.env.example admin\.env
   ```
2. Edit `admin\.env`. **Any missing or empty value falls back to an interactive prompt**, so `.env` is a convenience, not a requirement.

`.env` is gitignored; **`.env.example` is the committed template** — keep it in sync when you add new settings. Batch wrappers follow the same convention via `*.bat_sample` templates.

Working folders `Input/`, `Output/`, `Scratch/`, and `Archive/` are gitignored; scripts create `Output/` on demand and write timestamped logs/CSVs/JSON there.

## Authentication

No passwords are stored in code or `.env`. Scripts use one of:

- `GIS("pro")` — reuse the running ArcGIS Pro session.
- `GIS(portal_url, username, password)` with `getpass()` prompts (the admin account generally cannot be SSO-enabled).
- A REST token via `/sharing/rest/generateToken` (Enterprise) or `https://www.arcgis.com/sharing/rest/generateToken` (AGOL).
- **Windows Credential Manager via `keyring`**, referenced by name — the `.env` var `ORG_ARCGIS_MS_CREDS_NAME` for portal creds, and credential `org_powerautomate_gisemail` for the email integration. The Power Automate endpoint host comes from the `POWERAUTOMATE_BASE_URL` env var.

## Running

Run each script directly from an ArcGIS Pro conda prompt:

```powershell
python admin\GetAllArcGISServiceMetadata.py
python admin\PublishFromDBToFeatureService.py "C:\path\to\import.csv"   # optional CSV argument
```

Most scripts have hardcoded paths and behavior toggles near the top of the file — review them before running on a new machine.

### LogViewer (web app)

```powershell
python admin\LogViewer\app.py
# then open http://localhost:5000
```

Its **Refresh** button re-runs the log/service monitors via subprocess and may trigger the Power Automate email send — it is not a read-only action.

## Notes

- Scripts are intentionally **standalone** — there are no cross-script imports except the monitor scripts, which load `send_email_using_powerautomate.py` from a deployed network (`T:`) share via `sys.path`. That share copy is what scheduled tasks actually run.
- See [admin/README.md](admin/README.md) for a per-script breakdown and [CLAUDE.md](CLAUDE.md) for architecture and conventions.

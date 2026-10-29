# ArcGIS Admin

Scripts for administering ArcGIS Enterprise (Portal + Server) and ArcGIS Online - service publishing, item/content management, metadata harvesting, geodatabase administration, and Windows/Linux operational helpers.

## What's in here

- **Portal / AGOL items**
  - `GetAllArcGISServiceMetadata.py` - crawls a portal and exports every item's metadata + service JSON to `Output/`.
  - `extract_featureLayer_metadata_from_ArcGIS_portal.py`, `ListWebMapLayers.py`, `ListWebAppBuilderLayers.py`, `Parse_GDB_ITEMS.py`, `ParseManifestXMLFiles.py` - inventory helpers.
  - `UpdateArcGISItem.py`, `SetArcGISItemDeprecated.py`, `ChangeArcGISOwner.py`, `CopyDetailsOwnerGroupsOldItemToNew.py`, `AddItemWithStoredCredentials.py` - bulk item edits.
  - `Import_Content_from_Portal_to_AGOL.py` - content migration.

- **Service publishing**
  - `PublishFromDBToFeatureService.py` - CSV-driven bulk publish from SDE to feature services (see `Documentation/PublishFromDBToFeatureService.csv`).
  - `publish_features_to_agol_bulk.py`, `PublishRasterAsImageService.py`, `PublishGPTool.py`, `UploadFromSD.py`, `ListAndUpdateServices.py`, `modifyArcGISServices.py`.

- **Geodatabase / SDE**
  - `CreateGeodatabase.py`, `CreateSDEFiles.py`, `upgrade_gdb.py`, `testSDE.py`, `ExportXMLWorkspaceDocument.py`.
  - `CopyFeaturesToGDB.py` / `CopyRastersToGDB.py` / `copyFeaturesFromService.py` / `ArcPyExportFeatures.py` / `projectAllGDBFeatures.py` - feature/raster copy + projection.
  - SQL: `CreateDBRoles.sql`, `CreateDBSchema.sql`, `GrantDBPermissions.sql`, `All_GDB_Item.sql`, `All_GDB_Item_Relationships.sql`, `get_table_spatial_geometry.sql`.
  - `ApplyDBRolePrivileges.py` / `.bat` + `GrantDBUserPrivileges.py` - DB role/permission application.

- **Server / OS operations**
  - `GatherServerProperties.py` - exports per-server, per-service, and per-resource JSON.
  - `MonitorArcGISEnterpriseLogs.py` / `.bat_sample` - log polling.
  - `WindowsServicesMonitor.py` / `.bat_sample`, `WindowsServicesRestart.ps1` - Windows service watchdog.
  - `EnableInheritDirSecurity.ps1` - NTFS inheritance fix.
  - `GeoProcesssingToolMonitor/` - geoprocessing job watcher with `.bat_sample` wrapper.

- **Conda env utilities**
  - `CompareCondaEnvs.py` / `.ipynb`, `compare_yml_files.py`, `list_yml_libs.py`, `combine_json_files.py`, `CloneCondaEnv.bat_sample`, `install_certifi.py`.

- **Misc**
  - `feature_to_rasters.py`, `TimeEnabledRastersToCRF.py`, `ExtractPointsFromKMLorKMZ.py`, `calculate_population_within_aoi.py`, `BasinATLAS_Global_Population.R`.
  - `send_email_using_powerautomate.py` + `EmailStringAttachmentToGIS_PowerAutomateFlow.json` - Power Automate email integration.
  - `DirectoryCompare.py`, `UniqueLogRecords.py`, `ToolboxProperties.py`.

## Configuration

Copy `.env_sample` to `.env` in this folder and fill in:
- `PORTAL_URL`, `FEDERATED_SERVER_URL`, `ARCGIS_SERVER_MANAGER_URL`
- `PORTAL_USERNAME` (interactive password prompt is standard) or `NBS_ARCGIS_MS_CREDS_NAME` for stored creds
- DB connection settings: `WORKSPACE_TYPE_FILEGDB_OR_SDE`, `WORKSPACE_FULL_PATH`, `DATABASE_NAME`, `DATABASE_OWNER_NAME`
- See `.env_sample` for the full list

CSV-driven scripts (publishing, GDB copy) take their CSV from `Documentation/`. `Input/`, `Output/`, `Scratch/`, and `Archive/` are working folders (mostly gitignored).

Any `*.bat_sample` / `*.env_sample` file is a template; copy without the `_sample` suffix and edit locally - the populated version is gitignored.

## Authentication

Most scripts use one of:
- `GIS("pro")` - current ArcGIS Pro session (preferred when running interactively)
- `GIS(portal_url, username, password)` with `getpass()` prompts
- REST token via `get_token()` against `/sharing/rest/generateToken`

## Running

Run each script from inside the ArcGIS Pro conda env (Python 3.11). Most scripts have hardcoded paths near the top - review and edit before running on a new machine.

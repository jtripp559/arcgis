# AGOL -> MS SQL Enterprise Geodatabase Migration Plan

## Run it (quick start)

From the deployed `Migrate` folder (`C:\Admin\Tools\ArcGIS Admin\Migrate`), in the ArcGIS Pro conda env:

```
python run_migration_batch.py --manifest Input\ItemsToMigratePhase1.csv
```

`Input\ItemsToMigratePhase1.csv` is also the default, so `python run_migration_batch.py` alone does the same.

**Just finish the to-do items already in the ledger (no new downloads):** add `--ledger-only` - it processes
ONLY items already in the ledger (finishes in-progress copies + runs the publish..deprecate sweeps) and does
NOT start any new manifest items:

```
python run_migration_batch.py --ledger-only
```

Re-running is safe/idempotent: finished items are skipped, and rows carrying an `error` are skipped until you
clear them with `python clear_error.py <id>` (or `--all`). For staged/safe runs (dry-run, smoke-test a few,
hold the irreversible deprecate) and every flag, see *How to run the batch in production* below.

**Stop a run cleanly (after the current child finishes):** from another shell,
`python run_migration_pipeline.py --request-stop` (or create the file `Migrate\STOP_MIGRATION`). The running
batch/pipeline quits gracefully without killing the in-flight child; stopped items stay resumable and the
flag auto-clears on the next run. See *Stopping a run gracefully* below.

**Goal:** Copy an initial batch of **38 hosted feature services** from ArcGIS Online (AGOL)
into the `RRGOrg` Microsoft SQL Server enterprise geodatabase - preserving **data,
attachments, relationships, and symbology** - re-publish them as **referenced**
feature services on ArcGIS Enterprise, and finally **share each Enterprise item back to AGOL
by reference (with stored credentials)** so AGOL consumers still see it.

Full round-trip: **AGOL (hosted) -> RRGOrg SQL -> Enterprise (referenced) -> AGOL (by-reference item)**.

Status: DRAFT plan. Date: 2026-06-02. Owner: Julie Tripp.

---

## Pipeline stages at a glance (sequence order)

> **"Stage" vs "state" - they are different.** A **stage** is a pipeline STEP (a script the orchestrator
> runs, keyed for `--from`/`--to`/`--only`). A **state** is the ledger MILESTONE an item has reached (the
> `state` column). Some stages advance the state; others (manifest, relationships, thumbnails, group share,
> owner reassign, QA) do work WITHOUT moving the state (shown as `-`). Stage order comes from
> `run_migration_pipeline.build_stages`; the state vocabulary is `migration_status_ledger.STATES`.
> Status as of 2026-06-12.

|  # | Stage (key)           | Action                                                                                                                                                | Scope    | Ledger state it sets                                  | Status                                                      |
| -: | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------- | ----------------------------------------------------------- |
|  1 | `manifest`          | BuildMigrationManifest - expand multi-layer services into a per-layer/table CSV                                                                       | once     | `-`                                                 | **TODO** (multi-layer only)                           |
|  2 | `step1`             | Inspect source + resolve destination FC name                                                                                                          | per item | `-` (writes `poc_output` artifacts)               | DONE                                                        |
|  3 | `step3`             | Stage AGOL -> local FGDB + reproject to WGS84.**Route (b): export-to-FGDB (`EXPORT_MODE="always"`) w/ copyData fallback**                     | per item | `copied_local`                                      | DONE                                                        |
|  4 | `step3c`            | Load staged FGDB -> RRGOrg SDE (**`preserveGlobalIds=True`** -> carries attachments + relationships + original GlobalIDs)                     | per item | `copied_to_gdb`                                     | DONE                                                        |
|  5 | `attachments`       | **Travel WITH the data via route (b) export** - no separate pass. `copy_attachments.py` kept as a service->service / fallback tool            | per item | `-`                                                 | **DONE/PROVEN** (route b end to end)                  |
|  6 | `relationships`     | Relationship classes (incl. attachment `__ATTACHREL`) **travel WITH route (b) export**; `CreateRelationshipsInGDB` only for any not carried | per item | `-`                                                 | **Mostly via route b** (standalone helper still TODO) |
|  7 | `publish_csv`       | BuildPublishCSV - generate the publish-input CSV (gated at `copied_to_gdb`)                                                                         | once     | `-`                                                 | DONE*                                                       |
|  8 | `publish`           | Publish referenced feature services (SQL -> Enterprise)                                                                                               | once     | `published_to_portal`                               | DONE                                                        |
|  9 | `symbology_ent`     | Apply symbology + pop-ups + default view (Enterprise item)                                                                                            | once     | `portal_updated`                                    | DONE                                                        |
| 10 | `thumb_copy_portal` | Set Enterprise thumbnail from the AGOL original (render fallback)                                                                                     | once     | `-`                                                 | DONE                                                        |
| 11 | `qa`                | QA: row counts / field parity / visual symbology + pop-up check                                                                                       | manual   | `-`                                                 | DONE (manual)                                               |
| 12 | `source_update`     | Update source AGOL item (tags + Portal URL + comment; capture status)                                                                                 | once     | `source_updated`                                    | DONE                                                        |
| 13 | `coverage_share`    | Add the Enterprise Feature Service to the "Coverage Share" group                                                                                      | once     | `-`                                                 | DONE                                                        |
| 14 | `reassign_portal`   | Reassign Portal item owner + "Created By" + folder                                                                                                    | once     | `-`                                                 | DONE                                                        |
| 15 | `share_back`        | Create the AGOL by-reference item (stored credentials)                                                                                                | once     | `shared_to_agol`                                    | DONE                                                        |
| 16 | `symbology_agol`    | Re-apply symbology + pop-ups + default view (AGOL item)                                                                                               | once     | `agol_updated`                                      | DONE                                                        |
| 17 | `thumb_copy_agol`   | Copy the Enterprise Portal thumbnail onto the AGOL item                                                                                               | once     | `-`                                                 | DONE                                                        |
| 18 | `reassign_agol`     | Reassign by-ref AGOL item to original owner + folder; share to org group                                                                              | once     | `-`                                                 | DONE                                                        |
| 19 | `deprecate`         | Propagate authoritative, then deprecate the source (GATED, irreversible)                                                                              | once     | `authoritative_propagated` -> `source_deprecated` | DONE                                                        |

> \* `BuildPublishCSV.py` is built and is auto-run by `run_migration_batch.py` (gated at `copied_to_gdb`). The
> serial `run_migration_pipeline.py` still treats it as optional (it consumes an existing / `--publish-csv`
> CSV), so its pipeline stage prints `[TODO]` there even though the script exists.

**Ledger `state` order** (the milestone an item has reached, earliest -> terminal):
`copied_local` -> `copied_to_gdb` -> `published_to_portal` -> `portal_updated` -> `source_updated` ->
`shared_to_agol` -> `agol_updated` -> `authoritative_propagated` -> `source_deprecated`.

> **DONE = the stage/script is BUILT and proven on the POC items**, not that the whole batch is finished. The
> only unbuilt stage is the multi-layer `manifest` helper. **Attachments + relationships are PROVEN end to end
> (2026-06-12) via "route (b)"** -- staging by export-to-FGDB instead of copyData carries the `__ATTACH` table,
> the `__ATTACHREL` relationship class, and the ORIGINAL GlobalIDs all the way into the by-reference Enterprise
> service, which serves the attachment blobs (see Phase 2/Phase 3 and `docs/attachments-copy-plan.md`).
> `copy_attachments.py` is no longer on the SDE path (kept as a fallback / service->service tool). For live run
> status see *Section 9 - POC status*.

---

## How to run the batch in production (`run_migration_batch.py`)

> **Where it runs:** from the DEPLOYED copy on nbs-app2 - `C:\Admin\Tools\ArcGIS Admin\Migrate` - inside the
> ArcGIS Pro conda env (`...\envs\arcgispro3_5-clone\python.exe`). Edits in the repo must be redeployed there
> first. `run_migration_batch.py` is the PARALLEL driver (copy several items at once + incremental publish
> sweeps); `run_migration_pipeline.py --run` is the serial equivalent.

**1. Work list = the manifest CSV (default or `--manifest`).** The driver migrates every item in the
work-list CSV that is not already finished in the ledger. Default is
**`Migrate\Input\ItemsToMigratePhase1.csv`**; point it at a different file with **`--manifest <path>`** (e.g. a
per-phase `Input\ItemsToMigratePhase2.csv`). The flag is exported as **`MIGRATION_MANIFEST_PATH`**, so the copy
work list AND every child stage that reads the manifest (step1, publish, BuildPublishCSV) all key off the same
file (resolver: `items_manifest.default_manifest_path()`). Required columns:
`AGOL Item ID, AGOL Title, AGOL_Owner, Target Database, Target Database Schema, Connection_Filepath`.

**2. Supporting Input/credential setup (must cover every item in the run):**

- `Migrate\Input\Owner_Map.csv` - `AGOL_Owner` -> `Portal_Owner` + `Owner_Name` (unmapped or Viewer owners fall
  back to `rrgadmin` + a name tag; validate first with `python check_owner_map.py`).
- `Migrate\Input\Folder_Map.csv` - source `owner_folder` -> server / portal-user folders.
- The publish CSV is **auto-generated** by `BuildPublishCSV` (gated at `copied_to_gdb`) to
  `Migrate\Output\publish_input_batch.csv`; an existing one is reused unless `--regen-publish-csv`. Review its
  `agol_owner_folder` column before a large run.
- Store the three logins once (else runs prompt/stall): `python credential_store.py set agol` / `set portal` /
  `set GPUser`. (A bad `GPUser` is what blocked the POC at `share_back`.) RRGOrg schemas must already be
  registered as a federated data store.

**3. Production run recipe (staged - safest):**

```
# from C:\Admin\Tools\ArcGIS Admin\Migrate, in the ArcGIS Pro conda env:
python run_migration_batch.py --dry-run                          # 0) preview the plan + commands, change nothing
python run_migration_batch.py --max-items 3 --to reassign_agol   # 1) smoke-test a few items end-to-end, but
                                                                 #    HOLD the irreversible deprecate
#    ...verify those few in Portal + AGOL (round-trip OK; symbology / owner / folder correct)...
python run_migration_batch.py --to reassign_agol --max-parallel 4  # 2) full batch, still holding deprecate
#    ...QA the batch (Phase 6)...
python run_migration_batch.py --ledger-only                      # 3) finish: runs the GATED deprecate (only
                                                                 #    items at agol_updated with no error)
```

- **`--to reassign_agol`** holds back `deprecate` (IRREVERSIBLE) until the by-reference items are verified. A
  plain run uses the default `--to deprecate` and WILL deprecate the sources at the end.
- **`--max-items N`** scopes the WHOLE run (copies + once-stage sweeps) to N items - use it to roll out in
  controlled waves. **`--max-parallel N`** widens the copy pool (default 2; each child is a full arcpy process,
  heavy on RAM/network on the shared box). The SDE load (step3c) is serialized regardless.
- **`--ledger-only`** processes only items already in the ledger (no new downloads) - use it to resume an
  interrupted run or to run the held-back deprecate pass.
- Re-running is safe/idempotent: finished items are skipped, **errored rows are skipped until cleared**
  (`python clear_error.py <id>` / `--all`), and the once-stages are state-gated so they don't re-process
  finished items.
- **`--manifest <path>`** runs a specific work-list CSV (default `ItemsToMigratePhase1.csv`); add the SAME
  `--manifest` to every command in a phase so the whole run (and all child stages) key off that file.
- **Existing-service handling (passed through to the publish stage)** - when a same-name service already
  exists on the server, three mutually informative flags control what happens (precedence:
  `--override-existing` > `--use-existing` > `--create-new-if-existing`; default with none of them is to
  error):
  - **`--override-existing`** (`--OverrideExisting`) - overwrite the existing same-name service.
  - **`--use-existing`** (`--UseExisting`) - if the same SDE reference can't be confirmed, use the existing
    service as-is (do NOT republish) instead of erroring.
  - **`--create-new-if-existing`** (`--CreateNewIfExisting`) - if the same SDE reference can't be confirmed,
    leave the existing service alone and publish a NEW service under the next free suffixed name (e.g.
    `<name>_2`) referencing our SDE feature class, instead of erroring.
- Other flags: `--regen-publish-csv`, `--publish-csv <path>` (curated CSV), `--settle-seconds` /
  `--state-wait-seconds`, `--python <interp>`.

**4. Stopping a run gracefully (no kill - finishes the current child first).** A long batch (or serial
`run_migration_pipeline.py --run`/`--resume`) can be asked to stop cleanly **after the currently running
child process(es) finish** - it never kills an in-flight download/load/publish, so the ledger is left at a
clean, resumable state. It is a COOPERATIVE stop: the drivers poll a sentinel file BETWEEN child launches.
From another shell while a run is going:

```
python run_migration_pipeline.py --request-stop      # creates the flag (works for batch OR pipeline)
#   ...or just create the file by hand:  type NUL > "C:\Admin\Tools\ArcGIS Admin\Migrate\STOP_MIGRATION"
```

- The flag file is **`Migrate\STOP_MIGRATION`** (override with env `MIGRATION_STOP_FILE`). It is gitignored
  (a runtime signal, never committed).
- On a stop request the batch driver stops launching new copy stages + once-stage sweeps and exits after any
  in-flight child finishes; the final straggler sweep **and the irreversible `deprecate`** are SKIPPED.
  Stopped items stay at their last clean ledger state and report as `STOPPED (graceful, resumable)`, NOT as
  copy failures.
- The flag is **auto-cleared at startup** of the next run, so a leftover file never silently blocks a fresh
  launch - just re-run (e.g. `--ledger-only`) to finish the remaining items.
- Shared implementation lives in `run_migration_pipeline.py` (`stop_requested()` / `request_stop()` /
  `clear_stop_request()`); the batch driver calls `pipe.stop_requested()`, so the two never drift. As with
  every edit, **redeploy both scripts to `C:\Admin\Tools\ArcGIS Admin\Migrate`** before a run honors them.

**5. Long unattended runs - avoid the Windows console output freeze (NOT a hang).** On a multi-day run the
driver can appear "stuck" mid-output (a sweep prints a line, then nothing for hours) and then RESUME the
instant you press a key (e.g. Ctrl+Q). That is **not** a deadlock and **not** the ledger lock - it is the
Windows console pausing the process. Windows consoles with **QuickEdit Mode** on freeze the process the
moment it next writes to stdout if the window is in mark/selection mode (a click in the window is enough);
flow control behaves the same way (Ctrl+S = XOFF pauses, Ctrl+Q = XON resumes). Because the driver logs
every line to the console, a paused console blocks it on the next log write. (A genuine stuck ledger lock is
different: it times out after 120s and the child **exits 99** to STOP the run - it never hangs for days and
never resumes from a keypress. So the lock is not the cause here; leave it alone.) For unattended runs do
BOTH:

1. **Turn off QuickEdit Mode** on the console you launch from (classic conhost: right-click the title bar ->
   Properties -> Options -> uncheck **QuickEdit Mode** and **Insert Mode**), so a click can't pause the run.
2. **Redirect output to a file** so there is no interactive console buffer to pause (the full file log via
   `setup_logging` is unaffected; the console stream is redundant):

```
python run_migration_batch.py --max-parallel 4 > Output\batch_console.log 2>&1
```

For a truly hands-off multi-day batch on nbs-app2, run it **detached / non-interactive** (a Scheduled Task,
`start /b`, or `pythonw`) so no console window exists to freeze at all.

---

## 1. Scope & inputs

For this initial batch we have, per feature service:

- `item_id` and `item_url` (the AGOL `FeatureServer` URL).
- The target **SDE connection file** (full path), the target **database** (`RRGOrg`) and **schema**
  (`clim` / `crop` / `land` / `ws`).

A feature *service* can contain **multiple layers and/or tables**, so the 38 services expand
into more than 38 destination feature classes/tables. The work list must be enumerated at the
**layer/table** level, not the service level.

**Scale note:** this initial batch is 38, but the migration eventually covers **~6500 items**. Design
choices must scale accordingly - notably **per-item, transient staging geodatabases** (`Migrate\<item_id>.gdb`,
deleted after the SDE load), not a single shared FGDB; and throughput/batching/cleanup throughout.

---

## 2. Assets we already have

| Script                                                    | Role in this migration                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GetAllArcGISServiceMetadata.py`                        | **Source of truth.** Inventory of items -> per-layer/table list, attachment flags, relationship definitions, and the item `_description.json` / `_data.json` that hold the **symbology** (`drawingInfo`/`renderer`/`popupInfo`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `CreateGDBUsers.py` / `CreateSDEFilesBulk.py`         | Create the `clim`/`crop`/`land`/`ws` schema-owner users + role membership, and the per-schema `.sde` connection files.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `CopyFeaturesToGDB.py` + `copyFeaturesFromService.py` | **Data copy "route a"** AGOL -> SDE via REST `/query` paging. **Caveat (proven 2026-06-12):** the REST/FeatureSet path copies geometry + attributes ONLY -- it **DROPS attachments AND the GlobalID field entirely** (not just regenerates), and is bounded by `maxRecordCount`. Used now only as the FALLBACK for simple single-layer items / non-exportable services.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `export_item_to_fgdb.py`                                | **Data copy "route b" (Migrate/). BUILT + PROVEN 2026-06-12.** Esri "Export to File Geodatabase" of a hosted item -> downloads + unzips a full-fidelity FGDB: ALL layers + tables + `__ATTACH` + `__ATTACHREL` relationship classes + the **ORIGINAL managed GlobalIDs**, NOT bounded by `maxRecordCount`. Temporarily enables the source `Extract` capability if off and restores it; deletes the throwaway export item; verifies per-dataset + TOTAL row counts and (optionally) GlobalID preservation. This is the staging engine `step3` now prefers (`EXPORT_MODE="always"`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `PublishFromDBToFeatureService.py`                      | Publish from the SDE to Enterprise (sddraft DOM editing).**Already implements the FEATURE path** - the main loop uses `getWebLayerSharingDraft(service_type="FEATURE")` then DOM-edits the draft **by-reference** (`IncludeDataInSDFile=false`, `ByReference=true`, injects the SDE `OnServerConnectionString`), stages, and uploads. The top banner/Description comment still says "image services" but the code does features. Caveats in Phase 5.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `ApplyDBRolePrivileges.py`                              | Grant dataset-level VIEW/EDIT to `data creator`/`editor`/`viewer` roles after data lands.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `AddItemWithStoredCredentials.py`                       | **Final step (Phase 8).** Adds an AGOL item that references the published **Enterprise** service URL with **stored credentials** (`content.add(data=item_url, item_properties={serviceUsername, servicePassword, ...})`), tagged `by reference` + `stored credentials`. Drives off an explicit `portal_item_ids_to_add` list or a portal group ("Coverage Share"). **Updated 2026-06-10:** now **strips** the Enterprise-only migration-default tags (`Migrated from AGOL`/`Migrated`, decision #10) before adding the by-reference pair, and **sets the new item's sharing** (`AGOL_SHARING_LEVEL`, default `match_source` -> mirrors the original AGOL item's access via the ledger join).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `AddItemToCoverageShareGroup.py`                        | **Phase 8 prep (decision #9/#10).** BUILT. Shares the migrated ENTERPRISE **Feature Service** item(s) to the `"Coverage Share"` group. The work list is **Feature Services only** (`ALLOWED_ITEM_TYPES=["Feature Service"]`); but **`SHARE_BACKING_MAP_IMAGE_LAYER=True` (2026-06-10, decision #9)** also pulls each Feature Service's **backing Map Image Layer** (sibling `.../MapServer` Map Service) into the group alongside it, detected by `find_backing_map_services()` (relationships first, then a fallback matching the sibling MapServer url against candidates found by BOTH the item title AND the url-derived name). So the Map Image Layer is **group-shared + reassigned in Portal but NOT shared back to AGOL** (the AGOL share-back work list stays Feature-Service-only). Pro-session-first auth (else username/password); `gis.groups.search` + `item.share(groups=[id])`; idempotent (reports "already in"); `DRY_RUN`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `run_migration_pipeline.py`                             | **Pipeline orchestrator (Migrate/). BUILT 2026-06-10.** One ordered DEFINITION of the whole pipeline plus a small engine. `--plan` (default) prints every stage in execution order marked `[BUILT]`/`[TODO]` with its driver + the ledger state it advances to, the WORK LIST (manifest items not yet in the ledger), the IN-PROGRESS items, and the NEXT TODO to implement -- a living reference for "what to build next". `--run` executes the built stages over the work list (per-item copy stages loop the new ids; once stages run a single ledger/CSV/group-driven invocation). Work list = `ItemsToMigratePhase1.csv` MINUS the ledger ("in the ledger = already being processed"). `--run --item <id>` **auto-resumes** an in-ledger item from its current state. **`--resume`** continues every UNFINISHED ledger item (state != `source_deprecated`) that has been **idle >= `--stale-minutes`** (default 60), starting at the earliest stage any of them still needs -- so recently-updated/in-flight items are left alone. `--skip-unbuilt`/`--from`/`--to`/`--only`/`--dry-run`/`--item`/`--max-items`. **`--request-stop`** creates the cooperative stop flag (`Migrate\STOP_MIGRATION`) so a RUNNING `--run`/`--resume` (or a batch run) quits gracefully after its current child finishes; the flag auto-clears at the next start.                                             |
| `run_migration_batch.py`                                | **Parallel batch runner (Migrate/). BUILT 2026-06-11.** The "see AGOL results sooner" companion to `run_migration_pipeline.py`: copies several items at once (`--max-parallel`, default 2; the SDE-load step3c is serialized behind a lock) and fires incremental **once-stage sweeps** (publish .. reassign_agol) as each item finishes copying, so ready items publish while big layers still download; runs `deprecate` last (gated). Reuses `run_migration_pipeline.build_stages` so the two never drift. Auto-generates the publish CSV via `BuildPublishCSV` (gated at `copied_to_gdb`). Between copy stages it holds a **ledger gate** - a stage's milestone state must appear with **no error** before the next stage runs; a row carrying an `error` is skipped until cleared (`clear_error.py`). `--max-parallel`/`--max-items`/`--to`/`--ledger-only`/`--manifest`/`--publish-csv`/`--regen-publish-csv`/`--dry-run`/`--settle-seconds`/`--state-wait-seconds`/`--override-existing`/`--use-existing`/`--create-new-if-existing`. **Graceful stop:** polls a sentinel file (`Migrate\STOP_MIGRATION`, created by `run_migration_pipeline.py --request-stop`) BETWEEN child launches - on a stop request it stops starting new copy stages + sweeps and exits after the in-flight child finishes, SKIPPING the final straggler sweep and the irreversible `deprecate`; stopped items stay resumable and the flag auto-clears next run.                                                  |
| `clear_error.py`                                        | **Ledger error-clear CLI (Migrate/). BUILT 2026-06-12.** Clears the `error` column on one or more ledger rows so a fixed item can be retried (the batch driver, `BuildPublishCSV`, and the deprecate gate all SKIP errored rows by design). `clear_error.py <id ...>` / `--all` / `--phase <p>` / `--dry-run` / `--ledger-path`; resolves a source `item_id` or a destination (enterprise/by-ref) id; leaves `state` untouched. Thin wrapper over `migration_status_ledger.clear_errors()`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `copy_attachments.py`                                   | **Attachments copy (Migrate/). BUILT 2026-06-12. NO LONGER ON THE SDE MIGRATION PATH** -- route (b) export carries attachments with the data, so a separate pass is not needed; kept as a reusable standalone tool (service->service attachment copy, or a fallback when an item cannot be exported). Standalone, reusable: copies geodatabase attachments from a source AGOL/Portal feature layer to a destination arcpy FC (the SDE case) or a destination service layer. Matches source->dest features on `--join-field` (default GlobalID, GUID-normalized; validates uniqueness + overlap and fails loudly), downloads via the ArcGIS API to a per-source subfolder under `...\AGOL\Migrate\Attachments` (KEPT by default; `--cleanup-downloads`), enables attachments on an arcpy dest (`AddGlobalIDs` only if none), loads via an `AddAttachments` match table (or `attachments.add` for a service), and has an idempotency guard (skips any source attachment already on the dest by feature+name+size). `--from-step1 <id>` auto-fills source+dest from the Step-1 report; `--dry-run`. Does NOT advance a ledger state (records errors under phase `attachments` when `--item-id`/`--from-step1` given). **Full plan: `docs/attachments-copy-plan.md`.**                                                                                                                                                                |
| `RegenerateItemThumbnails.py`                           | **Thumbnail regeneration (Phase 4b / Step 6b).** BUILT. Headless equivalent of the portal "Update Thumbnail -> Create from Map": renders each item's layer(s) on the portal basemap via the **print service** (Export Web Map Task, `MAP_ONLY`) and sets the result as the item thumbnail (`item.update(thumbnail=...)`). Renders with the **item `/data`** renderer (not the service renderer), so by-reference services - whose service renderer stays `simple` - get a correctly symbolized thumbnail instead of a single color. Username/password login (needs a real token to pass per operational layer; `GIS("pro")` exposes none). `list`/`query` modes; `DRY_RUN`. **COPY MODE (added 2026-06-10):** copy an **existing** thumbnail onto the target instead of re-rendering (importable `copy_thumbnail()`, cross-portal safe): (a) **`--copy-agol-to-portal`** (ledger-driven, Phase 4b) sets the **Enterprise** item's thumbnail from the **ORIGINAL AGOL item** (+ Map Image sibling), FALLING BACK to a server render if the AGOL item has none; (b) **`--copy-portal-to-agol`** (ledger-driven, Phase 8) sets the **AGOL by-reference** item's thumbnail from the **Enterprise Portal item**; (c) **`--copy-from <src> <targets...>`** ad hoc. So the render is now the fallback, not the default; publish + Step 6 run with `regen_thumbnail=False`. |

**Gaps to build (new scripts):**
0. `migration_poc_step1_inspect.py` - **BUILT** (`docs/plan/completed/`). POC Step 1 for one item: reads
   the cached DataDump JSON, pulls the **live** service-layer definition (renderer/`drawingInfo`,
   fields+types, geometry, OID/GlobalID, attachments, count, SR), and resolves the destination FC
   name per the naming rule against the target SDE. Read-only; writes `poc_output/` artifacts
   (`_service.json`, `_renderer.json`, `_step1_report.json`). Precursor to `BuildMigrationManifest.py`.

1. `BuildMigrationManifest.py` - expand the 38 services into a per-layer/table CSV using the metadata output.
2. `ApplySymbology.py` - re-apply captured `drawingInfo`/`popupInfo` to the destination layer (the hard part). **A working pilot exists:** `docs/plan/AGOAssistant/update_item_data.py` (`--apply item|service|both`, layer-id remap, backups); `ApplySymbology.py` adds field-name remap + batch from the manifest.
3. `CreateRelationshipsInGDB.py` - **mostly OBVIATED by route (b)** (export carries relationship classes incl. `__ATTACHREL` into SDE). Still TODO only for relationships NOT carried by the export (e.g. an end migrated separately). Plus `export_item_to_fgdb.py` is **BUILT** (`Migrate/`) - the route-(b) staging engine that made attachments/relationships/GlobalIDs work; see Section 2.
4. **`UpdateSourceAGOLItem.py`** (Phase 5b) - **BUILT** (`Migrate/`). Update the **original AGOL item** once its Enterprise counterpart exists: append tags `Migrated` + `Migrated to Portal`, append `ArcGIS Portal URL: <url>` to the description, add a comment with the same URL, and **capture the original's `content_status`** (for the authoritative propagation in Phase 8). Logs to file + writes the ledger; `DRY_RUN`.
5. **`DeprecateAndPropagateAuthoritative.py`** (Phase 8) - **BUILT** (`Migrate/`). After share-back: propagate Authoritative (if the original was) to the new AGOL by-reference item + the Enterprise Portal item, then **deprecate the original AGOL item**. Uses `Item.content_status` (settable in arcgis 2.4.1.1); refuses to deprecate unless a by-reference replacement id resolves; `DRY_RUN`. **Updated 2026-06-10:** (a) also appends **`New AGOL Item: <url>`** to the end of the original item's description (append-only/idempotent, pointing at the new by-reference AGOL item) before deprecating; (b) adds a **ledger GATE** (`REQUIRE_CLEAN_LEDGER`, default on): an item is only processed if its ledger row reached `REQUIRED_STATE_BEFORE_DEPRECATE` (`agol_updated`) **with no recorded error** -- automating the "only deprecate after Step 5 succeeded" check (still verify stored-cred access for a consumer separately).
6. **`ReassignMigratedItemOwners.py`** + **`owner_map.py`** (decision #12) - **BUILT** (`Migrate/`). `--target portal`: append `Created By: <Owner_Name>` to the Enterprise item + reassign its owner to the mapped `Portal_Owner` (fallback `rrgadmin`). `--target agol`: reassign the by-reference AGOL item to the original AGOL owner. Driven by `Migrate\Input\Owner_Map.csv`; `Item.reassign_to` (verified arcgis 2.4.1.1); `DRY_RUN`. **Folder replication (2026-06-08):** also replicates the SOURCE item's folder - resolves the source folder title (`owner_map.get_item_folder_title`, `ownerFolder` id -> title) and passes it as `target_folder` to `reassign_to` on BOTH targets, creating it under the new owner if missing (`owner_map.ensure_folder`); `COPY_SOURCE_FOLDER` toggles it. Mirrors the established `ChangeArcGISOwner.py` pattern.
7. **`credential_store.py`** (cross-cutting) - **BUILT** (`ArcGIS Admin` root). Reads the workflow logins (`agol`/`portal`/`GPUser`) from the **Windows Credential Manager** (win32cred/keyring) with an interactive **prompt fallback**; CLI to store/list/delete. Wired into the connect path of every migration script (except `PublishFromDBToFeatureService.py`, which keeps `.env`). See *Cross-cutting: credentials* under Section 5.

> **Cross-cutting helper - BUILT:** `migration_status_ledger.py` (`Migrate/`) provides `setup_logging()` (file + console) and the `MigrationLedger` CSV state-ledger. Every migration script must **log to file** (not just `print`) and **update the migration status ledger CSV** via this helper - see *Cross-cutting: logging & migration status ledger* under Section 5. (`migration_poc_step6_apply_symbology.py` was retrofitted onto it.)

---

## 3. Key concept: what transfers, and what does NOT

A REST `/query` copy ("route a") moves **geometry + attributes** only. The migration now stages via
**route (b) export-to-FGDB** (Phase 2), which carries far more, so this list splits into "now travels with
route (b)" vs "still handled explicitly":

**Now TRAVELS with route (b) export (proven 2026-06-12) -- no longer separate work:**

- **Attachments** - the `__ATTACH` table + binaries ride along with the feature class (and survive the
  reproject + SDE load + by-reference publish). (Route a dropped them entirely.)
- **Relationship classes** - incl. the attachment `__ATTACHREL`; carried by the export.
- **GlobalIDs** - the ORIGINAL managed GlobalIDs are preserved end to end (`preserveGlobalIds=True`).
- **Domains / subtypes** - carried natively by the FGDB export (verify).
- **Tables + multiple layers** - the export brings the whole item.

**Still handled explicitly (item/portal-level, not in the data):**

- **Symbology / renderer** - lives in the source layer's `drawingInfo` (`<service>/<layerId>?f=json`)
  and in the item **data** JSON (`layerDefinition.drawingInfo.renderer`, `popupInfo`). Captured by
  `GetAllArcGISServiceMetadata.py` as `_data.json`.
- **Pop-ups / field aliases / field visibility** - in the item data `popupInfo` / `fieldInfos`.
- **Spatial reference** - standardize to **WGS84 (wkid 4326)**; reproject during the local-staging copy
  (Phase 2) if the source differs (geometry-only; symbology field refs unaffected).

### Where symbology lives (and how to re-apply it)

Two different targets, two different REST operations - see
`docs/plan/AGOAssistant/how-ago-assistant-view-edit-json.md` Section 4 for the full comparison:

- **Service-level renderer (the published service itself):** push `drawingInfo` to each layer via
  `FeatureLayer.manager.update_definition({"drawingInfo": <block>})` - the Python wrapper around the
  REST [`updateDefinition`](https://developers.arcgis.com/rest/services-reference/enterprise/update-definition-feature-service/)
  admin operation (`{service-admin}/FeatureServer/{layerId}/updateDefinition`). Requires
  publisher/admin on the federated server. **Cannot set pop-ups.**
- **Item/web-map style (the portal item):** set the destination item's data via
  `item.update(data=json.dumps(item_data))` (the Update Item `text=` operation). This carries the
  item-level renderer **and** is the **only** place `popupInfo` / `fieldInfos` can live - pop-ups are
  not a service concept.
- For a **referenced** Enterprise service, do **both**: `updateDefinition` for the service renderer,
  item data for pop-ups + item-level style.
- **Field-name dependency (critical):** renderers reference field names (`renderer.field`,
  class-breaks/unique-value fields) and `popupInfo` references `fieldInfos`. Those fields must exist
  on the destination with the **same names**. Copying with `CopyFeatures`/`ExportFeatures` preserves
  field names, but watch for SQL Server reserved words, case, length (>128), and the OID/GlobalID
  fields. If a field is renamed, the captured renderer must be **remapped** before it is applied.

> **Starting point already built:** `docs/plan/AGOAssistant/update_item_data.py` copies symbology +
> pop-ups from a source (AGOL) `_data.json` to a target item and/or its service
> (`--apply item|service|both`), backs up the prior state, and remaps source->target layer ids
> (AGOL layer ids rarely match the new Enterprise service's ids). It is the pilot/building block for
> `ApplySymbology.py`; it does **not yet** remap field names.

---

## 4. Migration manifest (the driver)

One **row per destination layer/table**. Built from the metadata output (Phase 1), reviewed by hand.

| column                 | example                    | notes                                                                 |
| ---------------------- | -------------------------- | --------------------------------------------------------------------- |
| `item_id`            | `b2142be3...`            | source AGOL item                                                      |
| `service_url`        | `.../FeatureServer`      | source service root                                                   |
| `layer_id`           | `0`                      | sublayer/table id                                                     |
| `source_layer_name`  | `waterschap_v`           | for matching/symbology                                                |
| `dest_schema`        | `clim`                   | target schema (= owner)                                               |
| `dest_feature_class` | `Waterschap`             | destination FC/table name - see**naming rule** below            |
| `sde_connection`     | `T:\...\RRGOrg_clim.sde` | **connect as the schema owner** so data is owned by that schema |
| `is_table`           | `N`                      | layer vs table                                                        |
| `has_attachments`    | `Y`                      | from metadata                                                         |
| `relationship_ids`   | `0;1`                    | recreate after both ends land                                         |
| `data_json_file`     | `..._data.json`          | symbology source                                                      |
| `notes`              |                            | field renames, SR overrides, etc.                                     |

> Connect as the **schema owner** (e.g. `RRGOrg_clim.sde`), not `sde`, so the destination data is
> created in and owned by the intended schema (`RRGOrg.clim.*`).

**Destination feature-class naming rule** (resolved per row, requires a live existence check
against the target schema):

1. Use the item property **`name`** (from the item description / `_get.json`).
2. If `name` is empty **or** already exists in the target geodatabase, use the URL segment
   **after `/rest/services/` and before the last `/`** of the service `url`.
3. If that still exists, append an incremental suffix `_1`, `_2`, ... until the name is free.

---

## 5. Phased pipeline

### Phase 0 - Prerequisites

- `RRGOrg` geodatabase exists; schemas/users created (`CreateGDBUsers.py`) and `.sde` files made (`CreateSDEFilesBulk.py`).
- Run `GetAllArcGISServiceMetadata.py` (full mode) against AGOL to capture the inventory + `_data.json` symbology for the 38 items.

### Phase 1 - Build the manifest

- `BuildMigrationManifest.py` (new): read the metadata `relevant_items` + per-layer details, expand each of the 38 services into per-layer/table rows, pre-fill schema/connection from your mapping, emit the CSV.
- **Human review** of the CSV: confirm dest names, schemas, field-rename notes.

### Phase 2 - Copy data (features + tables + attachments) - **stage local, reproject to WGS84, then load SDE**

Data flow: **AGOL -> local file GDB (staging) -> reproject to WGS84 -> SDE.** (Refined 2026-06-04.)

> **ROUTE (b) is now the default staging method (decision + proof 2026-06-12).** `migration_poc_step3_stage_local.py`
> sets **`EXPORT_MODE="always"`**: instead of the REST `copyData` engine (route a), it stages each item via an
> **Esri "Export to File Geodatabase"** (`export_item_to_fgdb.py`). This is the faithful path -- it brings ALL
> layers + tables + `__ATTACH` + `__ATTACHREL` relationship classes + the **ORIGINAL GlobalIDs**, and is NOT
> bounded by `maxRecordCount`. step3 then reprojects the staged FC to WGS84 with **`arcpy.env.preserveGlobalIds=True`**
> (`Project` for non-4326; `ExportFeatures` for already-4326 -- both proven to carry the attachment/relationship
> bundle), and **step3c loads FGDB -> SDE with `preserveGlobalIds=True`** (proven full fidelity into SQL Server;
> `arcpy.management.Copy` FGDB->SDE FAILED and is not used). **On any export-path failure step3 falls back to the
> copyData route below**, so simple/non-exportable items still work. The 2a/2b/2c notes below describe that
> copyData fallback (route a); they remain accurate for it. **Known limitation:** export is per-ITEM (whole
> service); the per-layer pipeline currently re-exports the whole item per layer row -- optimize to
> "export once, load each layer/table" in the multi-layer/manifest phase.

**SR-based routing (route a / copyData fallback):** local staging exists mainly to reproject. A source **already in WGS84 (4326)**
*could* skip the FGDB intermediate and copy **AGOL -> SDE in one pass** (the Step 3c "direct" path) - a
real saving across ~6500 items - but that path writes straight into SDE via the most fragile branch of
`copyFeaturesFromService.copyData` (multi-page SDE insert; per-page errors are swallowed). So
`migration_poc_step3_stage_local.py` now sets **`FORCE_LOCAL_STAGING = True`**: EVERY source is staged to
a local FGDB and loaded through the reliable Step 3c LOAD path (`ExportFeatures`) with a verifiable count
at each hop. Set it `False` to re-enable the direct-to-SDE path for 4326 sources (saves one copy, less
safe). 4326 sources that stage still skip the reproject (pass-through copy).

> **Chunking is mandatory either way.** AGOL caps every query at `maxRecordCount` (e.g. 2000), so a
> single `CopyFeatures(service_url, ...)` would silently return only the first page. The paged
> `copyData()` OID-window loop (`OID > y AND OID <= x`) is required regardless of destination or SR -
> "AGOL -> SDE in one pass" means **paged copy with the SDE FC as output**, not a single un-paged copy.
> `copyData()` already supports an SDE output workspace.

- **2a. Copy AGOL -> local FGDB (staging).** Land the layer/table in a local file geodatabase under
  `T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\Migrate`
  (one staging `.gdb`, e.g. `Migrate\<item_id>.gdb` or a shared `Migrate.gdb`). Doing the copy locally
  first isolates AGOL paging/429 handling and reprojection from the SDE write.
- **2b. Standardize spatial reference to WGS84.** Target SR is **GCS WGS 1984 (wkid 4326)**. If the source
  is Web Mercator (102100/3857) or anything else, **reproject to 4326** (`arcpy.management.Project`, or set
  `arcpy.env.outputCoordinateSystem` on the copy). Reprojection is geometry-only - it does **not** affect
  renderer/pop-up field references, so symbology is unaffected.
- **2c. Load local FGDB -> SDE.** Copy the WGS84 staged FC into the target schema (`RRGOrg_<schema>.sde`,
  connect as the schema owner) -> `RRGOrg.<schema>.<dest_feature_class>`.
- **PER-ITEM staging gdb (scale):** stage into `Migrate\<item_id>.gdb`, **not** one shared `Migrate.gdb`
  - the migration eventually covers **~6500 items**, far beyond what a single FGDB handles. Each per-item
    gdb is **transient**: delete it after the Step 3c SDE load succeeds. The staging script also drops the
    source-SR intermediate (`<dest>_src`) once the WGS84 reproject is verified, keeping each gdb lean.
- **POC implementation:** `docs/plan/completed/migration_poc_step3_stage_local.py` (BUILT) does 2a+2b for one
  layer - reuses `copyFeaturesFromService.copyData()` (the simple, importable paging engine) to stage
  into `Migrate\<item_id>.gdb`, then `arcpy.management.Project` to 4326. 2c (FGDB->SDE) is still to wire up.
- Driver today for AGOL->SDE: `CopyFeaturesToGDB.py` (heavier arcgis-API driver, Extract-capability
  toggle, tables, domains; CSV: `feature_service_url, database_owner_name, feature_name, workspace_full_path`). It copies AGOL->SDE **directly in source SR** - no local stage / reproject.
  Recommendation: keep the small POC staging script separate rather than merging the two copy scripts;
  fold the staging+reproject pattern into the production driver later.
- Ensure: GlobalIDs added where attachments/relationships are needed (`AddGlobalIDs`); `maintainAttachments`/`transferDomains` on.
- Handle AGOL **rate limiting (429)** with backoff (gap noted in existing chunk loop).
- **Future enhancement:** copy ALL layers, tables, attachments, and relationships per service (the POC item has a single layer with none).

### Phase 3 - Relationships & attachments (now carried by route (b) - PROVEN)

> **SUPERSEDED 2026-06-12 -> route (b).** The original plan (a SEPARATE attachment pass via
> `copy_attachments.py`, matching source->dest on GlobalID) was driven by `copyData` dropping attachments +
> GlobalIDs. With **route (b) export-to-FGDB staging (Phase 2)** the `__ATTACH` table, the `__ATTACHREL`
> relationship class, the attachment binaries, and the ORIGINAL GlobalIDs all travel WITH the feature class
> and survive the SDE load (`preserveGlobalIds=True`) and the by-reference publish. **So there is NO separate
> attachment/relationship stage on the SDE migration path.** Proven end to end on `196d4eb4...` -- see the
> OUTCOME section of `docs/attachments-copy-plan.md`.

**Geodatabase-attachment model (still the chosen model).** Attachments land as geodatabase attachments
(binaries in the `<fc>__ATTACH` table, served through the feature service's attachment REST endpoints), NOT
files in a web directory -- the secured feature service enforces the token natively (a static `webdocs`
directory has no clean token-security story); see `docs/attachments-copy-plan.md` Section 4-5 for that analysis.

**Verified at publish (2026-06-12):** the **referenced** Enterprise FeatureServer (MAP_IMAGE + Feature Access,
decision #9) exposes `queryAttachments` (`supportsQueryAttachments=True`) and serves the blobs --
`queryAttachments?objectIds=...` and the per-feature `/{oid}/attachments` endpoint both returned all
attachments, and a blob downloaded (HTTP 200, bytes match). The AGOL by-reference item points at the same
FeatureServer URL, so it inherits the same access. **Quirk:** `queryAttachments?where=1=1` returns 0 on this
build -- use `objectIds`/`globalIds` or the per-feature endpoint (what pop-ups/web maps use).

**`copy_attachments.py`** remains a BUILT, reusable standalone tool (service->service attachment copy, or a
fallback if an item cannot be exported), but is **not on the SDE migration path**. Its GlobalID-matching
mechanics + the storage-model analysis live in `docs/attachments-copy-plan.md`.

**Relationships:** route (b) export carries the source's relationship classes (incl. the attachment
`__ATTACHREL`) into the FGDB, and they survive the SDE load with GlobalIDs preserved -- so most relationships
need NO separate recreation. `CreateRelationshipsInGDB.py` (new, still TODO) is only needed for any relationship
NOT carried by the export (e.g. a relationship to a dataset migrated separately): `arcpy.management.CreateRelationshipClass`
per captured definition (origin/destination, origin PK + destination FK, cardinality, simple/composite, labels;
*message direction isn't in REST - default it*), run after both ends are in SDE with GlobalIDs preserved.

### Phase 4 - Apply symbology  <- the hard part

- Pilot tool already built: `docs/plan/AGOAssistant/update_item_data.py`. Inputs: source `_data.json`
  + target item id. Modes: `--apply service` (drawingInfo -> `updateDefinition`), `--apply item`
    (symbology + `popupInfo` -> item data), `--apply both`. Backs up prior state; remaps source->target
    **layer ids** via inference or `--layer-map`.
- `ApplySymbology.py` (new) generalizes the pilot for batch: drive from the manifest, and add the
  field-name validation/remap the pilot lacks.
- Steps per destination layer:
  1. Pull `drawingInfo`/`renderer` (+ `labelingInfo`, `transparency`) and `popupInfo`/`fieldInfos` from the captured JSON.
  2. **Validate/remap field references** against the destination schema (fail loudly if a referenced field is missing).
  3. `FeatureLayer.manager.update_definition({"drawingInfo": <renderer block>})`  (service renderer; no pop-ups).
  4. Update the destination **item data** with `popupInfo`/`fieldInfos` (+ item-level renderer) via `item.update(data=...)`  (pop-ups live ONLY here).
  5. Copy item-level properties so the target matches the source: default view (`extent`), tags, and
     **Terms of Use** (`licenseInfo`) via `item.update(item_properties=...)`. Step 6 reads `licenseInfo`
     from the cached `_description.json` (live-AGOL fallback) and applies it to the Feature Layer, the Map
     Image Layer, and the AGOL item (Phase 8 re-apply) regardless of the tags toggle. *(Title/Summary/
     Description/Credits are set at publish from the CSV - Phase 5.)*
- Pilot one layer with `update_item_data.py --apply both` and confirm the renderer + pop-ups match the source before batching.
- **Map Image Layer sync (decision #9):** apply the **same** renderer + pop-ups + default view to the backing
  **Map Image Layer** item so the two items match. Find it via Step 6's `find_map_image_item()`: check item
  relationships first (authoritative when the publish registered them), then derive the sibling `MapServer`
  url (`FeatureServer`->`MapServer`) and match it against candidates found by **BOTH the item title AND the
  url-derived service name** - a name-only search misses a Map Service whose item title differs from its
  service name (e.g. item "Guayule Historic (v.1)" backed by service `Guayule_Current_V1`). **Title-aware
  search backported into Step 6 on 2026-06-16**, kept in sync with `find_backing_map_services()` (the
  coverage-share + reassign scripts). Pop-ups + extent sync unconditionally via that item's `/data` +
  `extent`; the renderer override only redraws the image if `MapServer?f=json` reports
  `supportsDynamicLayers: true` (else the image keeps Pro-baked symbology - see decision #9 / risks).

### Phase 4b - Item thumbnails

> **REVISED 2026-06-10 - COPY an existing thumbnail first, regenerate only as a fallback.** Re-rendering on
> the server is now the FALLBACK, not the default. Both migrated items reuse an existing, already-correct
> thumbnail (`RegenerateItemThumbnails.py` copy modes; `copy_thumbnail()` is cross-portal safe):
>
> - **Enterprise item** (`thumb_copy_portal` stage / `--copy-agol-to-portal`): copy the **ORIGINAL AGOL
>   item's** thumbnail onto the Enterprise item (+ Map Image sibling). If the AGOL item has **no** thumbnail,
>   FALL BACK to regenerating on the server (the render path below). Because the Enterprise symbology was
>   copied from that same AGOL item, the AGOL thumbnail already matches.
> - **AGOL by-reference item** (`thumb_copy_agol` stage / `--copy-portal-to-agol`, Phase 8): copy the
>   **Enterprise Portal item's** thumbnail onto the new AGOL item (no AGOL re-render).
> - Net flow: AGOL original -> Enterprise (copy) -> AGOL by-ref (copy). A server render happens only when the
>   AGOL original lacks a thumbnail. Consequently the publish step and the standalone symbology step now run
>   with **`regen_thumbnail=False` / `--no-thumbnail`** (the copy stages own the thumbnail), and Step 6's
>   integrated thumbnail regeneration is suppressed in the pipeline.

The server-render path (still used as the Enterprise fallback, and historically for both items):
`RegenerateItemThumbnails.py` re-renders headlessly so the portal item card reflects the applied symbology:

- Reads each layer's `layerDefinition.drawingInfo` from the item `/data`, builds a Web Map JSON (portal default
  basemap + one operational layer per feature layer, with a **token** so the print service can read the secured
  layer and the **item `/data` renderer** so it draws with the corrected symbology), POSTs to the portal **print
  service** (Export Web Map Task, `MAP_ONLY`) -> PNG, then `item.update(thumbnail=...)`.
- Renders the **item-level** renderer, not the service renderer - essential for by-reference services whose
  service renderer stays `simple` (rendering that alone yields a one-color thumbnail). `minScale`/`maxScale` are
  deliberately **not** injected so the layer always draws regardless of its visibility range.
- Uses **username/password** (needs a real token to pass per operational layer; a `GIS("pro")` session exposes
  none). `DRY_RUN=True` renders + saves the PNG locally without touching the item.
- **Dependency - default view first.** The thumbnail is framed to `item.extent`, so the item's **default view
  must already be set** (copied from the source item by Step 6's extent step) before this runs - otherwise the
  thumbnail is framed to the **world** extent. The script reads `item.extent` live, prints it, and **warns** if it
  has to fall back to the world extent (the signal that the default view was not applied first).
- Run the Enterprise thumbnail **after Phase 4** (after the default-view/extent copy) and the AGOL
  by-reference thumbnail **after Phase 8** - but via the COPY modes above, with this render only as the
  Enterprise fallback.
- **Map Image Layer (decision #9):** don't re-render it - the thumbnail is identical to the Feature Layer's
  (same data/symbology/extent), so **apply the same PNG** to the Map Image Layer item via
  `item.update(thumbnail=png)`. The `--copy-agol-to-portal` mode does this for the copied PNG too.

### Phase 5 - Publish referenced feature services (SQL -> Enterprise)

**`PublishFromDBToFeatureService.py` does this. RUN OK 2026-06-09 for BOTH POC items.** Its CSV-driven
main loop, per dataset: builds a temp project from `Input/BlankTemplateProject/BlankTemplateProject.aprx`,
adds the SDE FC as a layer, sets `useServiceLayerIDs=True`, then publishes a **referenced** service via the
**canonical federated path (REVISED 2026-06-09)**:
`getWebLayerSharingDraft(server_type="FEDERATED_SERVER", service_type="MAP_IMAGE", service_name=...)`, sets
`federatedServerUrl`, **`copyDataToServer=False`** (by reference -- RRGOrg is a registered data store),
`serverFolder`/`portalFolder`, summary/tags/description; exports the `.sddraft`; `finalize_sddraft()` then
**enables the FeatureServer extension (Feature Access)** and sets the instance `Provider` (`DMaps`=shared);
then `StageService_server` -> `UploadServiceDefinition_server` (to the federated server URL) ->
`validate_and_update_portal_item`. This yields the **MapServer + FeatureServer pair** (decision #9).

> **Why MAP_IMAGE, not FEATURE (key finding 2026-06-09):** arcpy's `getWebLayerSharingDraft` validation
> allows `service_type="FEATURE"` only with `HOSTING_SERVER`/`MY_HOSTED_SERVICES`, **never with
> `FEDERATED_SERVER`**. A referenced feature service on a federated server must therefore be published as a
> **MAP_IMAGE** service with Feature Access on. The original `HOSTING_SERVER` + `offline` +
> connection-string DOM injection (`update_sddraft_dom`/`add_databases_to_sddraft_dom`) was a workaround that
> failed at upload with **ERROR 002901 "Unable to check if service exists"** (a HOSTING feature SD pushed to a
> federated server folder is not a valid publish target -- not a folder, URL, or permissions problem; the
> server folder created fine and the admin was reachable). The new path lets arcpy generate a correct
> by-reference SD natively, so `update_sddraft_dom`/`add_databases_to_sddraft_dom` are **retired** (replaced by
> the lean `finalize_sddraft`). Verified by-reference via the service `manifest.xml`
> (`<ByReference>true</ByReference>`); the FeatureServer is the Feature Access extension of the **same**
> MapServer (one service definition under `arcgisinput\<folder>\<name>.MapServer`, so by-reference covers both).
> Proven first with the standalone `test_federated_publish.py`; `verify_referenced.py` checks the result.

Use it for the POC rather than building new. Inputs (CLI args / `.env` / per-row CSV; precedence:
per-row CSV > CLI > `.env` > prompt). **Auth:** portal login via `credential_store` (key `portal` ->
`nbs_arcgis_admin`), prompt fallback. **Folders never prompt** (per-row / map-driven).

- **Publish CSV** columns: `feature_name,item_id,title,summary,description,tags,credits` (+ optional
  `instance,portal_groups,categories,agol_owner_folder`). The **SDE connection / database / schema come from
  the master manifest `Migrate\Input\ItemsToMigratePhase1.csv`** (helper `items_manifest.py`), keyed by
  `item_id` - NOT duplicated in the publish CSV (explicit `workspace_full_path`/`database_name`/
  `database_owner` columns still override). *(Different CSV from the Phase-2 copy CSV.)*
- **Item metadata + folders set at publish:** the CSV `title`/`summary`/`description`/`credits` are written
  into the SD draft `ItemInfo` (-> the Enterprise item's Title/Summary/Description/Credits). The DOM editor
  also sets the **portal item folder** (`PortalFolderName`) and the **server REST folder** (`ServiceFolder`),
  plus `AllowCopy=false`, `Provider`, `ServiceTitle`, `IncludeDataInSDFile=false`. **Folder model -
  map-driven (2026-06-09):** a service is published **as rrgadmin into the portal ROOT** (no content folder)
  and into the mapped **`Portal_Server_Folder`** (server REST folder). Folders come from
  **`Migrate\Input\Folder_Map.csv`** (helper **`folder_map.py`**, BUILT): each source AGOL `owner_folder`
  maps to a `Portal_Server_Folder` and a `Portal_Owner_User_Folder` (a `ROOT` sentinel = root). The publish
  CSV carries `agol_owner_folder` per row; the script resolves the **server** folder from the map (e.g. ws
  `MAXENT` + crop `MaxEnt` both -> server **`MaxEnt`**), and `portal_folder` is left blank (ROOT). An explicit
  `server_folder` column overrides the map. `ensure_portal_folder()` creates the (publishing user's) content
  folder only if a non-root `portal_folder` is given. **Caveats:** (a) the per-item **`Portal_Owner_User_Folder`**
  (also from the map) is applied **after publish at the Phase-8 reassign** (decision #12), together with the
  owner change (`Owner_Map.csv`); and (b) **Terms of Use (`licenseInfo`) is NOT set at publish** - it is
  applied in Step 6 (Phase 4).
- Per-row workspace/db/schema -> fully-qualified `<database>.<owner>.<feature_name>` (e.g.
  `RRGOrg.ws.Change_in_SW_Supply_by_2030`), resolved from `ItemsToMigratePhase1.csv` (above).
- **`REPOSITORY_ID` no longer injected (obsolete 2026-06-09).** The old workaround needed a RepositoryID
  from a prior manifest because it hand-built the `Databases` block. The new `FEDERATED_SERVER`/`MAP_IMAGE` +
  `copyDataToServer=False` path lets **arcpy generate the correct by-reference SD (with the right
  RepositoryID) natively** from the registered RRGOrg data store - so the chicken-and-egg RepositoryID
  bootstrap is gone. (`--repository-id`/`--server-manager-db` remain accepted but are no longer required.)
- `FEDERATED_SERVER_URL` (the upload `in_server`), `PORTAL_URL`, `PORTAL_USERNAME`.

**Prerequisite - DONE:** `RRGOrg` (`clim`/`ws`/`sde`/`land`/`crop`) is already **registered as a data
store** with the federated server, so `StageService` will not hit the `24011` "not registered" abort.
(NOTE for reference: `Scratch/RegisterWithGeodatabase.py` is *not* datastore registration - it registers
a table/view *with the geodatabase*. Datastore registration is Pro "Manage Registered Data Stores" /
`arcpy.management.AddDataStoreItem`.)

**Caveats to verify during the POC (carried as Phase-5 risks):**

1. **`HOSTING_SERVER` vs `FEDERATED_SERVER` - RESOLVED 2026-06-09.** The script now publishes via
   `FEDERATED_SERVER` + `MAP_IMAGE` + `copyDataToServer=False` (referenced) with Feature Access enabled - NOT
   the old `HOSTING_SERVER` + `offline` workaround (which failed with ERROR 002901). Confirmed referenced (data
   stays in RRGOrg SQL) via the service `manifest.xml` `<ByReference>true</ByReference>`. See the Phase 5
   "Why MAP_IMAGE" note above.
2. **Provider value - RESOLVED 2026-06-09.** `update_sddraft_dom` previously set the shared-instance
   `Provider` to `ArcObjectsRasterRendering` (a raster value, wrong for feature services), which forced
   the early POC to use a dedicated instance. It now sets **`DMaps`** for shared (the correct map/feature
   shared-instance pool provider; Esri: shared-pool services report `provider=DMaps`, min/max instances
   `0`) and keeps `ArcObjects11` for dedicated. **The whole migration workflow publishes SHARED** -
   `instance=shared` for every row in `publish_input_poc.csv`.
3. The non-CSV "publish all from workspace" branch still calls `ListRasters()` (raster leftover) - avoid it; **always drive from the CSV.**
4. **Basemap staging failure - FIXED 2026-06-12 (local repo copy; redeploy to nbs-app2 pending).** Staging
   failed with Analyzer ERROR 24078 *"Layer's data source is not supported: Topographic"* because `aprx.createMap()`
   (the `BlankTemplateProject` no longer ships a map) injects a default **Topographic basemap** that cannot stage
   into a referenced service. Fix: after resolving the temp map, remove any `lyr.isBasemapLayer` layers before
   staging. Surfaced while publishing the attachments POC (`POC_Attach_ExportFeat`).
5. **`ensure_portal_folder()` bug - FIXED 2026-06-12 (local repo copy; redeploy to nbs-app2 pending).** It
   raised `'Folder' object has no attribute 'get'` because arcgis 2.4.1.1 returns `Folder` OBJECTS (`.name`),
   not dicts. Fix: a version-tolerant `_folder_display_name()` for the existence check + create via the
   non-deprecated `gis.content.folders.create()` (fallback to the deprecated `create_folder()`). Validated
   against the live portal (existing-folder path no longer crashes; fresh-folder create works). So the portal
   item folder is now set at publish -- the post-publish `item.move()` workaround is no longer required.

**Attachments through the referenced service - VERIFIED 2026-06-12** (publishing the route-(b) SDE FC
`POC_Attach_ExportFeat`): the referenced FeatureServer serves `queryAttachments` + the attachment blobs (see
Phase 3). So a published referenced service carries attachments end to end.

After publish, the Phase 4 symbology apply runs against the **published** item. **Integrated 2026-06-08:**
`PublishFromDBToFeatureService.py` now imports `apply_symbology()` from `migration_poc_step6_apply_symbology.py`
and calls it **best-effort at the end of each publish loop**, so a successful publish also applies the source
item's renderer + pop-ups + visibility range + default view to the new Enterprise item and syncs its Map Image
Layer - in one run. **(REVISED 2026-06-10: the publish call now passes `regen_thumbnail=False`, so it no
longer renders the Enterprise thumbnail - the `thumb_copy_portal` stage sets it from the AGOL original, with
a server render only as fallback; see Phase 4b.)** It resolves the source AGOL item id via the migration-status-ledger join
(`dest_feature_class == feature_name`, so Step 1 + the copy phase must have run for that item) and the new
Enterprise item id from the publish. A symbology failure never fails the publish. The standalone Step 6 is
still used for the **AGOL by-reference** item in Phase 8 (and as a manual fallback). *(Ledger path: the
publish join reads the canonical ledger at `Migrate\Output\migration_status_ledger.csv`
(`migration_status_ledger.default_ledger_path()`), the same file every phase writes - the early-POC
`poc_output\` location was retired when the ledger was centralized.)*

**Tags on the Enterprise item (decision #10).** The Enterprise item(s) get **tags identical to the source AGOL
item plus two migration defaults**: `Migrated from AGOL` and `Migrated`. Source tags come from the cached AGOL
`_description.json` (`tags`), with a live-AGOL fallback (same source as the default extent). Applied to **both**
the Feature Service and the synced Map Image Layer item (decision #9). These migration defaults are
**Enterprise-only** - they must NOT propagate to the AGOL by-reference item in Phase 8 (see there). *(POC: set in
Step 6 via `item.update(item_properties={"tags": ...})`, since it already reads the source description; production
may instead pre-fill the publish CSV `tags` column.)*

### Phase 5b - Update the SOURCE AGOL item (pointer back to Portal)

Once the Enterprise item exists (Phase 5), update the **original AGOL item** so consumers are pointed at the
new Portal item. New script `UpdateSourceAGOLItem.py` (item edits via `item.update`; comment via
`item.add_comment`):

- **Tags:** append **`Migrated`** and **`Migrated to Portal`** to the source item's existing tags
  (`item.update(item_properties={"tags": [...]})`). Idempotent - don't duplicate if already present.
  *(Distinct from the Enterprise-item tags in decision #10, which are `Migrated from AGOL` + `Migrated`.)*
- **Description:** append a line to the **end** of the source item's `description`:
  `ArcGIS Portal URL: <enterprise portal item url>`
  (the Portal item page, `https://maps.rrgnbs.com/arcgisportal/home/item.html?id=<enterprise_item_id>`).
  Append-only (preserve the existing description); guard against re-appending on re-run.
- **Comment:** add an item comment with the same `ArcGIS Portal URL: <url>` text (`item.add_comment(text)`).
  Requires org **comments enabled** + permission - **skip-with-warning** if disabled (don't fail the run).
- **Capture authoritative status now:** read and record `item.content_status` to the status ledger so it can
  be propagated to the Portal + by-reference items **before** the source is deprecated in Phase 8 (decision #11).

### Phase 6 - Validation / QA

- Source vs destination **row counts** per layer/table; geometry sanity; **attachment counts**; relationship existence; spatial reference; field parity (names/types/aliases).
- **Source changed after the copy (added 2026-10-19):** when counts/values differ because the AGOL source kept
  being edited (e.g. RRG_HoldingsAssets), run `python ValidateMigratedItems.py --item <id> --diff`. It diffs every
  SDE dataset against the LIVE source row by row on GlobalID (attributes only) and writes
  `Migrate\Output\validate_diff_<item_id>_<stamp>.csv` (`change` = ONLY_IN_SOURCE / ONLY_IN_DATABASE / EDITED, one
  row per edited field with both values), logs a per-dataset summary, and adds a `validate_diff` NOTE to the ledger
  row (non-blocking). Use it to decide which side is authoritative before any reload. Needs a GlobalID on both
  sides (items copied by the old REST path have none). A constant whole-hour offset on every date is a time-zone
  difference, not an edit.
- Symbology: visual compare; confirm renderer `field` resolves.
- Re-run `GetAllArcGISServiceMetadata.py` against the **Enterprise** portal and diff against the AGOL inventory.

### Phase 8 - Share the Enterprise item back to AGOL (by reference, stored credentials)

Final step of the round-trip. Use `AddItemWithStoredCredentials.py`:

- It logs into **both** the Enterprise portal and AGOL, then for each Enterprise item calls
  `agol_gis.content.add(data=<enterprise service url>, item_properties={... serviceUsername, servicePassword, token})`
  to create an AGOL item that **references** the Enterprise service, with **stored credentials** so AGOL
  users reach the secured service without their own portal login.
- **Tags on the new AGOL item (decision #10):** tags **identical to the original AGOL item plus** `by reference`
  and `stored credentials`. Because the script copies the **Enterprise** item's tags, and those now carry the
  `Migrated from AGOL` / `Migrated` defaults (Phase 5), it **strips those two migration defaults** before adding
  the by-reference pair - so the AGOL item ends up with the original tags + `by reference` + `stored credentials`,
  not the Enterprise-only migration tags.
- **Share back to AGOL: Feature Service only, not the Map Image Layer (decision #10).** Only the **Feature
  Service** (Feature Layer) is shared **back to AGOL** as a by-reference item - the Map Image Layer (Map
  Service) is **not** (it stays Enterprise-side; for its group-share + Portal reassign see decision #9).
  Enforcement (revised - the "Coverage Share" group now contains BOTH items, decision #9, so the group can no
  longer be relied on to exclude the Map Service): **`AddItemWithStoredCredentials.py` drives its share-back
  work list off the LEDGER's Enterprise Feature Service item ids** (`ledger_enterprise_item_ids()` - one
  Enterprise item per migrated source item), so the backing Map Service is never in the work list. (Earlier
  drafts said the group held only the Feature Service and that the share-back script filtered `items_to_add`
  to `Feature Service` type; both are superseded - the ledger-driven work list is the real guard.)
- **Portal item owner + "Created By" (decision #12).** After the Enterprise item is in the **Coverage Share**
  group, on that Portal item: (a) append `Created By: <Owner_Name>` to the **end of its description** (the
  friendly name from `Migrate\Input\Owner_Map.csv`, append-only/idempotent); and (b) **reassign its owner** to the
  `Portal_Owner` mapped from the source `AGOL_Owner` - **falling back to `rrgadmin`** when the mapping is
  blank/missing or the mapped user can't own items (no `portal:user:createItem` / Viewer). Run as an **admin**.
  Implemented in **`ReassignMigratedItemOwners.py --target portal`** (BUILT; uses `owner_map.py`).
- For the POC, set `portal_item_ids_to_add = ['<Enterprise item id from Phase 5>']` (otherwise it pulls
  the "Coverage Share" portal group). Skips `esri`/`esri_livingatlas`; appends `" - NBS"` to `rrgadmin`-owned titles; skips if the AGOL title already exists.
- **Stored-credentials account:** use a dedicated low-privilege portal account (script defaults to `GPUser`),
  not an admin - its credentials are embedded in the AGOL item.
- **Symbology on the AGOL item - renderer does NOT flow automatically (REVISED 2026-06-08, per decision #2).**
  Earlier this plan assumed the service renderer (set via `updateDefinition`) flowed through the referenced
  service. The POC proved `updateDefinition` does **not** work for a by-reference service - its service renderer
  stays `simple` (blank). The new AGOL item is a fresh portal item with **default `/data`**, so **renderer +
  pop-ups + min/max (visibility range) + default view all live in the item `/data`/properties and must be
  re-applied to the AGOL item**, exactly as on the Enterprise item. Run `migration_poc_step6_apply_symbology.py`
  with the **`--agol` preset flag** (added 2026-06-10) -- a single switch that sets `TARGET_PORTAL_URL`=AGOL,
  `APPLY="item"`, `APPLY_TAGS=False`, `SYNC_MAP_IMAGE_LAYER=False` so **no CONFIG edits are needed** for the
  AGOL pass. It's a superset of `update_item_data.py --apply item` (which carries renderer/pop-ups but not
  min/max or default view). (Granular overrides: `--apply`, `--no-tags`, `--no-map-sibling`, `--no-thumbnail`.)
  Order: Phase 5 publish -> Phase 4 symbology (Enterprise item) -> Phase 4b thumbnail (Enterprise item) -> Phase 8
  add AGOL item -> Phase 4 re-apply (AGOL item) -> Phase 4b thumbnail (AGOL item).
- **Thumbnail (REVISED 2026-06-10):** the by-reference AGOL item is created with a generic thumbnail. Rather
  than re-render it on AGOL, **copy the Enterprise Portal item's thumbnail onto the AGOL item** -- they are
  identical (same data/symbology/extent), and the Portal thumbnail was already rendered correctly at
  `portal_updated`. Run `RegenerateItemThumbnails.py --copy-portal-to-agol` (ledger-driven: for each row,
  Enterprise `enterprise_item_id` thumbnail -> AGOL `agol_byref_item_id`). The AGOL symbology re-apply is
  therefore run as `migration_poc_step6_apply_symbology.py --agol --no-thumbnail` (symbology only); the copy
  step supplies the thumbnail. (Both stages are wired in `run_migration_pipeline.py` as `symbology_agol` ->
  `thumb_copy_agol`.)
- **AGOL item owner + group (decision #12).** After the by-reference AGOL item is created (and verified),
  **reassign its owner** to the **original AGOL item's owner** (`AGOL_Owner`) **and that owner's folder** via
  `item.reassign_to(owner, target_folder=...)`, using an **AGOL admin** login (the stored-cred `GPUser` is the
  embedded service account, not the login account). Defensive fallback to `rrgadmin` if that owner doesn't
  resolve / can't own. **Then share the item to the org group(s)** in `AGOL_SHARE_GROUPS` (default **"RRG
  Nature Based Solutions Organization (Internal)"**) - owner first, then group (added 2026-06-10). Do this
  **before** deprecating the source. Implemented in **`ReassignMigratedItemOwners.py --target agol`** (BUILT;
  pass `--byref <id>` or read from the ledger).
- **Authoritative propagation + deprecate the source (decision #11).** `DeprecateAndPropagateAuthoritative.py`,
  after the by-reference AGOL item exists and is verified:

  1. If the **original AGOL item** was Authoritative (`content_status` in `org_authoritative` /
     `public_authoritative`, captured in Phase 5b), set the **same** authoritative status on **both** the new
     **AGOL by-reference item** and the **Enterprise Portal item**.
  2. **Then** mark the **original AGOL item** as **deprecated** (`content_status = "deprecated"`).

  - **Order matters:** `contentStatus` is single-valued, so deprecating the source clears its authoritative flag
    - capture + propagate Authoritative **first**, deprecate **last**.
  - Marking authoritative/deprecated uses the REST `setContentStatus` op
    (`status` in {`org_authoritative`,`public_authoritative`,`deprecated`,``}); the arcgis Python API surfaces
    `Item.content_status` (**verify the set-mechanism against the installed arcgis version** during the POC).
  - **Caution:** deprecate the source only **after** the by-reference item is confirmed working (stored-cred
    access verified) so consumers have a live replacement before the original is flagged.

### Phase 7 - Pilot, then batch

- Run the whole pipeline on **1-2 representative services first** (one single-layer like `waterschap_v`, one multi-layer), validate the **symbology round-trip end-to-end**, then process the remaining 36.

---

### Cross-cutting: logging & migration status ledger

Applies to **every** migration script (the new ones and the existing POC/admin scripts).

**Logging to file (required).** Scripts must **log to a file**, not just `print()`. The shared helper
`migration_status_ledger.py` provides `setup_logging(__file__)` -> a `logging.Logger` that writes a timestamped
file under `<script_dir>/Output` **and** echoes to the console; scripts define a thin `log_message(msg, level)`
over it. **DONE:** `migration_poc_step6_apply_symbology.py` was retrofitted (all `print` -> file+console log);
`UpdateSourceAGOLItem.py` and `DeprecateAndPropagateAuthoritative.py` use it from the start. (The older
`AddItemWithStoredCredentials.py` / `RegenerateItemThumbnails.py` already log to file via their own pattern.)

**Migration status ledger (CSV, required).** A single source-of-truth CSV tracking each item through the
pipeline, **one row per source item** (per-layer copy detail stays in the manifest). Each phase updates it
**idempotently**: read -> update the row keyed by `item_id` -> write. Suggested columns:

| column                     | example                                           | notes                                    |
| -------------------------- | ------------------------------------------------- | ---------------------------------------- |
| `item_id`                | `4d6aff...`                                     | source AGOL item (key)                   |
| `title`                  | `Change in SW Supply by 2030`                   |                                          |
| `source_service_url`     | `.../Change_in_SW_Supply_by_2030/FeatureServer` |                                          |
| `dest_database`          | `RRGOrg`                                        |                                          |
| `dest_schema`            | `ws`                                            | `clim`/`crop`/`land`/`ws`        |
| `dest_feature_class`     | `Change_in_SW_Supply_by_2030`                   |                                          |
| `enterprise_item_id`     | `6b887c6b...`                                   | from Phase 5                             |
| `enterprise_service_url` | `.../WS_Change.../FeatureServer`                |                                          |
| `agol_byref_item_id`     |                                                   | from Phase 8                             |
| `state`                  | `published_to_portal`                           | pipeline milestone - see below           |
| `was_authoritative`      | `org_authoritative`                             | captured in Phase 5b, before deprecation |
| `last_updated`           | `2026-06-08T...`                                |                                          |
| `notes` / `error`      |                                                   |                                          |

`state` progression (the milestone the item has reached):
`copied_local` -> `copied_to_gdb` -> `published_to_portal` -> `portal_updated` (symbology/pop-ups/thumbnail) ->
`source_updated` (tags/desc/comment, Phase 5b) -> `shared_to_agol` -> `agol_updated` ->
`authoritative_propagated` -> `source_deprecated`.

> **BUILT:** `migration_status_ledger.py` implements exactly these columns + states as `MigrationLedger`
> (`set_state`/`update`/`save`, idempotent upsert keyed by `item_id`, forward-only warning on regression).
> The canonical ledger is `Migrate\Output\migration_status_ledger.csv` (`default_ledger_path()`; the
> early-POC `poc_output\` copy was retired when the ledger was centralized; override with env
> `MIGRATION_LEDGER_PATH` or `set_ledger_path()`). Cross-process writes are serialized behind a sidecar
> `.lock` file (reload-under-lock), so the parallel batch driver's child processes can't clobber each other.
> Wired into: Step 3 stage-local
> (`copied_local`), Step 3c SDE load (`copied_to_gdb`), `PublishFromDBToFeatureService.py`
> (`published_to_portal`), Step 6 (`portal_updated`/`agol_updated`), Phase 5b (`source_updated`),
> and Phase 8 (`authoritative_propagated`/`source_deprecated`). **Join note:** the copy phase keys by
> source `item_id` and records `dest_feature_class`; the publish phase only knows the dest feature
> name, so it joins on `dest_feature_class == feature_name` (skips-with-warning if no copy row exists).
> The two Step 3 copy scripts were also converted from print-only to file+console logging.

> **Errors + retrying a failed row (2026-06-12):** any stage records a failure into the row's `error` column
> (timestamped + phase-tagged, via `record_error`), and the runners then **SKIP** that row until it is cleared
>
> - the batch driver's copy resume, `BuildPublishCSV`, and the deprecate gate all exclude errored rows by
>   design, so a bad copy/load/publish is never carried onward. Once the cause is fixed, clear it with
>   **`Migrate\clear_error.py <item_id>`** (`--all` for every errored row, `--phase <p>` for one phase's entries,
>   `--dry-run` to preview) and re-run the stage. (A stage that succeeds on re-run also clears its own phase tag.)

---

### Cross-cutting: credentials (Windows Credential Manager)

To let the workflow run unattended, logins are read from the **Windows Credential Manager** with an
interactive **prompt fallback** (unchanged behavior when nothing is stored). Helper: **`credential_store.py`**
(BUILT) - backend `win32cred` (preferred; one Generic entry holds username + password), else `keyring`
(WinVaultKeyring), else prompt-only.

Three logical credentials (Generic Credential Manager entries):

- **`agol`** (`nbs_agol_user`) -> your AGOL account (step3/3c copy, step6 AGOL re-apply, UpdateSourceAGOLItem,
  Reassign `--target agol`, Deprecate, AddItemWithStoredCredentials AGOL login, and the AGOL-targeted runs of
  RegenerateItemThumbnails / AddItemToCoverageShareGroup).
- **`portal`** (`nbs_arcgis_admin`) -> your ArcGIS Enterprise (Portal) admin account (PublishFromDBToFeatureService,
  step6 Enterprise, Reassign `--target portal`, Deprecate, compare_services, AddItemToCoverageShareGroup,
  RegenerateItemThumbnails Enterprise).
- **`GPUser`** (`nbs_arcgis_gpuser`) -> the low-priv portal account embedded as stored credentials
  (AddItemWithStoredCredentials Portal login + the `serviceUsername`/`servicePassword` written into the AGOL
  by-reference item).

> **Wired 2026-06-09:** every migration script's connect path now uses `credential_store` (key chosen by
> host: `agol` for `*.arcgis.com`, else `portal`) before any prompt. The two that still prompted -
> `AddItemToCoverageShareGroup.py` and `RegenerateItemThumbnails.py` - were wired this date (the latter keeps
> its Pro-session-with-token preference for the print service, and an explicit `PORTAL_PASSWORD` still wins).

**Populate once, then runs are unattended:**

```
python credential_store.py set agol
python credential_store.py set portal
python credential_store.py set GPUser
python credential_store.py list           # shows usernames only; never prints passwords
```

`resolve(key, label, default_username, allow_save)` is the function each script's connect path calls: stored
credential -> returned silently; otherwise prompt (with a y/N offer to save). **Auth precedence (revised
2026-06-08): try the stored/entered credentials FIRST; `GIS("pro")` is used only as a fallback if the
credentials don't work** (previously the scripts tried `GIS("pro")` first). Credentials persist for the
**current Windows user** only (`CRED_PERSIST_LOCAL_MACHINE`); they are NOT committed to the repo.
*(`PublishFromDBToFeatureService.py` - **wired 2026-06-09**: its `connect_to_portal()` now calls
`credential_store.resolve("portal", ...)` (the `nbs_arcgis_admin` entry) before prompting, so the Enterprise
publish login is taken from the Windows Credential Manager when stored; the rest of its config is still `.env`
/ CLI driven. The portal account must be a non-SSO publisher/admin.)*

---

## 6. Risks & mitigations

| Risk                                                             | Mitigation                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Renderer field missing/renamed on destination                    | Validate field refs in `ApplySymbology.py`; remap or fail loudly; preserve field names in copy.                                                                                                                                                                                                                                                                                                                                   |
| Attachments lost                                                 | Add GlobalIDs + EnableAttachments before/after copy; verify counts.                                                                                                                                                                                                                                                                                                                                                                 |
| Relationships not recreated                                      | Driven from captured metadata in Phase 3; require both ends present.                                                                                                                                                                                                                                                                                                                                                                |
| AGOL rate limits / token expiry on long runs                     | Backoff on 429; refresh token (also a known gap in the metadata script).                                                                                                                                                                                                                                                                                                                                                            |
| Multi-layer services under-enumerated                            | Manifest is per-layer/table, built from metadata `layer_count`/`table_count`.                                                                                                                                                                                                                                                                                                                                                   |
| Publish script "image-oriented" (myth)                           | `PublishFromDBToFeatureService.py` already publishes FEATURE services; only the comments are stale. Real risks below.                                                                                                                                                                                                                                                                                                             |
| Referenced vs hosted ambiguity (`HOSTING_SERVER`)              | Verify the published service is by-reference (data in SQL); if copied, switch `server_type` to `FEDERATED_SERVER`.                                                                                                                                                                                                                                                                                                              |
| sddraft `Provider` is raster value for shared instances        | **RESOLVED 2026-06-09:** `update_sddraft_dom` sets `DMaps` for shared (was `ArcObjectsRasterRendering`); the workflow publishes shared.                                                                                                                                                                                                                                                                                 |
| SDE not registered as federated data store                       | Register it first (Pro "Manage Registered Data Stores" /`AddDataStoreItem`); else `StageService` 24011 aborts.                                                                                                                                                                                                                                                                                                                  |
| Message/notification direction not in REST                       | Default it on relationship creation; document.                                                                                                                                                                                                                                                                                                                                                                                      |
| SQL Server name constraints (reserved words, case, 128-char)     | Normalize dest names in the manifest; note remaps.                                                                                                                                                                                                                                                                                                                                                                                  |
| Map Image Layer renderer won't sync (no dynamic layers)          | Check `MapServer?f=json` `supportsDynamicLayers`; if false, enable dynamic layers on the service or accept image keeps Pro-baked symbology (pop-ups/extent/thumbnail still sync).                                                                                                                                                                                                                                               |
| Migration default tags leak onto the AGOL item                   | **DONE 2026-06-10:** `AddItemWithStoredCredentials.py` strips `Migrated from AGOL` / `Migrated` (case-insensitive) before adding `by reference` + `stored credentials`, and sets sharing (`AGOL_SHARING_LEVEL`, default `match_source`).                                                                                                                                                                        |
| Map Image Layer accidentally shared to AGOL                      | The backing Map Image Layer is now in the "Coverage Share" group too (decision #9, for Enterprise-side coverage + reassign), so AGOL exclusion is enforced on the share-back side: `AddItemWithStoredCredentials.py` drives off the LEDGER's Enterprise **Feature Service** ids, so the Map Service is never in the share-back work list.                                                                                          |
| Deprecating the source orphans live consumers                    | Deprecate the original**only after** the by-reference AGOL item is verified working (stored-cred access OK); description/comment already point consumers at the Portal URL (Phase 5b). **DONE 2026-06-10:** `DeprecateAndPropagateAuthoritative.py` also appends `New AGOL Item: <url>` to the source description and is **ledger-gated** (deprecates only items at `agol_updated` with no recorded error). |
| Authoritative flag lost when source is deprecated                | `contentStatus` is single-valued - capture `was_authoritative` in Phase 5b and propagate to the Portal + by-reference items **before** deprecating (decision #11).                                                                                                                                                                                                                                                        |
| Org comments disabled / no permission                            | `add_comment` may fail - skip-with-warning, don't abort the run; tags + description still applied.                                                                                                                                                                                                                                                                                                                                |
| `setContentStatus` API differs by arcgis version               | Verify `Item.content_status` set-mechanism (Python vs raw REST `setContentStatus`) against the installed version during the POC.                                                                                                                                                                                                                                                                                                |
| Scripts print-only (no audit trail)                              | Require file logging + the migration status ledger CSV on every script (see Section 5*Cross-cutting*).                                                                                                                                                                                                                                                                                                                            |
| Reassign fails (target user can't own / not in org / Viewer)     | Pre-check `gis.users.get` + ownership privilege; on any failure fall back to `rrgadmin` and log the fallback (decision #12).                                                                                                                                                                                                                                                                                                    |
| Owner not in `Owner_Map.csv`                                   | Treat as the blank-`Portal_Owner` case -> owner `rrgadmin`; log the unmapped `AGOL_Owner` so the map can be extended.                                                                                                                                                                                                                                                                                                         |
| Reassign needs admin; stored-cred `GPUser` is low-priv         | Run reassignment under an**admin** login (separate from the embedded stored-cred account); `reassign_to` requires admin/owner.                                                                                                                                                                                                                                                                                              |
| Reassign moves item to new owner's root folder                   | **DONE:** `ReassignMigratedItemOwners.py` sets `target_folder` on `reassign_to` (`get_item_folder_title` + `ensure_folder`, decision #12). Portal item -> mapped `Portal_Owner_User_Folder` (`folder_map.py` / `Folder_Map.csv`); AGOL by-ref -> original AGOL folder. `COPY_SOURCE_FOLDER` toggles it.                                                                                                     |
| Terms of Use (`licenseInfo`) not carried to the migrated items | **DONE:** Step 6 applies the source `licenseInfo` to the Enterprise + Map Image + AGOL items (regardless of the tags toggle); `AddItemWithStoredCredentials.py` also copies it onto the AGOL item at creation.                                                                                                                                                                                                            |
| Publish folder is one fixed value, not per-item                  | `ARCGIS_PORTAL_FOLDER_NAME`/`ARCGIS_SERVER_FOLDER_NAME` set a single folder per run (Enterprise item only); the authoritative per-item source folder is applied at the Phase-8 reassign (decision #12).                                                                                                                                                                                                                         |
| Stored credentials exposure / staleness                          | `credential_store.py` keeps logins in the per-user Windows Credential Manager (not the repo); rotate with `set`/`delete`. On a password change, runs fall back to a prompt if the stored value is stale.                                                                                                                                                                                                                      |

---

## 7. Decisions to confirm (before building)

1. **Referenced vs hosted/copied in Enterprise** - assume *referenced* feature services pointing at `RRGOrg` SQL (matches the enterprise model). **CONFIRMED: referenced** (POC runs full scope incl. Enterprise publish).
2. **Symbology apply method** - Python API `update_definition` + item data (recommended) vs `.lyrx` files. **CONFIRMED: item `/data` via `item.update(data=...)`** (renderer + pop-ups). **REVISED 2026-06-08 (POC Step 6):** `update_definition` (service renderer) does **NOT** work for a by-reference service published from Pro - that service renderer is baked from the Pro map authoring and has no REST `rest/admin/services` endpoint. The **item `/data`** path is the working programmatic edit and is what portal/web-map clients read; the service-level step is best-effort (hosted layers only).
3. **Orchestration** - keep phase-specific scripts (recommended, matches current repo) vs one combined driver. **CONFIRMED: phase-specific scripts.**
4. **Schema assignment** - how each of the 38 maps to `clim`/`crop`/`land`/`ws` (provided in the manifest). *(POC item -> `ws`.)*
5. **Attachments scope** - copy attachments for all, or only flagged layers? *(Open; POC item has none.)*
6. **Spatial reference** - **CONFIRMED: standardize all to WGS84 (wkid 4326)**; reproject in the local-staging copy (Phase 2) when the source differs. *(POC item is Web Mercator -> will be reprojected.)*
7. **Symbology/pop-up timing** - **CONFIRMED: record at copy time, APPLY AFTER PUBLISH.** Pop-ups
   (`popupInfo`) are a portal-item concept and cannot live on a FGDB/SDE feature class, so they must be
   applied to the published web items: renderer + pop-ups on the **Enterprise** item after Phase 5, and
   **renderer + pop-ups + min/max + default view again on the **AGOL by-reference** item after Phase 8**.
   **REVISED 2026-06-08 (per decision #2):** the renderer does **NOT** flow through the referenced service
   automatically - `updateDefinition` doesn't work for a by-reference service (its service renderer stays
   `simple`), and the new AGOL item has its own default `/data`, so everything must be re-applied to the AGOL
   item, not just pop-ups.
8. **Local staging** - **CONFIRMED: copy AGOL -> local file GDB first** (under `...\AGOL\Migrate`), reproject
   to WGS84 there, then load to SDE - rather than copying AGOL -> SDE directly.
9. **Map Service byproduct** - a referenced publish from Pro creates a backing **Map Service** (Map Image
   Layer) item alongside the **Feature Service** (Feature Layer) item, sharing the service name
   (`.../<name>/MapServer` vs `.../<name>/FeatureServer`). **REVISED 2026-06-08:** previously we left the Map
   Service untouched; now we **keep the two items in sync** - apply the **default view, pop-ups, and
   thumbnail** to the Map Image Layer item as well, and the **renderer where the service allows it**, so the
   two portal items present identically.
   - **Default view / pop-ups / thumbnail - unconditional.** The Map Image Layer item has its own `extent`
     (set via `item.update(item_properties={"extent": ...})`) and its own `/data` `layers[]` with per-sublayer
     `popupInfo` (read client-side by the Map Viewer). The thumbnail is **identical** to the Feature Layer's
     (same data/symbology/extent), so **reuse the same rendered PNG** rather than re-rendering.
   - **Renderer - conditional on dynamic layers.** The Map Image Layer item `/data` can carry per-sublayer
     `layerDefinition.drawingInfo`, **but the drawn image only honors it if the MapServer reports
     `supportsDynamicLayers: true`** (the Map Viewer applies the override via a `dynamicLayers` export
     request). Otherwise the image keeps the **publish-time (Pro-baked)** symbology - which in this workflow
     is the *blank/default* one, since real symbology is applied post-publish via item `/data` (decision #2).
     **POC RESULT 2026-06-08:** the POC MapServer reports **`supportsDynamicLayers: true`** -> the renderer
     override redraws the image, so all four sync. *Batch TODO:* not all services may allow dynamic layers - the
     batch driver should check `MapServer?f=json` per service and, if false, enable dynamic layers on the service
     (or accept that only pop-ups/extent/thumbnail sync there).
   - **Finding the Map Image Layer item id:** check item relationships first, then derive the sibling
     `MapServer` url (`FeatureServer`->`MapServer`) and match it against candidates found by **BOTH the item
     title AND the url-derived service name** - a name-only search misses a Map Service whose item title
     differs from its service name (e.g. item "Guayule Historic (v.1)" backed by service `Guayule_Current_V1`).
     Implemented as `find_map_image_item()` (Step 6, title-aware as of 2026-06-16) and
     `find_backing_map_services()` (coverage-share + reassign), kept in sync. (Phase 5 publish also yields both ids.)
   - **Backing Map Image Layer is now IN SCOPE for Enterprise-side coverage + ownership (2026-06-10).** The
     sibling Map Service travels with its Feature Service: `AddItemToCoverageShareGroup.py`
     (`SHARE_BACKING_MAP_IMAGE_LAYER=True`) adds it to the **Coverage Share** group alongside the Feature
     Service, and `ReassignMigratedItemOwners.py --target portal` (`REASSIGN_BACKING_MAP_IMAGE_LAYER=True`)
     reassigns it to the SAME owner + folder + "Created By"/attribution. It is **still NOT shared back to
     AGOL** (group-only; the AGOL by-reference item + share-back work list stay Feature-Service-only).
   - *Batch TODO:* confirm the batch publisher produces the same referenced Map+Feature pair; decide the
     long-term fate of the unshared Map Service items (~=2x item count at 6500 - keep synced, or delete).
10. **Tags & share-back scope** - **CONFIRMED 2026-06-08.**
    - **Enterprise item tags** = source AGOL tags **+ `Migrated from AGOL` + `Migrated`** (the two migration
      defaults). Applied to both the Feature Service and the synced Map Image Layer item (Phase 5 / Step 6).
    - **AGOL by-reference item tags** = the **original** AGOL tags **+ `by reference` + `stored credentials`**.
      The migration defaults are Enterprise-only and **must not** propagate to AGOL, so Phase 8 strips
      `Migrated from AGOL` / `Migrated` (case-insensitive) before adding the by-reference pair.
    - **Share back to AGOL: Feature Service only.** Only the Feature Layer is shared back to AGOL. The
      backing Map Image Layer IS now added to the **"Coverage Share"** group too (decision #9,
      `SHARE_BACKING_MAP_IMAGE_LAYER=True`) for Enterprise-side coverage + reassign, so the AGOL exclusion is
      enforced on the share-back side: `AddItemWithStoredCredentials.py` drives off the LEDGER's Enterprise
      Feature Service ids (`ledger_enterprise_item_ids()`), so the Map Service is never in the share-back work list.
11. **Source-item lifecycle - CONFIRMED 2026-06-08.** The **original AGOL item** is updated, then deprecated,
    as part of the round-trip:
    - **After Enterprise publish (Phase 5b):** append tags **`Migrated`** + **`Migrated to Portal`**; append
      `ArcGIS Portal URL: <portal item url>` to the **end of the description**; add a **comment** with the same
      URL (skip-with-warning if org comments are disabled); and **capture the original's `content_status`**.
    - **After share-back (Phase 8):** if the original was **Authoritative** (`org_authoritative` /
      `public_authoritative`), set the **same** status on the new **AGOL by-reference item** AND the
      **Enterprise Portal item**; **then deprecate the original AGOL item**. Capture/propagate Authoritative
      **before** deprecating (single-valued `contentStatus`).
    - *Open:* confirm the URL written is the **Enterprise Portal item page** (vs the service URL or the new AGOL
      by-reference item).
12. **Item ownership + "Created By" credit - CONFIRMED 2026-06-08.** Driven by an owner-mapping CSV
    **`Migrate\Input\Owner_Map.csv`** (TAB-delimited; columns `AGOL_Owner`, `Portal_Owner`, `Owner_Name`).
    - **Enterprise Portal item (after Coverage Share share):**
      - **Reassign owner** to the `Portal_Owner` mapped from the source item's `AGOL_Owner`
        (`item.reassign_to(portal_owner)`). **Fall back to `rrgadmin`** when: `Portal_Owner` is blank, the
        AGOL owner isn't in the map, OR the mapped user can't own items (no `portal:user:createItem` / Viewer
        user type). Requires an **admin** to run.
      - **Append `Created By: <Owner_Name>`** (the friendly name from the map) to the **end of the description**
        (append-only, idempotent). NOTE: `AddItemWithStoredCredentials.py` copies the Enterprise description to
        the AGOL by-reference item, so this credit propagates to the AGOL item too.
      - **Owner_Name as a TAG on fallback (added 2026-06-10).** When the mapped owner could **not** be applied
        (the reassign fell back to `rrgadmin` - Viewer/no-create-item, blank, or failure), the `Owner_Name` is
        also added as a **tag** on the Portal item (idempotent), so attribution survives even when the person
        can't own the item. *(POC reality: `samantha.martin` owns hers; `dave.dorrance` (ddorrance2) and
        `christina.bynum` (cortiz_rrg) are **Viewer** user types -> can't own -> rrgadmin owner + name tag.
        `check_owner_map.py` (new) validates `Owner_Map.csv` against Portal: reports OK / NO-OWN / MISSING /
        BLANK and suggests real usernames.)*
    - **New AGOL by-reference item (after share-back, Phase 8):** **reassign owner** to the **original AGOL
      item's owner** (`AGOL_Owner`) via `item.reassign_to(agol_owner, target_folder=...)` (original folder),
      **then share it to the org group(s)** in `AGOL_SHARE_GROUPS` (default **"RRG Nature Based Solutions
      Organization (Internal)"**) - owner first, then group (the `CopyDetailsOwnerGroupsOldItemToNew.py`
      pattern; added 2026-06-10). Needs an **AGOL admin** login (the embedded stored-cred account `GPUser` is
      not the login account, so an admin login can reassign); defensive fallback to `rrgadmin` if that owner
      can't own / doesn't resolve.
    - **API (verified arcgis 2.4.1.1):** `Item.reassign_to(target_owner, target_folder=None)`; ownership
      capability via `User.privileges` / `User.user_types`. Reassign moves the item to the new owner's
      root folder unless `target_folder` is given.
    - **Folder placement (2026-06-08; map-driven 2026-06-09; Folder-API fix 2026-06-10).** `ReassignMigratedItemOwners.py`
      resolves the source item's AGOL folder title (`owner_map.get_item_folder_title` - maps `ownerFolder` id ->
      title) and passes a `target_folder` to `reassign_to`, creating it under the new owner if missing
      (`owner_map.ensure_folder`). **2026-06-10:** `owner_map` was fixed for the newer `arcgis` API where
      `User.folders` returns **`Folder` objects** (not dicts) - `_fget()/_folder_id()/_folder_title()` read
      either form (the prior `'Folder' object has no attribute 'get'` warning sent items to root). Folder
      placement is now **best-effort**: if reassigning *into* the folder fails, the item is still reassigned to
      the owner's root rather than failing the whole reassign. The two targets differ: the **PORTAL** item goes to the **mapped
      `Portal_Owner_User_Folder`** from `Folder_Map.csv` (`folder_map.user_folder`; e.g. `MAXENT` -> `MaxEnt`;
      unmapped -> keep the name; `ROOT` -> owner root) - this sets the item's final content folder after the
      publish placed it in the portal ROOT; the **AGOL by-reference** item keeps the **original AGOL folder
      name** (no mapping - it returns to AGOL). Toggle `COPY_SOURCE_FOLDER`. Mirrors the established
      `ChangeArcGISOwner.py` pattern. Reading/creating another user's folder needs an **admin** connection
      (which reassign already requires); if the source folder title can't be read, it logs a warning and the
      item lands in the owner's root. Complements the publish-time `PortalFolderName` (Phase 5), which is a
      single per-run value and is overwritten by the reassign move.

---

## 8. Suggested next actions

1. Confirm the Section 7 decisions.
2. Build `BuildMigrationManifest.py` and produce the per-layer CSV for the 38; review it.
3. Pilot Phases 2 -> 4 on one single-layer and one multi-layer service; validate symbology round-trip.
4. Build `ApplySymbology.py` and `CreateRelationshipsInGDB.py`.
5. ~~Adapt `PublishFromDBToFeatureService.py` for feature services~~ - **already feature-capable**; ~~fix the raster `Provider` value~~ **DONE 2026-06-09 (shared `Provider`=`DMaps`; workflow publishes shared)**; still verify referenced-not-copied (Phase 5).
6. ~~Build `UpdateSourceAGOLItem.py` (Phase 5b) and `DeprecateAndPropagateAuthoritative.py` (Phase 8)~~ - **BUILT** (`Migrate/`); run them on the POC item after Phase 5 / Phase 8.
7. ~~Add **file logging** + stand up the **migration status ledger CSV** and wire it into the copy/publish/symbology/source phases~~ - **DONE** (`migration_status_ledger.py`; wired into Step 3, Step 3c, `PublishFromDBToFeatureService.py`, Step 6, Phase 5b, Phase 8).
8. Batch the remaining services; run Phase 6 validation.

> **Batch drivers + remaining gaps (updated 2026-06-12).** Two ordered drivers (Migrate/):
> `run_migration_pipeline.py` (SERIAL - every stage for all items before the next; `--plan`/`--run`/`--resume`
> over "manifest minus ledger") and `run_migration_batch.py` (PARALLEL copy + incremental once-stage sweeps -
> the "see AGOL results sooner" companion; reuses the same `build_stages`). **All Phase-5/5b/8 stages are
> BUILT**, and **`BuildPublishCSV.py` is now BUILT** (Phase 5 prep): it generates the publish CSV from the
> ledger's copied-but-unpublished rows, gated at **`copied_to_gdb`** so only items actually loaded to SDE are
> published, excluding errored rows. The only remaining `[TODO]` stages are the two **multi-layer** helpers
> (not needed for the single-layer POC items, which the per-item inspect/copy steps already cover):
>
> 1. **`BuildMigrationManifest.py`** (Phase 1) - expand multi-layer services into a per-layer/table CSV.
> 2. **`CreateRelationshipsInGDB.py`** (Phase 3) - recreate relationship classes (no-op where there are none).
>    These are the next scripts to implement for multi-layer services in the full ~6500-item batch.

---

## 9. POC: item `4d6aff488b9e48bf8a1f204c05d6f53d` ("Change in SW Supply by 2030")

End-to-end pilot of the full pipeline on one clean single-layer service before batching.
Scope: **full**, including the Phase 5 Enterprise referenced-service publish.

> **POC STATUS (current; last advanced 2026-06-10).** Two pilot items - `4d6aff488b9e48bf8a1f204c05d6f53d`
> (ws) + `64e4eeaa23a64987afb06097abed06c5` (crop) - driven via `run_migration_pipeline.py --resume`.
> **Done:** Steps 1-3 (copy/load to SDE); Phase 5 publish (referenced MapServer+FeatureServer pairs in `MaxEnt`,
> verified by-reference -> ledger `published_to_portal`); Step 6 symbology (`portal_updated`); and Phase 8
> through `reassign_portal` (5b source-update, coverage_share, and portal owner/folder all DONE - crop ->
> `samantha.martin@rrgnbs.com`/`MaxEnt`; ws -> fell back to `rrgadmin` + a "Dave Dorrance" name tag, since that
> owner is a Viewer and can't own items). **BLOCKED at `share_back`:** the GPUser Enterprise login is invalid -
> fix it (`python credential_store.py set GPUser`) and re-run. **Remaining:** share_back -> symbology_agol
> (`--agol --no-thumbnail`) -> thumb_copy_agol (`--copy-portal-to-agol`) -> reassign_agol -> deprecate. The full
> ordered sequence + work list are in `run_migration_pipeline.py --plan`; thumbnails are copy-based (Phase 4b);
> `deprecate` is gated on `agol_updated` with no recorded error (still verify stored-cred access for a consumer
> first). Enterprise item ids: ws `764f6940864a41adbeca491f3179b66d`, crop `0aef1bd4ddb44b229fc155d587187d7b`.

> **OPERATIONAL HARDENING + first parallel batch (2026-06-12).** The first `run_migration_batch.py` run over
> `Input\ItemsToMigratePhase1.csv` surfaced three recurring `error`-column patterns in the ledger; each was
> root-caused and fixed (full analysis: **`docs\plan\migration_error_remediation_plan.md`**):
>
> - **Already-WGS84 items stalled** (blank state + "batch gate ... `copied_local` did not appear"):
>   `migration_poc_step3_stage_local.py` took the DIRECT path (skip staging) and returned WITHOUT recording
>   `copied_local`, so the batch driver's ledger gate timed out and halted the item (and the recorded gate
>   error then blocked every resume). Fixed two ways: step3 now records `copied_local` even on the direct
>   return, AND **`FORCE_LOCAL_STAGING = True`** is now the default so every source stages locally and goes
>   through the reliable Step 3c LOAD path - retiring the fragile direct-to-SDE pager for normal runs (Phase 2).
> - **Premature publish** (`copied_local` rows + repeated "[publish] feature dataset ... does not exist"):
>   `BuildPublishCSV` defaulted to `include_state=copied_local`, so it listed items not yet in the SDE; publish
>   then failed and that error blocked the copy resume. Fixed: `BuildPublishCSV` now gates at **`copied_to_gdb`**.
> - **Unverifiable / fragile DIRECT copies:** step3c DIRECT mode now treats an *unobtainable* source count as a
>   FAILURE (the count match is the only completeness check, since `copyData` swallows per-page errors), and the
>   `copyFeaturesFromService` OID-window WHERE-clause spacing bug (`>5AND` -> `>5 AND`) was fixed.
> - **New tool** `Migrate\clear_error.py` clears a row's `error` so a fixed item is retried (errored rows are
>   skipped by the batch driver, the publish CSV, and the deprecate gate by design).
>   All six touched files (`BuildPublishCSV.py`, `clear_error.py`, `run_migration_pipeline.py`,
>   `migration_poc_step3_stage_local.py`, `migration_poc_step3c_load_sde.py`, `copyFeaturesFromService.py`) must
>   be **redeployed to `C:\Admin\Tools\ArcGIS Admin`** before a run picks them up.

**Second pilot item (added 2026-06-08).** A second service has also been copied into the enterprise
geodatabase for the remaining-steps run: **`RRGOrg.crop.Asparagus_Cold_Dormancy_Current_2030_Change`**
(schema `crop`; source AGOL item id **`64e4eeaa23a64987afb06097abed06c5`**, owner `smartindelcampo_20`,
title "Asparagus Cold Dormancy Climate Suitability Change from Historic to 2030 (v.2)"; renderer
**classBreaks on `Score`**, 1 layer/0 tables, layer id 0, polygon, no attachments/relationships, SR
102100, 7 SQL-safe fields). Both it and `RRGOrg.ws.Change_in_SW_Supply_by_2030` are now in the DB
(ledger: crop `copied_to_gdb`; ws loaded pre-ledger) and ready, so the remaining phases
(5 -> 5b -> 4/4b -> 8) will be run on **both** items. (Phase 7 calls for piloting 1-2 representative
services end-to-end before batching - these are those two.)

> **Two schemas, ONE Phase-5 publish run.** The two items live in different schemas (`ws`, `crop`).
> As of 2026-06-09 `PublishFromDBToFeatureService.py` accepts (a) **command-line overrides** and (b)
> **optional per-row CSV columns** so a single CSV/run can publish across multiple databases and schemas.
> Precedence for the SDE/db/schema: **explicit per-row CSV column > master manifest (by `item_id`) > CLI arg
>
>> .env > prompt** (so the shared `.env`, which holds the live monitoring/CRB config, never needs editing).
>> **SDE connection / database / schema come from the master manifest `Migrate\Input\ItemsToMigratePhase1.csv`**
>> (loader **`items_manifest.py`**, BUILT), keyed by AGOL Item ID - the single source of truth, NOT duplicated
>> in the publish CSV. So `poc_output/publish_input_poc.csv` carries only `feature_name`, **`item_id`**, the
>> item metadata (title/summary/description/tags/credits), `instance`, and `agol_owner_folder`; the script
>> looks up `Connection_Filepath` / `Target Database` / `Target Database Schema` from the manifest per row
>> (ws -> `RRGOrg_ws.sde`/`RRGOrg`/`ws`; crop -> `RRGOrg_crop.sde`/`RRGOrg`/`crop`). Per-row columns
>> `workspace_full_path` / `database_name` / `database_owner` still override the manifest if present. Single run:
>> `python PublishFromDBToFeatureService.py "<...>\publish_input_poc.csv" --server-manager-db "sde.DEFAULT (NBS-APP1)" --repository-id 0`
>> (`instance=shared`, `item_id`, and `agol_owner_folder` are per-row in the CSV; SDE/db/schema come from
>> `ItemsToMigratePhase1.csv` by `item_id`; the shared-provider `DMaps` fix landed 2026-06-09; the server REST
>> folder is resolved from `Folder_Map.csv` - ws `MAXENT` + crop `MaxEnt` both -> `MaxEnt` - and the portal
>> item folder is ROOT, published as rrgadmin).
>> Run-level workspace/owner/folder are optional now (blank = take
>> per-row). See `PublishFromDBToFeatureService.py --help` for the full option list.
>>

### Item facts (from cached metadata + live layer pull)

|                                        |                                                                                                                                                                  |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source service                         | `.../services/Change_in_SW_Supply_by_2030/FeatureServer` (org `cb1XtHtD3d6ZWNAQ`)                                                                            |
| Layers / tables                        | **1 layer, 0 tables**                                                                                                                                      |
| Layer id / name / geometry             | **`1`** / `aqueduct_projections` / **Polygon**                                                                                                   |
| Attachments / relationships / GlobalID | **none / none / none**                                                                                                                                     |
| Spatial reference                      | 102100 (Web Mercator, 3857) ->**reproject to WGS84 (4326)** during local staging; ~184 MB; global extent                                                   |
| Owner / access                         | `ddorrance2` / org-`shared` (no stored credentials)                                                                                                          |
| Target                                 | `RRGOrg.ws.Change_in_SW_Supply_by_2030` via `T:\ArcGISDataset\Enterprise\Connections\RRGOrg_ws.sde` (connected user `ws`, instance `NBS-APP1\frutsql01`) |

### Key findings

- **Phase 3 is a no-op** (no attachments, no relationships) - good clean pilot.
- **The cached `_data.json` carries NO renderer** - only `defaultVisibility` + `popupInfo`. The
  symbology lives at the **service level**, so the renderer must be pulled live from
  `.../FeatureServer/1?f=json` (done by `migration_poc_step1_inspect.py`). Pop-ups come from the
  cached `_data.json`; the renderer comes from the live `..._renderer.json`. Live pull confirmed the
  renderer is **`uniqueValue` on field `bt3038cl`**, and that field **exists** in the live layer ->
  symbology will resolve after copy.
- **Captured pop-up is STALE vs the live schema.** The live layer has only **16 fields** (`OBJECTID`,
  `BasinID`, `dwnBasinID`, `Area_km2`, `Shape_Leng`, the nine `bt****cl` strings, `Shape__Area`,
  `Shape__Length`), but the cached `_data.json` `popupInfo` references **hundreds** of fields
  (`ws*`/`ut*`/`sv*`/`bt*tr|tl|cr|ur|ul`) that were since removed from the service. Dead `fieldInfos`
  are ignored by ArcGIS (harmless), but **Step 6 decision:** apply the pop-up as-is, or prune
  `fieldInfos` to the 16 real fields. (Title `{BasinID}` is valid either way.) General lesson: the
  captured item `_data.json` can be out of sync with the current service - validate against the
  live field list before applying.
- **Layer-id shift `1 -> 0`:** the source layer is id `1`; the republished Enterprise referenced
  service will assign id `0`. `update_item_data.py` auto-infers single->single, so handled.
- Field names (`bt2024cl`, `ws*`, `ut*`, `sv*`, `Area_km2`, `Shape_Leng`, ...) are all <=10 chars and
  SQL-safe; `CopyFeatures` preserves them, so renderer/pop-up field refs should resolve without remap.
- Dest name resolves to `Change_in_SW_Supply_by_2030` (item `name`, not taken in `ws`).

### POC step status

- **Step 1 - inspect source + resolve dest name:** `migration_poc_step1_inspect.py` (BUILT, **RUN OK**
  as `jtripp23`). Renderer `uniqueValue`/`bt3038cl`, 16 SQL-safe fields, dest name
  `Change_in_SW_Supply_by_2030` (free). Artifacts in `poc_output/`.
- **Step 2 - 1-row manifest:** `poc_output/migration_manifest_poc.csv` (BUILT). layer `1` -> `ws` /
  `Change_in_SW_Supply_by_2030` / `RRGOrg_ws.sde`; no attach/rel.
- **Step 3a/3b - stage local + reproject:** `migration_poc_step3_stage_local.py` (BUILT) - reuses
  `copyFeaturesFromService.copyData()` to page AGOL layer 1 -> `...\AGOL\Migrate\<item_id>.gdb\Change_in_SW_Supply_by_2030_src`
  (source SR), then `arcpy.management.Project` -> `...\Change_in_SW_Supply_by_2030` (WGS84 4326), then drops
  `_src`. Per-item gdb (scales to ~6500 items), transient. Reads params from Step 1 report; reports counts.
  Now logs to file + sets ledger state `copied_local` (records `dest_feature_class`). *(ready to run)*
- **Step 3c - load FGDB -> SDE:** `migration_poc_step3c_load_sde.py` (BUILT, **RUN OK**) - loaded
  `Migrate\<item_id>.gdb\Change_in_SW_Supply_by_2030` -> **`RRGOrg.ws.Change_in_SW_Supply_by_2030`**
  (15,006 features, WGS84 4326, count verified); transient staging gdb auto-deleted. Refuses to clobber
  an existing dest (`OVERWRITE_EXISTING`). Has a DIRECT mode (paged copyData AGOL->SDE) for already-WGS84
  items that skipped staging, but that path is **dormant by default now that step3 sets
  `FORCE_LOCAL_STAGING=True`** (every item stages locally and step3c runs its reliable LOAD path /
  `ExportFeatures`); DIRECT mode also now **FAILS if the source feature count can't be obtained** - a count
  match is the only completeness check for a paged copy (copyData swallows per-page errors) (2026-06-12). Now
  logs to file + sets ledger state `copied_to_gdb` (records `dest_database`/`dest_schema`/`dest_feature_class`).
  **-> Steps 1-3 of the POC are complete; data is in the enterprise GDB.**
- **Step 4 - relationships/attachments:** skip (none).
- **Step 5 - publish referenced service: RUN OK 2026-06-09 for BOTH POC items** (via the refactored
  `FEDERATED_SERVER`/`MAP_IMAGE`/`copyDataToServer=False` + Feature Access path - see Phase 5). Datastore
  registration done (RRGOrg clim/ws/sde/land/crop). Driver `PublishFromDBToFeatureService.py` +
  `poc_output/publish_input_poc.csv` (per-row `item_id`; SDE/db/schema from `ItemsToMigratePhase1.csv`;
  `instance=shared`; server folder `MaxEnt` via `Folder_Map.csv`; portal item folder ROOT). Published (both
  verified **referenced** via the service `manifest.xml` `<ByReference>true</ByReference>`; one `.MapServer`
  definition per service, FeatureServer is its Feature Access extension):
  - ws  `4d6aff488b9e48bf8a1f204c05d6f53d` -> Enterprise Feature Layer **`764f6940864a41adbeca491f3179b66d`**,
    `.../arcgisserver/rest/services/MaxEnt/Change_in_SW_Supply_by_2030/FeatureServer` (+ MapServer sibling).
  - crop `64e4eeaa23a64987afb06097abed06c5` -> Enterprise Feature Layer **`0aef1bd4ddb44b229fc155d587187d7b`**,
    `.../arcgisserver/rest/services/MaxEnt/Asparagus_Cold_Dormancy_Current_2030_Change/FeatureServer` (+ MapServer sibling).
    Ledger `published_to_portal` recorded for both; the integrated Step 6 then advanced both to `portal_updated`.
    *(The earlier manual `6698de1a...` / `6b887c6b...` test items are superseded by these real publishes.)*
  - **Post-publish item fidelity - ALL FIXED 2026-06-09 (publish is fully working):**

    1. **Title synced to BOTH items.** `validate_and_update_portal_item` now iterates the published pair
       (MapServer + FeatureServer share the service name) and sets the friendly title on **both** the Feature
       Layer and the Map Image Layer (was: only the first match) - decision #9.
    2. **Description = the ORIGINAL AGOL item.** New `get_source_description()` reads the source item's
       description (HTML) from the cached `AGOL_<id>_description_*.json` (DataDump) and the publish applies it
       to **both** items, instead of the concise CSV `description`. (The publish resolves the source item id
       via the ledger join first, then passes it to the title/description sync.)
    3. **`['nan']` categories** - empty CSV `categories`/`portal_groups` came in as `NaN`; read side now
       coerces to '', apply side drops blank/`'nan'`.

    - **Patching the two ALREADY-published POC items** (these fixes apply to future publishes; the existing
      items predate them): run `poc_update_portal_items.py` (ledger-driven; sets title + source description on
      each Feature Layer **and** its Map Image sibling) and `clear_categories.py`. Both BUILT this date.
  - Portal **owner + per-item folder are NOT set at publish** (item created as rrgadmin in the portal ROOT);
    applied at the **Phase-8 reassign** (`ReassignMigratedItemOwners.py --target portal`, decision #12).
- **Step 5b - update the source AGOL item:** `UpdateSourceAGOLItem.py` (**BUILT, not yet run**) - on source
  item `4d6aff...`: append tags `Migrated` + `Migrated to Portal`, append `ArcGIS Portal URL: <url>` to the
  description (HTML `<p>` with a link; append-only/idempotent), add a comment with the same URL
  (skip-with-warning if org comments disabled), and capture `content_status` (`org-shared`, **not** currently
  authoritative - so the Phase 8 authoritative propagation is a no-op for this POC item, but the code path
  exists for items that are). Logs to file + writes the status ledger (state `source_updated`); `DRY_RUN`.
  Run after Phase 5 publish: `python UpdateSourceAGOLItem.py 4d6aff488b9e48bf8a1f204c05d6f53d 6b887c6b9395471fb7c88dc115037ec6`.
- **Step 6 - symbology:** `migration_poc_step6_apply_symbology.py` (BUILT, **RUN OK 2026-06-08**) - applies
  renderer (from live `..._renderer.json`) via `updateDefinition` to target layer 0 **and** renderer+pop-ups
  (pop-ups from cached `_data.json`) via item `/data`, remapping `1->0`, with backups + field-reference check;
  **prune ON** (`PRUNE_STALE_FIELDINFOS=True` -> pop-up trimmed from 223 to the 16 live fields). Target item id
  via CLI arg. Two manual test items exist: **blank** `6b887c6b...` (`WS_Change_in_SW_Supply_by_2030`, default
  target) and **control** `6698de1a...` (`TEST_w_symbol_...`, symbolized by hand in Pro).
  `migration_poc_compare_services.py` (BUILT, **RUN OK**) dumps + diffs both services' layer JSON + item
  `/data` to prove before/after.
  - **RESULT:** the item `/data` edit succeeded - blank target's **item-level** renderer went
    `simple -> uniqueValue/bt3038cl` and pop-up went default -> the source AGOL pop-up (`{BasinID}`, pruned to
    the 16 live fieldInfos), matching the control. **Programmatic pop-up + symbology correction via
    `item.update(data=...)` is CONFIRMED working** - and **visually verified correct in the portal viewer**
    on `6b887c6b...` (2026-06-08).
  - **SECOND TARGET double-check (2026-06-08):** re-ran on `361dae1d...` (`TEST_3w_symbol_...`, a Pro-authored
    control that already had item-level symbology). Backed up its prior `/data`, then overwrote item `/data`
    to renderer `uniqueValue/bt3038cl` (7 unique-value classes) + the source pop-up (`{BasinID}`, pruned to
    16 fieldInfos) - identical outcome, confirming the apply is consistent across targets.
  - **VISIBILITY RANGE added (2026-06-08):** scale-dependent visibility (`minScale`/`maxScale`) did NOT copy
    - it lives on the source SERVICE layer (`minScale=0, maxScale=9027`), is **absent from the cached
      `_data.json`**, and the Enterprise targets defaulted to `0/0` (no limit). It is captured in Step 1's
      `..._layer<n>_service.json`. Step 6 now reads `minScale`/`maxScale` from that file and writes them into
      the item `/data` `layerDefinition` (the client-honored lever; the service-layer value can't be set on a
      by-reference service - same `updateDefinition` constraint as the renderer). Re-ran on `6b887c6b...`:
      item `/data` `layerDefinition` now `minScale=0/maxScale=9027`, **identical to the AGOL source**.
      *General lesson:* the renderer JSON alone is insufficient - layer-display props (`minScale`/`maxScale`,
      and potentially `definitionExpression`, `displayField`) come from the full source layer def, not the
      cached `_data.json`.
  - **FINDING (changes Phase 4 / decision #2):** service-level `updateDefinition` is **NOT available** for a
    by-reference service published from a Pro map (it is a **MapServer + FeatureServer extension**; the
    federated `arcgisserver` exposes **no `rest/admin/services` catalog**, so `.manager.update_definition`
    raises `{'code':500,'message':'Service not found'}`). The service renderer is **baked from the Pro map
    authoring** - it cannot be set via REST. The script now treats the service step as **best-effort** (works
    for HOSTED layers, gracefully skips for referenced) and relies on the **item `/data`** path, which is what
    portal / web-map clients actually read for renderer + pop-ups (pop-ups live ONLY there regardless).
  - **DEFAULT VIEW / EXTENT added (2026-06-08):** Step 6 now also copies the **source item's default extent**
    (item-level bounding box, WGS84 `[[xmin,ymin],[xmax,ymax]]`) to the target via
    `item.update(item_properties={"extent": ...})`, so the target item opens to the same view as the source. The
    extent is read from the cached `_description.json`, with a **live AGOL fallback** (`SOURCE_PORTAL_URL`, Pro
    session or anonymous) when it isn't cached. (Service `initialExtent`/`fullExtent` are computed from the data
    and are **not** set - there is no per-layer "zoom" to copy; scale-dependent visibility is the `minScale`/`maxScale`
    handled above.)
  - Two small fixes during the run: `datetime` import changed to `import datetime as dt` (the
    `from datetime import datetime` form broke `datetime.now()` under the arcgis import); service step wrapped
    in try/except so a referenced service no longer aborts the item update.
  - **MAP IMAGE LAYER sync (decision #9, BUILT + RUN OK 2026-06-08):** Step 6 now also applies the same renderer +
    pop-ups + default view to the backing **Map Image Layer** item so the pair matches. POC items: Feature Layer
    `6b887c6b...` (`.../Test/WS_Change_in_SW_Supply_by_2030/FeatureServer`) <-> Map Image Layer
    **`fcab4da7fa8d4530adae3dee9a1f7530`** (`.../Test/WS_Change_in_SW_Supply_by_2030/MapServer`). The sibling is
    **auto-discovered** (FeatureServer->MapServer url match) - confirmed it found `fcab4da7...` (type "Map Service")
    with no manual id. Item `/data` (renderer `uniqueValue/bt3038cl`, visibility `0/9027`, pop-up pruned to 16
    fields) + default extent applied to **both** items OK; prior `/data` of each backed up to `poc_output/`.
    **`.../MapServer?f=json` `supportsDynamicLayers` = TRUE** -> the renderer override **does** redraw the map image,
    so all four (symbology + pop-ups + default view + thumbnail) sync for this pair. *(Visual confirm in the portal
    Map Viewer still recommended.)*
  - **TERMS OF USE added (2026-06-08):** Step 6 now also copies the source item's **`licenseInfo`** (Terms of
    Use / use constraints) to the target via `item.update(item_properties={"licenseInfo": ...})`, applied to the
    Feature Layer, the Map Image Layer, and (on the Phase 8 re-apply) the AGOL item - **regardless of `APPLY_TAGS`**
    (it is not a tag). Read from the cached `_description.json` with a live-AGOL fallback (same source as
    extent/tags). Confirmed present for the POC item (the WRI Aqueduct Creative Commons license text). Closes the
    pre-patch gap where Title/Summary/Description/Credits transferred but Terms of Use did not. *General lesson:*
    item-property fidelity (Folder, Owner, Title, Summary, Description, Terms of Use, Credits) spans three places -
    the publish CSV (title/summary/description/credits), Step 6 item properties (`licenseInfo`, tags, extent), and
    the reassign step (owner + folder).
- **Step 6b - regenerate thumbnail:** `RegenerateItemThumbnails.py` (BUILT, **RUN OK 2026-06-08**) - renders
  `6b887c6b...` on the portal default basemap via the **print service** using the item `/data` `uniqueValue/bt3038cl`
  renderer, then sets the result as the item thumbnail so the portal item card reflects the applied symbology. The
  by-reference service renderer stays `simple`, so the portal's "Create from Map" button would render a single
  color - this script injects the **item `/data`** renderer instead (and skips `minScale`/`maxScale` so the layer
  always draws). The thumbnail is framed to `item.extent`, so it **must run after Step 6's default-view/extent copy**
  (else it frames the world and warns). `DRY_RUN` available; PNGs written to `Output/Thumbnails/`. Run after Step 6
  (and again after Step 8 for the AGOL item).
  - **MAP IMAGE LAYER (decision #9):** apply the **same PNG** to the Map Image Layer item (`fcab4da7...`) - same
    data/symbology/extent => identical thumbnail, no re-render needed.
- **Step 7 - QA:** row count, field parity, geometry, visual symbology + pop-up check.
- **Step 8 - share back to AGOL:**
  - **8 prep - group membership (decision #9/#10):** `AddItemToCoverageShareGroup.py` (BUILT) adds the
    Feature Service (`6b887c6b...`) to the **"Coverage Share"** group, and (`SHARE_BACKING_MAP_IMAGE_LAYER=True`,
    2026-06-10) **also** pulls in its backing Map Image Layer (`fcab4da7...`) alongside it. The Map Service is
    group-shared + reassigned in Portal but is NOT shared back to AGOL (the share-back work list is the
    ledger's Feature Service ids). Title- AND url-aware sibling detection + idempotent + `DRY_RUN`.
  - **8 prep (b) - Portal owner + "Created By" (decision #12):** `ReassignMigratedItemOwners.py --target portal`
    (**BUILT, not yet run**) - on `6b887c6b...`: append `Created By: Dave Dorrance` (source owner `ddorrance2`
    maps to `dave.dorrance@rrgnbs.com` / "Dave Dorrance") and reassign owner to that Portal_Owner (fallback
    `rrgadmin`). Run as an Enterprise **admin**. *(For `ddorrance2` the map has a non-blank Portal_Owner, so no
    fallback expected.)* **Folder (2026-06-08):** also moves the Portal item into the source item's folder via
    `target_folder` (created under the new owner if missing); `COPY_SOURCE_FOLDER`.
  - `AddItemWithStoredCredentials.py` with `portal_item_ids_to_add=['6b887c6b9395471fb7c88dc115037ec6']` (or the
    group) -> creates an AGOL by-reference item with stored creds (account `GPUser` or similar); intended tags =
    original AGOL tags + `by reference` + `stored credentials`. *(2026-06-08: now also copies the source
    `licenseInfo` (Terms of Use) onto the AGOL item at creation, alongside the existing snippet/description/
    `accessInformation` copy; Step 6's AGOL re-apply re-asserts it regardless.)*
    **GAP status (updated 2026-06-16):** the migration-default tag strip and item sharing are **DONE in code** -
    the script strips `Migrated from AGOL` / `Migrated` (case-insensitive) before adding the by-reference pair
    (decision #10 now enforced), and sets the new item's sharing via `AGOL_SHARING_LEVEL` (default `match_source`,
    mirroring the original AGOL item's access through the ledger join). **Map-Image exclusion - RESOLVED:** the
    share-back work list now drives off the **LEDGER's Enterprise Feature Service ids**
    (`ledger_enterprise_item_ids()`), not the "Coverage Share" group, so the backing Map Service (now also a
    group member, decision #9) is never in `items_to_add`. (The earlier "add an in-script `Feature Service` type
    filter" gap is moot - the ledger-driven work list is Feature-Service-only by construction.)
  - Then re-apply renderer + pop-ups + min/max + default view to the new AGOL item using
    **`migration_poc_step6_apply_symbology.py` generalized for AGOL** (`TARGET_PORTAL_URL`=AGOL, `APPLY="item"`,
    `APPLY_TAGS=False`, `SYNC_MAP_IMAGE_LAYER=False`; pass the new AGOL item id as the CLI arg) - a superset of
    `update_item_data.py --apply item` (which carries renderer/pop-ups but not min/max or default view). Then
    `RegenerateItemThumbnails.py` (Step 6b) against it for the thumbnail.
  - **Step 8c - AGOL owner (decision #12):** `ReassignMigratedItemOwners.py --target agol --byref <new id>`
    (**BUILT, not yet run**) - reassign the new by-reference AGOL item to the **original** AGOL owner
    (`ddorrance2`), fallback `rrgadmin`. Run as an AGOL **admin**, **before** Step 8b deprecation.
    **Folder (2026-06-08):** also places the by-reference item in the source item's folder (resolved from the
    original AGOL item) via `target_folder`; `COPY_SOURCE_FOLDER`.
  - **Step 8b - authoritative propagation + deprecate source (decision #11):**
    `DeprecateAndPropagateAuthoritative.py` (**BUILT, not yet run**) - if `4d6aff...` was Authoritative (it is
    `org-shared`, not authoritative -> propagation no-op here), set the same status on the new AGOL item + the
    Portal item `6b887c6b...`; then set `4d6aff...` `content_status = "deprecated"`. Reads the by-reference item id
    from the CLI arg or the ledger and **refuses to deprecate unless that replacement resolves**. Uses the settable
    `Item.content_status` (verified in arcgis 2.4.1.1). Logs to file + updates the ledger
    (`authoritative_propagated` -> `source_deprecated`); `DRY_RUN`. Run last:
    `python DeprecateAndPropagateAuthoritative.py <agol_byref_item_id> 6b887c6b9395471fb7c88dc115037ec6 4d6aff488b9e48bf8a1f204c05d6f53d`.
  - Round-trip complete: AGOL -> RRGOrg SQL -> Enterprise -> AGOL.

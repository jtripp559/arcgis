# -*- coding: utf-8 -*-
"""
Name: migration_poc_step3_stage_local.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-04

================================================================================
WHAT THIS SCRIPT DOES  (POC Step 3a/3b of the AGOL -> RRGOrg SDE migration)
================================================================================
Stage one AGOL feature-service layer to a LOCAL file geodatabase and standardize
its spatial reference to WGS84 (wkid 4326). This is the "copy local + reproject"
half of Phase 2 -- it does NOT touch the SDE (that is Step 3c, a separate load).

Data flow handled here:
    AGOL feature layer  ->  Migrate.gdb\\<dest>_src  (source SR, paged copy)
                        ->  Migrate.gdb\\<dest>       (reprojected to WGS84 4326)

Why local first: isolates AGOL paging / 429 handling and the reprojection from the
SDE write, and leaves a verifiable local artifact before anything lands in RRGOrg.

It reuses the proven paging engine `copyData()` from `copyFeaturesFromService.py`
(REST OID paging -> FeatureSet -> FeatureClassToFeatureClass/Append), then runs
`arcpy.management.Project` to WGS84. Parameters are read from the Step 1 report
(`Migrate/Output/<id>_step1_report.json`) so the steps chain; CONFIG below overrides.

================================================================================
HOW TO RUN
================================================================================
Run inside the ArcGIS Pro conda env. Authenticates with stored/entered AGOL credentials FIRST
(credential_store); the active GIS("pro") session is used only as a fallback if they don't work.

    python migration_poc_step3_stage_local.py
    python migration_poc_step3_stage_local.py <itemId>

================================================================================
OUTPUT
================================================================================
  T:\\...\\AGOL\\Migrate\\Migrate.gdb\\<dest>_src   (source SR staging copy)
  T:\\...\\AGOL\\Migrate\\Migrate.gdb\\<dest>       (WGS84 4326, ready for SDE load)

NEXT (Step 3c, not done here): load Migrate.gdb\\<dest> into the target schema
(`RRGOrg_ws.sde`, connect as the schema owner) -> RRGOrg.ws.<dest>.
"""

import os
import sys
import json
import getpass
import shutil

import arcpy
from arcgis.gis import GIS

# This file lives in ArcGIS Admin\docs\plan\completed. copyFeaturesFromService.py + credential_store.py are
# in the ArcGIS Admin root; migration_status_ledger.py is in ArcGIS Admin\Migrate -- add both to sys.path.
ARCGIS_ADMIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for _p in (ARCGIS_ADMIN_DIR, os.path.join(ARCGIS_ADMIN_DIR, "Migrate")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from copyFeaturesFromService import copyData  # noqa: E402  (proven paging engine -- route a)
import migration_status_ledger as ledger_mod  # noqa: E402
import credential_store  # noqa: E402
from export_item_to_fgdb import export_to_fgdb  # noqa: E402  (route b: full-fidelity export incl attachments)
from arcgis.features import FeatureLayerCollection  # noqa: E402

logger = ledger_mod.setup_logging(__file__)


def log_message(msg, level="info"):
    """Log to file AND console. level in info|warning|error|debug (defaults to info)."""
    getattr(logger, level if level in ("info", "warning", "error", "debug") else "info")(msg)
    if level == "error":
        _record_error_to_ledger(msg)


# Reentrancy guard + per-run de-dupe so the auto-record-on-error in log_message neither loops nor appends
# the same message to the ledger row's error column more than once.
_recording_ledger_error = False
_recorded_ledger_errors = set()


def _record_error_to_ledger(message):
    """Best-effort: when an 'error' is logged, append it to this item's migration-status-ledger row (keyed by
    the SOURCE item_id ITEM_ID; create=True because the copy phase owns/creates the row). CENTRALIZES the
    'on error, record against the row' pattern so individual error sites don't each need their own
    record_error block -- an errored row is then skipped by future publish CSVs and not retried every sweep.
    De-duped per run + reentrancy-guarded; never raises (logging must not depend on the ledger)."""
    global _recording_ledger_error
    if ledger_mod is None or not ITEM_ID or _recording_ledger_error:
        return
    key = (str(ITEM_ID).lower(), str(message)[:300])
    if key in _recorded_ledger_errors:
        return
    _recording_ledger_error = True
    try:
        ledger_mod.record_error(ITEM_ID, str(message)[:300], phase="copy_local", create=True, logger=logger)
        _recorded_ledger_errors.add(key)
    except Exception:
        pass   # never let ledger recording break logging
    finally:
        _recording_ledger_error = False

# ----------------------------------------------------------------------------
# CONFIG  (most values are read from the Step 1 report; override here if needed)
# ----------------------------------------------------------------------------
def _cli_flag(name, default=None):
    """Value following a `--name` token in sys.argv (e.g. `--migrate-dir C:\\scratch`), else default.
    Lets a run override a setting WITHOUT editing this file; the positional item-id arg and the deployed
    pipeline's `python <script> <item_id>` call keep working."""
    argv = sys.argv
    if name in argv and argv.index(name) + 1 < len(argv):
        return argv[argv.index(name) + 1]
    return default


def _first_positional(default):
    """First non-flag token after argv[0] (the source item id). Skips `--flag value` pairs so the item id
    resolves correctly regardless of argument order."""
    skip = False
    for tok in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if tok.startswith("--"):
            skip = True            # our flags (e.g. --migrate-dir) take a value -> skip it too
            continue
        return tok
    return default


ITEM_ID = _first_positional("64e4eeaa23a64987afb06097abed06c5")  # source AGOL item id (positional arg)

OUTPUT_DIR = os.path.join(ARCGIS_ADMIN_DIR, "Migrate", "Output")
# Migration ledger path + writes are handled by migration_status_ledger (ledger_mod.set_state); the
# canonical path resolves to OUTPUT_DIR\migration_status_ledger.csv (env MIGRATION_LEDGER_PATH overrides).

# Local staging location (per the migration plan).
# PER-ITEM staging gdb (Migrate\<item_id>.gdb): a single shared gdb would not scale to the ~6500
# items eventually migrated (FGDB performance/size). Each per-item gdb is transient -- delete it
# after the Step 3c SDE load succeeds.
# Override per-run WITHOUT editing this file via `--migrate-dir <path>` or env MIGRATION_STAGING_DIR -- e.g.
# point a POC/test run at a LOCAL scratch dir so it never writes into the shared T: staging folder a
# production run is actively using. Default = the shared T: location the production migration uses.
MIGRATE_DIR = (_cli_flag("--migrate-dir") or os.getenv("MIGRATION_STAGING_DIR")
               or r"T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\Migrate")

TARGET_WKID = 4326  # WGS84 (GCS WGS 1984)

# After the WGS84 reproject succeeds, delete the source-SR intermediate (<dest>_src) to keep the
# per-item staging gdb lean (the final WGS84 FC is what Step 3c loads to SDE).
DELETE_SRC_AFTER_PROJECT = True

# ALWAYS stage locally, even when the source is already WGS84 (4326). A 4326 source COULD be copied
# AGOL -> SDE directly (the Step 3c "direct" path), saving a copy -- but that path drives
# copyFeaturesFromService.copyData straight into SDE, whose multi-page insert branch is the least-tested,
# most fragile copy path, and copyData swallows per-page errors (a dropped page is silent). Staging to a
# local FGDB first routes EVERY item through the reliable Step 3c LOAD path (ExportFeatures of a whole
# local FC) with a verifiable feature count at each hop. Set this False to re-enable the direct-to-SDE
# path for 4326 sources (saves one copy, but is less safe -- see the Step 3c DIRECT-mode notes).
FORCE_LOCAL_STAGING = True

# Route (b) -- staging METHOD. copyData (the REST /query paging engine, "route a") copies geometry +
# attributes of ONE layer ONLY: it DROPS attachments, relationship classes, and the GlobalID, and does not
# handle tables or multi-layer items. A full-fidelity Esri EXPORT to FGDB instead brings ALL layers + tables
# + attachments + relationship classes + the ORIGINAL GlobalIDs, is NOT bounded by maxRecordCount, and routes
# every item through the reliable Step-3c LOAD path (proven end to end -- see export_item_to_fgdb.py). The
# reproject below then runs with preserveGlobalIds=True.
#   "always" (DEFAULT for this migration) -> always stage via export. The faithful/robust path: covers
#            attachments, relationships, tables, AND multiple layers, and preserves GlobalIDs for every item.
#            Cost: a temp export item per item + the source must allow Extract (the export helper enables it
#            temporarily and restores it). Items that cannot export FALL BACK to copyData automatically.
#   "auto"   -> export only when the source layer reports attachments OR relationships; else copyData. NOTE:
#            this does NOT detect multi-layer/table items, so a multi-layer item with no attachments would
#            mis-route to the single-layer copyData path. Use only for known-simple single-layer items.
#   "never"  -> always copyData (legacy; attachments/relationships/tables/extra layers will NOT transfer).
# On ANY export-path failure the code falls back to the copyData path, so this never hard-fails an item.
EXPORT_MODE = "always"

# Per-key fallbacks (belt-and-suspenders only). The script REQUIRES a Step-1 report for ITEM_ID
# (see the guard in main) so these are never used for a different item; they remain only so a
# partial report with a missing key degrades gracefully.
FALLBACK_SERVICE_URL = ""
FALLBACK_LAYER_ID = 0
FALLBACK_DEST_NAME = ""

# ---- AGOL sign-in -----------------------------------------------------------
# Auth for the source (org-shared) service: the active ArcGIS Pro session is tried FIRST; if Pro is
# unavailable or yields no usable token, it falls back to an AGOL username/password login (prompted).
AGOL_URL = "https://rrg.maps.arcgis.com/"
AGOL_USERNAME = ""   # optionally pre-fill the username; left blank -> prompted (not SSO)


def load_step1_report(item_id):
    path = os.path.join(OUTPUT_DIR, f"{item_id}_step1_report.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _token_from_pro():
    """Try the active ArcGIS Pro session. Return (gis, token), or (None, None) on failure/empty token."""
    try:
        gis = GIS("pro")
    except Exception as e:
        log_message(f"   (ArcGIS Pro session unavailable: {e})")
        return None, None
    token = None
    try:
        token_info = arcpy.GetSigninToken()  # active ArcGIS Pro portal token
        if token_info and token_info.get("token"):
            token = token_info["token"]
    except Exception as e:
        log_message(f"   (arcpy.GetSigninToken failed: {e})")
    token = token or gis._con.token
    return (gis, token) if token else (None, None)


def _token_from_login():
    """Log in to AGOL via the shared credential_store.connect() (stored 'agol' credential first, Pro/prompt
    fallback). Return (gis, token)."""
    gis = credential_store.connect(AGOL_URL, key="agol", default_username=AGOL_USERNAME, log=log_message)
    return gis, gis._con.token   # token is populated for user/password auth


def connect_and_get_token():
    """Connect for a token: stored/entered credentials FIRST; the active ArcGIS Pro session is
    used only as a fallback if the credentials don't work. Returns (gis, token); (None, None) if
    neither yields a usable token."""
    log_message("connecting   : trying stored/entered AGOL credentials first ...")
    try:
        gis, token = _token_from_login()
        if token:
            return gis, token
        log_message("   credentials gave no usable token; falling back to the active ArcGIS Pro session.")
    except Exception as e:
        log_message(f"   credential login failed ({e}); falling back to the active ArcGIS Pro session.")
    return _token_from_pro()


def _refresh_token(gis):
    """Return a FRESH token from the SAME connection that minted the original (no re-prompt). Passed to
    copyData as token_provider so a long paged copy can recover from token expiry mid-run: reading
    gis._con.token makes the ArcGIS API regenerate the token once it has expired. arcpy.GetSigninToken()
    is only a fallback (it is the Pro-session identity, which may differ from the stored AGOL credential,
    so it is tried last). Returns None if neither yields a token."""
    try:
        tok = gis._con.token
        if tok:
            return tok
    except Exception as e:
        log_message(f"   (token refresh via gis._con.token failed: {e})", "warning")
    try:
        ti = arcpy.GetSigninToken()
        if ti and ti.get("token"):
            return ti["token"]
    except Exception as e:
        log_message(f"   (token refresh via arcpy.GetSigninToken failed: {e})", "warning")
    return None


def get_record_count(gis, layer_url):
    """Total feature count via returnCountOnly (NOT capped by maxRecordCount). -1 if unknown."""
    try:
        res = gis._con.get(f"{layer_url}/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})
        if isinstance(res, dict) and "count" in res:
            return int(res["count"])
    except Exception as e:
        log_message(f"   (count probe failed: {e})")
    return -1


def _norm_name(s):
    """Fold a layer/FC name to a comparable key (lowercased, non-alphanumeric runs -> '_')."""
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def _find_export_fc(export_gdb, src_layer_name):
    """Path to the operational feature class in the export FGDB for the target layer. Excludes the
    attachment/relationship companion tables (__ATTACH/__ATTACHREL) and the export's GDB_ServiceItems
    metadata table. Matches the source layer name (normalized); if exactly one operational FC exists,
    returns it. Returns None if it cannot be resolved unambiguously (e.g. a multi-layer item with no match)."""
    arcpy.env.workspace = export_gdb
    fcs = list(arcpy.ListFeatureClasses() or [])
    for ds in (arcpy.ListDatasets(feature_type="Feature") or []):
        fcs += [os.path.join(ds, f) for f in (arcpy.ListFeatureClasses(feature_dataset=ds) or [])]
    if not fcs:
        return None
    want = _norm_name(src_layer_name)
    for fc in fcs:
        if _norm_name(os.path.basename(fc)) == want:
            return os.path.join(export_gdb, fc)
    return os.path.join(export_gdb, fcs[0]) if len(fcs) == 1 else None


def _cleanup_export_tmp(item_id, export_root):
    """Remove the throwaway export download (the unzipped <id>_fgdb dir + the <id>_fgdb_export_tmp*.zip)
    under export_root. Best-effort; never raises."""
    import glob
    try:
        extract_dir = os.path.join(export_root, f"{item_id}_fgdb")
        if os.path.isdir(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
        for z in glob.glob(os.path.join(export_root, f"{item_id}_fgdb_export_tmp*.zip")):
            try:
                os.remove(z)
            except OSError:
                pass
    except Exception as e:
        log_message(f"   (export temp cleanup note: {e})")


def _stage_via_export(gis, item_id, service_url, src_layer_name, dest_name, staging_gdb,
                      live_wkid, expected_count):
    """Route (b) staging: export the whole item to a FGDB (brings the __ATTACH table + relationship classes
    + ORIGINAL GlobalIDs), then reproject/rename the target layer's FC into staging_gdb\\<dest_name> as WGS84
    with preserveGlobalIds=True (so attachments/relationships stay linked). On a verified stage it sets the
    ledger 'copied_local' and returns True; on ANY problem it logs a warning and returns False so the caller
    falls back to the copyData paging path. (POC scope: single target layer; a multi-layer item exports the
    whole service and this picks the one FC for src_layer_name.)"""
    try:
        itm = gis.content.get(item_id)
        if itm is None:
            log_message("   export: source item not found via the API; cannot use export path", "warning")
            return False
        flc = FeatureLayerCollection.fromitem(itm)
        export_root = os.path.join(MIGRATE_DIR, "_export_tmp")
        export_gdb = export_to_fgdb(itm, flc, export_root, keep_export_item=False, manage_capability=True)
        if (not export_gdb) or not arcpy.Exists(export_gdb):
            log_message("   export: export-to-FGDB produced no geodatabase", "warning")
            return False
        export_fc = _find_export_fc(export_gdb, src_layer_name)
        if not export_fc:
            log_message(f"   export: could not locate the FC for layer '{src_layer_name}' in the export gdb "
                        f"(multi-layer item without a name match?)", "warning")
            return False

        final_fc = os.path.join(staging_gdb, dest_name)
        if arcpy.Exists(final_fc):
            arcpy.management.Delete(final_fc)
        # KEEP the original AGOL GlobalIDs through the reproject -- attachments (__ATTACH.REL_GLOBALID) and
        # relationship classes key on them; regenerating would orphan them.
        arcpy.env.preserveGlobalIds = True
        if int(live_wkid or 0) == TARGET_WKID:
            log_message(f"   export: source already WGS84 -> ExportFeatures '{os.path.basename(export_fc)}' "
                        f"-> {dest_name} (preserveGlobalIds) ...")
            arcpy.conversion.ExportFeatures(export_fc, final_fc)
        else:
            log_message(f"   export: reproject {live_wkid} -> {TARGET_WKID}; '{os.path.basename(export_fc)}' "
                        f"-> {dest_name} (preserveGlobalIds) ...")
            arcpy.management.Project(export_fc, final_fc, arcpy.SpatialReference(TARGET_WKID))
        if not arcpy.Exists(final_fc):
            log_message("   export: staging FC was not created", "warning")
            return False

        final_count = int(arcpy.management.GetCount(final_fc)[0])
        final_sr = arcpy.Describe(final_fc).spatialReference
        attach_tbl = os.path.join(staging_gdb, f"{dest_name}__ATTACH")
        attach_n = int(arcpy.management.GetCount(attach_tbl)[0]) if arcpy.Exists(attach_tbl) else 0
        log_message(f"   export: staged {final_count} feature(s); SR {final_sr.factoryCode} "
                    f"({final_sr.name}); attachments={attach_n}")
        if final_sr.factoryCode != TARGET_WKID:
            log_message(f"   export: staged SR {final_sr.factoryCode} != {TARGET_WKID} -- not accepting", "warning")
            return False
        if expected_count is None or expected_count < 0:
            log_message("   export: source count UNKNOWN -- cannot confirm the export is complete; "
                        "not accepting (will fall back to copyData).", "warning")
            return False
        if final_count != expected_count:
            log_message(f"   export: COUNT MISMATCH (source {expected_count} vs staged {final_count}) -- "
                        "not accepting (will fall back to copyData).", "warning")
            return False

        _cleanup_export_tmp(item_id, export_root)
        # The ledger MUST capture this milestone -- a lost 'copied_local' write makes the batch gate time out
        # and halt the item. The cross-process lock WAITS through transient Windows permission errors; if it
        # still can't write, let it PROPAGATE (raises a fatal ledger_mod.LedgerWriteError -> the step exits non-zero) rather than
        # continue with a stale ledger.
        ledger_mod.set_state(item_id, "copied_local", logger=logger,
                             source_service_url=service_url, dest_feature_class=dest_name)
        log_message(f"  [route b] staged {dest_name} ({final_count} feats, attachments={attach_n}) via export; "
                    f"GlobalIDs + attachments + relationships preserved. Ready for Step 3c.")
        return True
    except Exception as e:
        log_message(f"   export path error: {e}", "warning")
        return False


def main():
    report = load_step1_report(ITEM_ID)
    if not report:
        log_message(f"!! no Step-1 report for {ITEM_ID} in {OUTPUT_DIR}. "
                    f"Run migration_poc_step1_inspect.py {ITEM_ID} first. Stopping.", "error")
        return
    service_url = report.get("source_service_url", FALLBACK_SERVICE_URL)
    layer_id = report.get("layer_id", FALLBACK_LAYER_ID)
    dest_name = report.get("dest_feature_class", FALLBACK_DEST_NAME)
    src_sr = report.get("spatial_reference") or {}
    src_wkid = src_sr.get("latestWkid") or src_sr.get("wkid")

    log_message(f"=== POC Step 3a/3b: stage local + reproject to WGS84 for {ITEM_ID} ===\n")
    log_message(f"source layer : {service_url}/{layer_id}")
    log_message(f"dest name    : {dest_name}")
    log_message(f"source SR    : {src_wkid}")

    # --- connect for a token (org-shared service needs auth) ----------------
    gis, token = connect_and_get_token()
    if not token or gis is None:
        log_message("!! no token obtained from credentials or the ArcGIS Pro session; "
                    "cannot query the secured service. Stopping.")
        return
    me = gis.users.me
    log_message(f"connected as : {me.username if me else '?'} on {gis.url}")
    log_message("token        : obtained")

    # --- read the live layer def (authoritative SR + maxRecordCount) --------
    layer_url = f"{service_url}/{layer_id}"
    svc = gis._con.get(layer_url, {"f": "json"}) or {}
    max_rec = int(svc.get("maxRecordCount", 1000) or 1000)
    live_sr = (svc.get("extent", {}) or {}).get("spatialReference", {}) or {}
    live_wkid = live_sr.get("latestWkid") or live_sr.get("wkid") or src_wkid

    # Probe the total record count: chunking is only needed when count > maxRecordCount.
    rec_count = get_record_count(gis, layer_url)
    needs_chunking = (rec_count < 0) or (rec_count > max_rec)
    count_str = rec_count if rec_count >= 0 else "unknown"
    chunk_str = "YES (count > maxRecordCount)" if needs_chunking else "no (single pass fits in one query)"
    log_message(f"live SR       : {live_wkid}   maxRecordCount: {max_rec}")
    log_message(f"record count  : {count_str}   chunking: {chunk_str}")

    # Route (b) trigger: does this layer carry attachments and/or relationships? (read from the LIVE layer
    # def -- authoritative). If so, copyData would silently drop them, so we stage via export instead.
    has_attach = bool(svc.get("hasAttachments"))
    has_rels = bool(svc.get("relationships"))
    src_layer_name = svc.get("name") or dest_name
    log_message(f"attachments  : {has_attach}   relationships: {len(svc.get('relationships') or [])}   "
                f"source layer name: {src_layer_name}")

    # --- skip local staging if already WGS84 (no reproject needed) ----------
    # "skip local staging" drops the FGDB intermediate + the reproject. Whether the AGOL->SDE copy itself
    # needs chunking depends ONLY on count vs maxRecordCount (copyData self-selects single-pass vs paged).
    if live_wkid == TARGET_WKID and not FORCE_LOCAL_STAGING:
        log_message(f"\nSource is already WGS84 ({TARGET_WKID}) -- local staging + reproject NOT needed.")
        sde_target = f"<RRGOrg_schema.sde>\\<schema>.{dest_name}"
        if needs_chunking:
            log_message(f"Step 3c direct path: count {count_str} > maxRecordCount {max_rec} -> PAGED copy required:")
            log_message(f"  copyData('{layer_url}', '{sde_target}', token, maxRecordCount={max_rec})")
        else:
            log_message(f"Step 3c direct path: count {count_str} <= maxRecordCount {max_rec} -> a SINGLE copy is enough:")
            log_message(f"  arcpy.conversion.ExportFeatures('{layer_url}', '{sde_target}')   # one query, no paging")
        log_message(f"  (Set FORCE_LOCAL_STAGING=True to stage locally anyway.)")
        # Record the copied_local milestone even though no local FGDB was produced: step3's job (decide
        # source SR + stage/skip) is DONE, and step3c self-selects its DIRECT AGOL->SDE mode when no staged
        # FC exists. Without this, an orchestrator that gates the next stage on copied_local (e.g.
        # run_migration_batch.py) would wait forever for a milestone that the direct path never sets and
        # then halt the item. dest_feature_class is recorded so step3c/publish can resolve the dest name.
        # The write must not be silently skipped: the lock WAITS through transient permission errors, and a
        # genuine post-retry failure PROPAGATES (raises a fatal ledger_mod.LedgerWriteError -> the step exits non-zero).
        ledger_mod.set_state(ITEM_ID, "copied_local", logger=logger,
                             source_service_url=service_url,
                             dest_feature_class=dest_name)
        return

    # --- make the per-item staging gdb (Migrate\<item_id>.gdb) --------------
    if not os.path.isdir(MIGRATE_DIR):
        os.makedirs(MIGRATE_DIR)
    staging_gdb_name = f"{ITEM_ID}.gdb"
    staging_gdb = os.path.join(MIGRATE_DIR, staging_gdb_name)
    if not arcpy.Exists(staging_gdb):
        log_message(f"creating staging gdb: {staging_gdb}")
        arcpy.management.CreateFileGDB(MIGRATE_DIR, staging_gdb_name)
    arcpy.env.overwriteOutput = True

    # --- Route (b): export-to-FGDB for attachment/relationship-bearing layers -----------------------
    # copyData (route a, below) copies geometry + attributes only -- it DROPS attachments and the GlobalID.
    # For a layer that has attachments and/or relationships, stage via a full-fidelity export instead
    # (brings the __ATTACH table + relationship class + ORIGINAL GlobalIDs) and reproject with
    # preserveGlobalIds=True. Any failure falls through to the copyData path so a simple item never blocks.
    use_export = (EXPORT_MODE == "always") or (EXPORT_MODE == "auto" and (has_attach or has_rels))
    if use_export:
        log_message(f"\n[route b] attachments={has_attach}, relationships={has_rels} -> staging via "
                    f"export-to-FGDB (preserves attachments + relationships + GlobalIDs)")
        if _stage_via_export(gis, ITEM_ID, service_url, src_layer_name, dest_name, staging_gdb,
                             live_wkid, rec_count):
            return
        log_message("[route b] export staging did not complete -> falling back to copyData paging path.",
                    "warning")
    elif EXPORT_MODE == "auto":
        log_message("\n[route a] no attachments/relationships -> copyData paging path (geometry + attributes).")

    src_fc = os.path.join(staging_gdb, f"{dest_name}_src")
    final_fc = os.path.join(staging_gdb, dest_name)

    # --- 3a. paged copy AGOL -> local FGDB (source SR) ----------------------
    log_message(f"\n[3a] copying AGOL layer -> {src_fc} (source SR) ...")
    if arcpy.Exists(src_fc):
        arcpy.management.Delete(src_fc)
    copyData(service=layer_url, featureClass=src_fc, token=token, maxRecordCount=max_rec,
             token_provider=lambda: _refresh_token(gis))
    if not arcpy.Exists(src_fc):
        log_message("!! staging copy failed -- see CopyFeaturesFromService log. Stopping.")
        ledger_mod.record_error(ITEM_ID, f"staging copy AGOL->FGDB failed for {dest_name} (no output FC)",
                                phase="copy_local", create=True, logger=logger)
        return
    src_count = int(arcpy.management.GetCount(src_fc)[0])
    staged_sr = arcpy.Describe(src_fc).spatialReference
    log_message(f"     staged {src_count} features; SR = {staged_sr.factoryCode} ({staged_sr.name})")

    # --- 3b. reproject to WGS84 (or pass through if already 4326) -----------
    if staged_sr.factoryCode == TARGET_WKID:
        log_message(f"\n[3b] already WGS84 ({TARGET_WKID}); copying to final name ...")
        if arcpy.Exists(final_fc):
            arcpy.management.Delete(final_fc)
        arcpy.management.CopyFeatures(src_fc, final_fc)
    else:
        log_message(f"\n[3b] reprojecting {staged_sr.factoryCode} -> {TARGET_WKID} (WGS84) ...")
        if arcpy.Exists(final_fc):
            arcpy.management.Delete(final_fc)
        arcpy.management.Project(src_fc, final_fc, arcpy.SpatialReference(TARGET_WKID))

    final_count = int(arcpy.management.GetCount(final_fc)[0])
    final_sr = arcpy.Describe(final_fc).spatialReference
    log_message(f"     final {final_count} features; SR = {final_sr.factoryCode} ({final_sr.name})")

    # --- drop the source-SR intermediate once the reproject is verified -----
    if DELETE_SRC_AFTER_PROJECT and src_fc != final_fc and src_count == final_count and arcpy.Exists(src_fc):
        arcpy.management.Delete(src_fc)
        log_message(f"     removed source-SR intermediate {os.path.basename(src_fc)}")

    # --- QA summary ---------------------------------------------------------
    log_message("\n--- staging summary ---")
    log_message(f"  staging gdb : {staging_gdb}")
    log_message(f"  final       : {dest_name}  ({final_count} feats, SR {final_sr.factoryCode})")

    # TWO independent completeness checks must BOTH pass before advancing to 'copied_local':
    #   (1) reproject integrity : the WGS84 FC kept every row the source-SR staging copy had (src == final).
    #   (2) SOURCE completeness  : the staged FC has EVERY row the LIVE AGOL layer reports (final == rec_count).
    #       This is the gate that catches a SILENTLY TRUNCATED copy. copyData swallows per-page errors, so a
    #       dropped page leaves a short-but-internally-consistent FC that check (1) alone passes -- exactly how
    #       a short copy reached SDE undetected (caught only later by ValidateMigratedItems). rec_count comes
    #       from returnCountOnly (NOT capped by maxRecordCount). An UNKNOWN source count is treated as a
    #       FAILURE -- we cannot prove completeness -- mirroring the Step 3c gate.
    count_known = rec_count is not None and rec_count >= 0
    reproject_ok = (src_count == final_count)
    source_ok = count_known and (final_count == rec_count)
    if not reproject_ok:
        log_message(f"  !! COUNT MISMATCH ({src_count} -> {final_count}) after reproject -- investigate before SDE load")
    elif not count_known:
        log_message("  !! source feature count could not be determined -- cannot confirm the copy is complete "
                    "(copyData does not fail on dropped pages). Treating as a FAILURE.")
    elif not source_ok:
        log_message(f"  !! TRUNCATED COPY: staged {final_count} != live source {rec_count} "
                    f"({rec_count - final_count} row(s) missing) -- NOT advancing; investigate the copy.")
    else:
        log_message(f"  count preserved and matches the live source ({final_count} == {rec_count}). "
                    f"Ready for Step 3c: load -> SDE.{dest_name}")
    log_message("  NOTE: this per-item staging gdb is transient -- delete it after the Step 3c SDE load succeeds.")

    # --- migration status ledger (state -> copied_local only on a FULLY verified stage; else record error) ---
    if reproject_ok and source_ok:
        # Milestone write must not be silently skipped (a lost 'copied_local' halts the item at the batch
        # gate). The lock WAITS through transient permission errors; a genuine post-retry failure PROPAGATES
        # (raises a fatal ledger_mod.LedgerWriteError -> the step exits non-zero) instead of continuing with a stale ledger.
        ledger_mod.set_state(ITEM_ID, "copied_local", logger=logger,
                             source_service_url=service_url,
                             dest_feature_class=dest_name)
    else:
        detail = (f"staged {final_count} vs live source {rec_count if count_known else 'UNKNOWN'} "
                  f"(reproject {src_count} -> {final_count})")
        ledger_mod.record_error(ITEM_ID, f"staging completeness check failed for {dest_name} ({detail})",
                                phase="copy_local", create=True, logger=logger)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_message(f"!! Step 3 failed for {ITEM_ID}: {e}", "error")   # auto-recorded to the ledger row
        raise

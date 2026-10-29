# -*- coding: utf-8 -*-
"""
Name: migration_poc_step3c_load_sde.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-04

================================================================================
WHAT THIS SCRIPT DOES  (POC Step 3c of the AGOL -> RRGOrg SDE migration)
================================================================================
Load one layer into the target enterprise geodatabase as WGS84 (4326), owned by
the target schema, verify the row count + spatial reference, and -- on success --
delete the transient per-item staging gdb.

Two modes (auto-selected):
  * LOAD (default): a reprojected WGS84 staging FC already exists at
    Migrate\\<item_id>.gdb\\<dest> (produced by migration_poc_step3_stage_local.py).
    Copy it into the SDE. This is the path for sources that were NOT WGS84.
  * DIRECT: no staging FC exists AND the source is already WGS84 (4326). Paged-copy
    AGOL -> SDE directly (no local stage / reproject), reusing copyFeaturesFromService.

Connect to the SDE as the SCHEMA OWNER (e.g. RRGOrg_ws.sde as 'ws') so the data is
created in and owned by that schema -> RRGOrg.<schema>.<dest>.

================================================================================
HOW TO RUN
================================================================================
    python migration_poc_step3c_load_sde.py
    python migration_poc_step3c_load_sde.py <itemId>

Reads parameters from the Step 1 report (Migrate/Output/<id>_step1_report.json):
dest_db, dest_schema, dest_feature_class, target_sde, source_service_url, layer_id,
spatial_reference. CONFIG below overrides.
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
# (Was hardcoded to a T: network copy; computed locally now that the script lives under completed\.)
ARCGIS_ADMIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for _p in (ARCGIS_ADMIN_DIR, os.path.join(ARCGIS_ADMIN_DIR, "Migrate")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import migration_status_ledger as ledger_mod  # noqa: E402
import credential_store  # noqa: E402

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
        ledger_mod.record_error(ITEM_ID, str(message)[:300], phase="copy_sde", create=True, logger=logger)
        _recorded_ledger_errors.add(key)
    except Exception:
        pass   # never let ledger recording break logging
    finally:
        _recording_ledger_error = False

# ----------------------------------------------------------------------------
# CONFIG  (most values come from the Step 1 report; override here if needed)
# ----------------------------------------------------------------------------
def _cli_flag(name, default=None):
    """Value following a `--name` token in sys.argv (e.g. `--migrate-dir C:\\scratch`), else default."""
    argv = sys.argv
    if name in argv and argv.index(name) + 1 < len(argv):
        return argv[argv.index(name) + 1]
    return default


def _first_positional(default):
    """First non-flag token after argv[0] (the source item id). Skips `--flag value` pairs."""
    skip = False
    for tok in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if tok.startswith("--"):
            skip = True
            continue
        return tok
    return default


ITEM_ID = _first_positional("64e4eeaa23a64987afb06097abed06c5")  # source AGOL item id (positional arg)

OUTPUT_DIR = os.path.join(ARCGIS_ADMIN_DIR, "Migrate", "Output")
# Migration ledger path + writes are handled by migration_status_ledger (ledger_mod.set_state); the
# canonical path resolves to OUTPUT_DIR\migration_status_ledger.csv (env MIGRATION_LEDGER_PATH overrides).
# MIGRATE_DIR must match the value step3 staged into. Override per-run via `--migrate-dir <path>` or env
# MIGRATION_STAGING_DIR (e.g. a local scratch dir for an isolated test); default = the shared T: location.
MIGRATE_DIR = (_cli_flag("--migrate-dir") or os.getenv("MIGRATION_STAGING_DIR")
               or r"T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\Migrate")

TARGET_WKID = 4326  # WGS84

# Delete the transient per-item staging gdb after a verified SDE load (LOAD mode only).
DELETE_STAGING_ON_SUCCESS = True
# Refuse to clobber an existing destination FC unless this is True.
OVERWRITE_EXISTING = False

# AGOL sign-in (DIRECT mode only): Pro session first, then username/password.
AGOL_URL = "https://rrg.maps.arcgis.com/"
AGOL_USERNAME = ""

# Per-key fallbacks (belt-and-suspenders only). The script REQUIRES a Step-1 report for ITEM_ID
# (see the guard in main), so these are never used for a different item; they remain only so a
# partial report with a missing key degrades gracefully.
FALLBACK = {
    "dest_db": "RRGOrg",
    "dest_schema": "",
    "dest_feature_class": "",
    "target_sde": "",
    "source_service_url": "",
    "layer_id": 0,
}


def load_step1_report(item_id):
    path = os.path.join(OUTPUT_DIR, f"{item_id}_step1_report.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def connect_and_get_token():
    """Connect for a token (DIRECT mode only) via the shared credential_store.connect(): stored 'agol'
    credential FIRST, then the active ArcGIS Pro session, then a prompt. Returns (gis, token). When the
    connection is the Pro-session fallback (no usable _con token), fall back to arcpy.GetSigninToken()."""
    gis = credential_store.connect(AGOL_URL, key="agol", default_username=AGOL_USERNAME, log=log_message)
    token = gis._con.token
    if not token:
        try:
            ti = arcpy.GetSigninToken()
            if ti and ti.get("token"):
                token = ti["token"]
        except Exception:
            pass
    return gis, token


def main():
    rpt = load_step1_report(ITEM_ID)
    if not rpt:
        log_message(f"!! no Step-1 report for {ITEM_ID} in {OUTPUT_DIR}. "
                    f"Run migration_poc_step1_inspect.py {ITEM_ID} first. Stopping.", "error")
        return
    dest_db = rpt.get("dest_db", FALLBACK["dest_db"])
    dest_schema = rpt.get("dest_schema", FALLBACK["dest_schema"])
    dest_name = rpt.get("dest_feature_class", FALLBACK["dest_feature_class"])
    target_sde = rpt.get("target_sde", FALLBACK["target_sde"])
    service_url = rpt.get("source_service_url", FALLBACK["source_service_url"])
    layer_id = rpt.get("layer_id", FALLBACK["layer_id"])
    src_sr = rpt.get("spatial_reference") or {}
    src_wkid = src_sr.get("latestWkid") or src_sr.get("wkid")

    log_message(f"=== POC Step 3c: load -> {dest_db}.{dest_schema}.{dest_name} ===\n")

    if not arcpy.Exists(target_sde):
        log_message(f"!! target SDE connection not found: {target_sde}. Stopping.")
        return
    arcpy.env.overwriteOutput = True

    staging_gdb = os.path.join(MIGRATE_DIR, f"{ITEM_ID}.gdb")
    staged_fc = os.path.join(staging_gdb, dest_name)
    dest_qualified = f"{dest_db}.{dest_schema}.{dest_name}"
    dest_path = os.path.join(target_sde, dest_name)          # created owned by the connected schema user
    dest_check = os.path.join(target_sde, dest_qualified)

    # --- guard against clobbering an existing destination ------------------
    if arcpy.Exists(dest_check):
        if not OVERWRITE_EXISTING:
            log_message(f"!! destination already exists: {dest_qualified}")
            log_message("   set OVERWRITE_EXISTING=True to replace it, or pick a new dest name. Stopping.")
            return
        log_message(f"   overwriting existing {dest_qualified}")
        arcpy.management.Delete(dest_check)

    mode = "LOAD" if arcpy.Exists(staged_fc) else None
    expected_count = None

    if mode == "LOAD":
        # --- LOAD: staged WGS84 FGDB FC -> SDE ------------------------------
        src_sr_desc = arcpy.Describe(staged_fc).spatialReference
        expected_count = int(arcpy.management.GetCount(staged_fc)[0])
        log_message(f"mode        : LOAD  (staged FC {staged_fc})")
        log_message(f"staged       : {expected_count} features, SR {src_sr_desc.factoryCode} ({src_sr_desc.name})")
        if src_sr_desc.factoryCode != TARGET_WKID:
            log_message(f"!! staged FC is SR {src_sr_desc.factoryCode}, expected WGS84 {TARGET_WKID}. "
                  f"Re-run Step 3a/3b. Stopping.")
            return
        log_message(f"loading -> {dest_qualified} ...")
        # Preserve the ORIGINAL GlobalIDs into SDE so attachments (__ATTACH) and relationship classes stay
        # linked (route b). ExportFeatures FGDB->SDE carries the __ATTACH table + relationship class when the
        # staged FC has them AND preserveGlobalIds is set -- proven 2026-06-12 (full fidelity into SQL Server).
        # Harmless for plain layers (nothing to preserve). NOTE: the CopyFeatures fallback below does NOT carry
        # attachments, so it is a degraded path used only if ExportFeatures itself errors.
        arcpy.env.preserveGlobalIds = True
        try:
            arcpy.conversion.ExportFeatures(staged_fc, dest_path)
        except Exception as e:
            log_message(f"   ExportFeatures failed ({e}); trying CopyFeatures "
                        f"(NOTE: attachments/relationships will NOT transfer on this fallback) ...", "warning")
            arcpy.management.CopyFeatures(staged_fc, dest_path)
    else:
        # --- DIRECT: no staging FC; only valid if source is already WGS84 ---
        if src_wkid not in (TARGET_WKID, None):
            log_message(f"!! no staged FC at {staged_fc}, and source SR is {src_wkid} (not WGS84).")
            log_message("   Run Step 3a/3b (stage + reproject) first. Stopping.")
            return
        log_message(f"mode        : DIRECT  (no staging FC; source already WGS84 -> paged copy AGOL->SDE)")
        from copyFeaturesFromService import copyData  # noqa: E402
        gis, token = connect_and_get_token()
        if not token:
            log_message("!! no token; cannot query the secured service. Stopping.")
            return
        layer_url = f"{service_url}/{layer_id}"
        svc = gis._con.get(layer_url, {"f": "json"}) or {}
        max_rec = int(svc.get("maxRecordCount", 1000) or 1000)
        # Source feature count is the ONLY post-copy completeness check for the DIRECT path (copyData
        # swallows per-page errors), so it must be obtained robustly: try returnCountOnly, then fall back
        # to counting returnIdsOnly. If BOTH fail, expected_count stays None and the verify block below
        # treats the copy as UNVERIFIABLE -> failure (do not advance on a guess).
        expected_count = None
        try:
            res = gis._con.get(f"{layer_url}/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})
            if isinstance(res, dict) and res.get("count") is not None:
                expected_count = int(res["count"])
        except Exception as e:
            log_message(f"   (returnCountOnly failed: {e}; falling back to returnIdsOnly)", "warning")
        if expected_count is None:
            try:
                ids_res = gis._con.get(f"{layer_url}/query",
                                       {"where": "1=1", "returnIdsOnly": "true", "f": "json"})
                obj_ids = (ids_res or {}).get("objectIds") if isinstance(ids_res, dict) else None
                if obj_ids is not None:
                    expected_count = len(obj_ids)
            except Exception as e:
                log_message(f"   (returnIdsOnly count also failed: {e})", "warning")
        log_message(f"paged copy -> {dest_qualified} (maxRecordCount={max_rec}) ...")
        # token_provider lets copyData recover from token expiry mid-copy: on a 498/499 it reads
        # gis._con.token (the ArcGIS API regenerates it once expired) and retries the window once.
        copyData(service=layer_url, featureClass=dest_path, token=token, maxRecordCount=max_rec,
                 token_provider=lambda: gis._con.token)

    # --- verify ------------------------------------------------------------
    if not arcpy.Exists(dest_check):
        log_message(f"!! load failed -- {dest_qualified} not found after load. Stopping.")
        ledger_mod.record_error(ITEM_ID, f"SDE load failed -- {dest_qualified} not found after load",
                                phase="copy_sde", create=True, logger=logger)
        return
    sde_count = int(arcpy.management.GetCount(dest_check)[0])
    sde_sr = arcpy.Describe(dest_check).spatialReference
    log_message("\n--- load summary ---")
    log_message(f"  dest    : {dest_qualified}")
    log_message(f"  features: {sde_count}" + (f"  (expected {expected_count})" if expected_count is not None else ""))
    log_message(f"  SR      : {sde_sr.factoryCode} ({sde_sr.name})")

    # Best-effort attachment-fidelity check (route b): compare the staged FGDB __ATTACH row count to the
    # SDE __ATTACH row count. Informational only -- does not gate the load.
    if mode == "LOAD":
        try:
            staged_attach = staged_fc + "__ATTACH"
            if arcpy.Exists(staged_attach):
                staged_att_n = int(arcpy.management.GetCount(staged_attach)[0])
                sde_attach = os.path.join(target_sde, dest_qualified + "__ATTACH")
                sde_att_n = int(arcpy.management.GetCount(sde_attach)[0]) if arcpy.Exists(sde_attach) else 0
                tag = "OK" if sde_att_n == staged_att_n else "MISMATCH"
                log_message(f"  attach  : staged {staged_att_n} -> SDE {sde_att_n}  [{tag}]",
                            "info" if tag == "OK" else "warning")
        except Exception as e:
            log_message(f"  (attachment count check skipped: {e})")

    # Completeness gate: the SR must be WGS84 AND the source count must be KNOWN and MATCH. An unknown
    # expected_count is NOT a free pass -- copyData swallows per-page errors, so without a count match we
    # cannot tell a complete copy from a silently truncated one. (LOAD mode always has a count from the
    # staged FC, so this only tightens the DIRECT path.)
    count_known = expected_count is not None
    ok = (sde_sr.factoryCode == TARGET_WKID) and count_known and (sde_count == expected_count)
    if not ok:
        if sde_sr.factoryCode != TARGET_WKID:
            log_message(f"  !! SR is not WGS84 ({TARGET_WKID}) -- investigate.")
        if not count_known:
            log_message("  !! source feature count could not be determined -- cannot confirm the copy is "
                        "complete (copyData does not fail on dropped pages). Treating as a FAILURE.")
        elif sde_count != expected_count:
            log_message(f"  !! COUNT MISMATCH (expected {expected_count}, got {sde_count}) -- investigate.")
        log_message("  staging gdb NOT deleted (verification failed).")
        detail = (f"SR {sde_sr.factoryCode}, count {sde_count} vs expected "
                  f"{expected_count if count_known else 'UNKNOWN (source count unobtainable)'}")
        ledger_mod.record_error(ITEM_ID, f"SDE load verification failed for {dest_qualified} ({detail})",
                                phase="copy_sde", create=True, logger=logger)
        return

    log_message("  load verified (count + SR OK).")
    # --- delete the transient staging gdb on success (LOAD mode) -----------
    if mode == "LOAD" and DELETE_STAGING_ON_SUCCESS and os.path.isdir(staging_gdb):
        try:
            arcpy.management.Delete(staging_gdb)
            if os.path.isdir(staging_gdb):           # belt-and-suspenders if a lock lingered
                shutil.rmtree(staging_gdb, ignore_errors=True)
            log_message(f"  deleted transient staging gdb: {staging_gdb}")
        except Exception as e:
            msg = f"could not delete staging gdb {staging_gdb}: {e} -- delete manually"
            log_message(f"  ({msg})", "warning")
            # NON-FATAL: the load succeeded; only the transient staging gdb couldn't be removed (usually a
            # lingering file lock). Record it to the ledger NOTES column (NOT error -- an error would block
            # this item's resume / publish / deprecate) so it survives for manual cleanup later. create=True
            # because this runs just before the set_state below that (re)creates the row.
            ledger_mod.record_note(ITEM_ID, msg, phase="copy_sde", create=True, logger=logger)

    # --- migration status ledger (state -> copied_to_gdb on a verified load) ---
    # The ledger MUST capture this milestone -- a lost write desyncs the pipeline (the batch gate would wait
    # for 'copied_to_gdb', time out, and mark the item failed). The cross-process lock already WAITS through
    # transient Windows permission/sharing errors; if it STILL can't write, it raises a fatal
    # ledger_mod.LedgerWriteError (a BaseException best-effort handlers don't swallow) -> the step exits
    # non-zero rather than continuing with a stale ledger.
    ledger_mod.set_state(ITEM_ID, "copied_to_gdb", logger=logger,
                         source_service_url=service_url,
                         dest_database=dest_db,
                         dest_schema=dest_schema,
                         dest_feature_class=dest_name)

    log_message(f"\nDone. Next: Phase 5 publish {dest_qualified} as a referenced Enterprise feature service.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_message(f"!! Step 3c failed for {ITEM_ID}: {e}", "error")   # auto-recorded to the ledger row
        raise

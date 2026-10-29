# -*- coding: utf-8 -*-
"""
Name: migration_poc_step1_inspect.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-04  (CSV-driven 2026-06-08)

================================================================================
WHAT THIS SCRIPT DOES  (POC Step 1 of the AGOL -> RRGOrg SDE migration)
================================================================================
For ONE AGOL feature-service item, gather everything Step 2 (build the manifest)
and Step 6 (apply symbology) need, WITHOUT changing anything. It is read-only.

It does four things:

  0. Looks the item up in the input CSV (Migrate\\Input\\ItemsToMigratePhase1.csv)
     to get the target SDE connection file, target database, and target schema -- so
     the only thing you have to pass to run a different item is its AGOL item id.

  1. Loads the already-captured metadata for the item from the GetAllArcGISService-
     Metadata DataDump (the item `_get`/description JSON and the `_data` JSON), if
     present, to read the item `name` and whether pop-ups were captured.

  2. Pulls the LIVE service-layer definition (`{serviceUrl}/{layerId}?f=json`) for
     the things the cached `_data.json` does NOT carry:
        - drawingInfo / renderer  (the symbology -- often defined ONLY at the
          service level, not in the item data)
        - the full field list + types  (for SQL-name / field-parity checks)
        - geometryType, objectIdField, globalIdField, hasAttachments
        - record count, extent, spatial reference, maxRecordCount
     The service URL and the layer id are DERIVED LIVE from the item (item.url +
     the service's layers[] list), not hardcoded. The renderer block is written to
     its own file so Step 6 can re-apply it.

  3. Resolves the destination feature-class NAME per the agreed naming rule, checking
     the target SDE for collisions:
        a. use the item property `name`;
        b. if empty OR it already exists in the target GDB, use the URL segment
           after `/rest/services/` and before the last `/`;
        c. if that still exists, append `_1`, `_2`, ... until free.

It prints a Step-1 report and writes a JSON summary the downstream steps read
(Step 3 stage-local, Step 3c SDE load -- both chain off `<id>_step1_report.json`).

================================================================================
HOW TO RUN
================================================================================
Run inside the ArcGIS Pro conda env. The live service pull authenticates with stored/entered
AGOL credentials FIRST (Windows Credential Manager via credential_store, or prompt); the active
GIS("pro") session is used only as a fallback if the credentials don't work. The destination-name
check uses arcpy + the target .sde.

    python migration_poc_step1_inspect.py                 # default POC item (CSV row)
    python migration_poc_step1_inspect.py <itemId>        # any item id present in the CSV

The target SDE / database / schema come from the CSV row for <itemId>. Edit the
CONFIG block below only to override the CSV (e.g. point at a different CSV, or force
a service URL / layer id).

================================================================================
WHAT IT WRITES  (to Migrate/Output)
================================================================================
  <id>_layer<lid>_service.json   -- the full live service-layer definition
  <id>_layer<lid>_renderer.json  -- just drawingInfo (symbology source for Step 6)
  <id>_step1_report.json         -- the resolved facts (dest name, fields, flags)
"""

import os
import re
import sys
import csv
import json

from arcgis.gis import GIS

# This file lives in ArcGIS Admin\docs\plan\completed -> climb to the ArcGIS Admin root
# (completed -> plan -> docs -> ArcGIS Admin) to find Migrate\Input\ItemsToMigratePhase1.csv
# and credential_store.py (which lives in the ArcGIS Admin root).
ARCGIS_ADMIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ARCGIS_ADMIN_DIR not in sys.path:
    sys.path.insert(0, ARCGIS_ADMIN_DIR)
import credential_store  # noqa: E402

# ----------------------------------------------------------------------------
# CONFIG  (defaults are this POC's item; the SDE/db/schema come from the CSV row)
# ----------------------------------------------------------------------------
ITEM_ID = sys.argv[1] if len(sys.argv) > 1 else "c" # 4d6aff488b9e48bf8a1f204c05d6f53d

# CSV that supplies, per item: target SDE connection file, target database, target schema.
# Columns: "AGOL Item ID","AGOL Title","AGOL Item Type","AGOL_Owner","Target Database",
#          "Target Database Schema",...,"Connection_Filepath".
# Honor the run-wide manifest override (MIGRATION_MANIFEST_PATH) that the batch/pipeline driver exports, so a
# custom work-list CSV reaches this child too; else the canonical Migrate\Input\ItemsToMigratePhase1.csv.
CSV_PATH = (os.environ.get("MIGRATION_MANIFEST_PATH") or "").strip() or \
    os.path.join(ARCGIS_ADMIN_DIR, "Migrate", "Input", "ItemsToMigratePhase1.csv")

# Optional overrides (leave blank/None to derive from the CSV + the live item).
SERVICE_URL_OVERRIDE = ""     # force the FeatureServer root; else item.url
LAYER_ID_OVERRIDE = None      # force the sublayer id; else the service's single/first layer
TARGET_SDE_OVERRIDE = ""      # force the .sde; else the CSV Connection_Filepath
TARGET_DB_OVERRIDE = ""       # force the database; else the CSV Target Database
TARGET_SCHEMA_OVERRIDE = ""   # force the schema; else the CSV Target Database Schema

# Where GetAllArcGISServiceMetadata.py dumped this item's cached JSON.
METADATA_DUMP_DIR = r"T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\DataDump"

# Source AGOL sign-in. Stored/entered credentials are tried FIRST (see connect_source); the active
# ArcGIS Pro session is used only as a fallback if the credentials don't work.
AGOL_URL = "https://rrg.maps.arcgis.com/"
AGOL_USERNAME = ""   # optionally pre-fill the username; left blank -> resolved from the store / prompted

OUTPUT_DIR = os.path.join(ARCGIS_ADMIN_DIR, "Migrate", "Output")


def connect_source():
    """Connect to the source AGOL org via the shared credential_store.connect(): stored 'agol' credential
    FIRST, then the active ArcGIS Pro session, then a username/password prompt."""
    return credential_store.connect(AGOL_URL, key="agol", default_username=AGOL_USERNAME, log=print)


def read_csv_row(item_id):
    """Return the CSV row dict for item_id (matched on 'AGOL Item ID'), or {} if absent."""
    if not os.path.isfile(CSV_PATH):
        print(f"  !! input CSV not found: {CSV_PATH}")
        return {}
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if (row.get("AGOL Item ID") or "").strip().lower() == item_id.lower():
                return row
    print(f"  !! item id {item_id} not found in {os.path.basename(CSV_PATH)}")
    return {}


def find_cached_file(item_id, kind):
    """Locate a cached DataDump file for the item. `kind` is 'description', 'data',
    or 'get'. Filenames look like AGOL_<id>_<kind>_<title>.json or
    ArcGIS_Items_AGOL_<id>_get.json -- match loosely on id + kind."""
    if not os.path.isdir(METADATA_DUMP_DIR):
        return None
    for fn in os.listdir(METADATA_DUMP_DIR):
        low = fn.lower()
        if item_id.lower() in low and low.endswith(".json") and f"_{kind}" in low:
            return os.path.join(METADATA_DUMP_DIR, fn)
    return None


def load_json(path):
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return None


def name_from_service_url(url):
    """Segment after '/rest/services/' and before the last '/'.
    e.g. '.../rest/services/Change_in_SW_Supply_by_2030/FeatureServer' -> 'Change_in_SW_Supply_by_2030'."""
    m = re.search(r"/rest/services/(.+)/[^/]+$", url)
    return m.group(1).split("/")[-1] if m else None


def choose_layer_id(svc_root):
    """Pick the layer id to migrate from the FeatureServer root JSON.
    Returns (layer_id, layers, tables). POC handles a single feature layer; if a service
    has multiple layers/tables it warns and uses the first LAYER, leaving per-layer
    enumeration to the manifest (Phase 1)."""
    layers = svc_root.get("layers", []) or []
    tables = svc_root.get("tables", []) or []
    if LAYER_ID_OVERRIDE is not None:
        return LAYER_ID_OVERRIDE, layers, tables
    if not layers:
        return None, layers, tables
    if len(layers) > 1 or tables:
        print(f"  !! service has {len(layers)} layer(s) + {len(tables)} table(s); "
              f"the POC chain processes ONE layer. Using the first layer (id {layers[0].get('id')}). "
              f"Use the manifest (Phase 1) for multi-layer services or set LAYER_ID_OVERRIDE.")
    return layers[0].get("id"), layers, tables


def fc_exists(workspace, db, schema, name):
    """True if {db}.{schema}.{name} exists in the SDE workspace."""
    import arcpy
    fq = f"{db}.{schema}.{name}"
    return arcpy.Exists(os.path.join(workspace, fq))


def resolve_dest_name(item_name, service_url, workspace, db, schema):
    """Apply the agreed naming rule; returns (final_name, how)."""
    candidates = []
    if item_name:
        candidates.append(("item name", item_name))
    svc = name_from_service_url(service_url)
    if svc:
        candidates.append(("service url segment", svc))

    base = None
    for how, cand in candidates:
        if not fc_exists(workspace, db, schema, cand):
            return cand, how
        base = base or cand  # remember first candidate for suffixing

    # everything taken -> increment a suffix on the first base
    base = base or (item_name or svc)
    i = 1
    while fc_exists(workspace, db, schema, f"{base}_{i}"):
        i += 1
    return f"{base}_{i}", f"incremented (base '{base}' was taken)"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"=== POC Step 1: inspect source + resolve dest name for {ITEM_ID} ===\n")

    # --- 0. CSV row -> target SDE / db / schema ----------------------------
    row = read_csv_row(ITEM_ID)
    target_sde = TARGET_SDE_OVERRIDE or (row.get("Connection_Filepath") or "").strip()
    target_db = TARGET_DB_OVERRIDE or (row.get("Target Database") or "").strip()
    target_schema = TARGET_SCHEMA_OVERRIDE or (row.get("Target Database Schema") or "").strip()
    csv_title = (row.get("AGOL Title") or "").strip()
    csv_owner = (row.get("AGOL_Owner") or "").strip()
    print(f"CSV target    : {target_db}.{target_schema}  via  {target_sde}")
    if csv_title:
        print(f"CSV title/owner: {csv_title!r}  /  {csv_owner!r}")
    if not (target_sde and target_db and target_schema):
        print("!! missing target SDE / database / schema (CSV row absent or incomplete, "
              "and no CONFIG override). Stopping.")
        return

    # --- 1. cached metadata -------------------------------------------------
    desc = load_json(find_cached_file(ITEM_ID, "description")) or \
        load_json(find_cached_file(ITEM_ID, "get"))
    data = load_json(find_cached_file(ITEM_ID, "data"))
    item_name = (desc or {}).get("name")
    item_title = (desc or {}).get("title")
    has_popup = bool(
        data and any("popupInfo" in lyr for lyr in data.get("layers", []))
    )

    # --- 2a. connect + derive the service URL from the live item -----------
    gis = connect_source()
    me = gis.users.me
    print(f"\nConnected to {gis.url} as {me.username if me else '?'} for the live pull")
    item = gis.content.get(ITEM_ID)
    if item is None:
        print(f"!! item {ITEM_ID} not found / not accessible with this session. Stopping.")
        return
    if item.type != "Feature Service":
        print(f"  !! item type is '{item.type}', expected 'Feature Service' -- proceeding, but verify.")
    # Prefer the live item name/title (CSV/cached are fallbacks for the dest-name rule).
    item_name = item_name or getattr(item, "name", None)
    item_title = item.title or item_title or csv_title
    service_url = SERVICE_URL_OVERRIDE or (item.url or "")
    if not service_url:
        print(f"!! item has no service url; cannot inspect layers. Stopping.")
        return
    print(f"item name (property): {item_name!r}   title: {item_title!r}")
    print(f"pop-ups captured in _data.json: {has_popup}")
    print(f"service url   : {service_url}")

    # --- 2b. enumerate layers, choose the one to migrate -------------------
    svc_root = gis._con.get(service_url, {"f": "json"})
    if not isinstance(svc_root, dict) or "error" in (svc_root or {}):
        print(f"!! could not read service root {service_url}: {svc_root}")
        return
    layer_id, layers, tables = choose_layer_id(svc_root)
    if layer_id is None:
        print(f"!! no feature layers found on {service_url} "
              f"(layers={len(layers)}, tables={len(tables)}). Stopping.")
        return
    print(f"layers/tables : {len(layers)} layer(s), {len(tables)} table(s)  -> migrating layer id {layer_id}")

    # --- 2c. live service-layer definition ---------------------------------
    layer_url = f"{service_url}/{layer_id}"
    svc = gis._con.get(layer_url, {"f": "json"})
    if not isinstance(svc, dict) or "error" in (svc or {}):
        print(f"!! could not read {layer_url}: {svc}")
        return

    svc_path = os.path.join(OUTPUT_DIR, f"{ITEM_ID}_layer{layer_id}_service.json")
    with open(svc_path, "w", encoding="utf-8") as fh:
        json.dump(svc, fh, indent=2, ensure_ascii=False)

    drawing_info = svc.get("drawingInfo")
    renderer = (drawing_info or {}).get("renderer", {})
    fields = svc.get("fields", [])
    sr = (svc.get("extent", {}) or {}).get("spatialReference")
    print(f"\nservice layer name: {svc.get('name')}   geometry: {svc.get('geometryType')}")
    print(f"objectIdField: {svc.get('objectIdField')}   globalIdField: {svc.get('globalIdField') or '(none)'}")
    print(f"hasAttachments: {svc.get('hasAttachments')}   spatialReference: {sr}")
    print(f"renderer: type={renderer.get('type')} "
          f"field={renderer.get('field') or renderer.get('field1') or '(n/a)'}  "
          f"{'(NO drawingInfo on service)' if not drawing_info else ''}")
    print(f"field count: {len(fields)}")

    if drawing_info:
        rend_path = os.path.join(OUTPUT_DIR, f"{ITEM_ID}_layer{layer_id}_renderer.json")
        with open(rend_path, "w", encoding="utf-8") as fh:
            json.dump({"drawingInfo": drawing_info}, fh, indent=2, ensure_ascii=False)
        print(f"  -> renderer written: {rend_path}")

    # SQL Server name sanity: flag fields >128 chars or with odd chars
    long_or_odd = [f["name"] for f in fields
                   if len(f["name"]) > 128 or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", f["name"])]
    if long_or_odd:
        print(f"  !! field names to review for SQL Server: {long_or_odd}")

    # --- 3. resolve destination name ---------------------------------------
    print(f"\nresolving dest name against {target_db}.{target_schema} via {target_sde}")
    try:
        dest_name, how = resolve_dest_name(
            item_name, service_url, target_sde, target_db, target_schema)
        print(f"  -> dest feature class: {target_db}.{target_schema}.{dest_name}  (via {how})")
    except Exception as e:
        dest_name, how = None, f"ERROR: {type(e).__name__}: {e}"
        print(f"  !! could not check SDE: {how}")

    # --- report -------------------------------------------------------------
    report = {
        "item_id": ITEM_ID,
        "item_name": item_name,
        "item_title": item_title,
        "item_owner": item.owner or csv_owner,
        "source_service_url": service_url,
        "layer_id": layer_id,
        "layer_count": len(layers),
        "table_count": len(tables),
        "service_layer_name": svc.get("name"),
        "geometry_type": svc.get("geometryType"),
        "object_id_field": svc.get("objectIdField"),
        "global_id_field": svc.get("globalIdField") or None,
        "has_attachments": svc.get("hasAttachments"),
        "spatial_reference": sr,
        "field_count": len(fields),
        "fields": [{"name": f["name"], "type": f["type"].replace("esriFieldType", "")} for f in fields],
        "fields_to_review_for_sql": long_or_odd,
        "renderer_type": renderer.get("type"),
        "renderer_field": renderer.get("field") or renderer.get("field1"),
        "has_service_drawing_info": bool(drawing_info),
        "popups_captured": has_popup,
        "dest_db": target_db,
        "dest_schema": target_schema,
        "dest_feature_class": dest_name,
        "dest_name_resolution": how,
        "target_sde": target_sde,
        "service_json_file": svc_path,
    }
    report_path = os.path.join(OUTPUT_DIR, f"{ITEM_ID}_step1_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"\nStep-1 report written: {report_path}")
    print("Review it, then proceed to Step 3 (stage local + reproject).")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Name: migration_poc_step6_apply_symbology.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-04  (apply_symbology() extracted as an importable function 2026-06-08)

================================================================================
WHAT THIS SCRIPT DOES  (POC Step 6 of the AGOL -> RRGOrg SDE migration)
================================================================================
Apply the SOURCE AGOL item's symbology + pop-ups + default view to a published TARGET
item/service so the target matches the source. REST operations (see how-ago-assistant doc):
  * SERVICE renderer    -> target layer .manager.update_definition({"drawingInfo": ...})
  * ITEM /data          -> item.update(data=...)  (carries renderer + popupInfo; pop-ups live ONLY here)
  * ITEM default extent -> item.update(item_properties={"extent": ...})  (the default view)
  * ITEM tags           -> item.update(item_properties={"tags": ...})  (source AGOL tags + MIGRATION_TAGS;
                           these migration defaults are Enterprise-only -- Phase 8 strips them from the AGOL item)
  * ITEM Terms of Use   -> item.update(item_properties={"licenseInfo": ...})  (source item use constraints;
                           applied regardless of APPLY_TAGS so it also copies on the AGOL re-apply)

MAP IMAGE LAYER sync (decision #9): a referenced publish from Pro creates a Map Service (.../MapServer)
item alongside the Feature Service (.../FeatureServer) item. With SYNC_MAP_IMAGE_LAYER the SAME renderer
+ pop-ups + default view are applied to the Map Image Layer item's /data + extent so the two items match.
Pop-ups + extent sync unconditionally; the renderer override only redraws the map image if the MapServer
reports supportsDynamicLayers=true (else the image keeps the Pro-baked symbology). The sibling item is
auto-discovered (FeatureServer->MapServer url match) unless MAP_IMAGE_ITEM_ID is set.

Source pieces (captured earlier; the cached item _data.json had NO renderer):
  * renderer    : Migrate\Output\<srcItem>_layer<srcLayer>_renderer.json   (live-pulled drawingInfo)
  * pop-ups     : <DataDump>\AGOL_<srcItem>_data_*.json                 (cached popupInfo)
  * item extent : <DataDump>\AGOL_<srcItem>_description_*.json (or _get) (cached item "extent");
                  falls back to a LIVE read from SOURCE_PORTAL_URL when not cached

Layer-id remap: source layer (SRC_LAYER_ID, from the Step-1 report) -> a target layer. A referenced
republish of one feature class assigns the new service layer id 0, while AGOL ids rarely match; a
multi-layer service published by hand keeps the source ids (e.g. 1-22). The target layer is resolved
automatically (TARGET_LAYER_ID = None): the service's only layer; else the layer with the same name as the
source layer; else the layer with the same id. Pass --target-layer <id> to force one. That primary layer
gets the renderer + visibility range + pop-up.

Multi-layer items: every OTHER source layer / table is paired with a target layer / table of the same kind
(by name, then by id, then by service order) and gets ITS OWN renderer + visibility range (from its
Step-1 capture <src>_layer<n>_renderer.json / _service.json) and its own pop-up. Source layer names come
from the Step-1 captures, so this also works after the source was deleted; the live source item is only
read when a pop-up belongs to a layer / table Step 1 did not capture.

Backups: current item /data and current target-layer drawingInfo are written to Migrate/Output/
before anything is changed.

Field check: a renderer references a field, and popupInfo references fieldInfos. This script reports
any referenced fields missing on the TARGET layer; with PRUNE_STALE_FIELDINFOS=True it drops popup
fieldInfos that point at non-existent fields (the captured AGOL pop-up lists many fields the trimmed
service no longer has). Default False = faithful copy of the source pop-up (dead refs are ignored by ArcGIS).
Pop-up Arcade expressions ('expression/<name>' fieldInfos + expressionInfos) are not layer fields and are
never pruned. A field the SDE load renamed (an SQL Server reserved word -- LEVEL, PRIMARY, COUNT, USE, ...
becomes LEVEL_ ...) is RENAMED throughout the pop-up first (fieldInfos, '{LEVEL}' text tokens, Arcade
'$feature.LEVEL'), so it is kept instead of pruned.

================================================================================
IMPORTABLE  apply_symbology(...)
================================================================================
The core is exposed as apply_symbology(gis, target_item_id, src_item_id, ...) so other phases can call
it without shelling out. PublishFromDBToFeatureService.py imports it and calls it best-effort at the end
of each publish loop, to symbolize the Enterprise item (+ sync its Map Image Layer) in the same run.
`gis` must already be connected to the TARGET portal. src_layer_id auto-resolves from the Step-1 report
when not given. main() just wires CONFIG/CLI to the same function.

================================================================================
HOW TO RUN  (standalone)
================================================================================
Run in the ArcGIS Pro conda env. Connects to the ENTERPRISE portal (Pro session if it is that
portal, else username/password). updateDefinition needs publisher/admin on the federated server;
item.update needs item ownership/admin.

    python migration_poc_step6_apply_symbology.py

PHASE 8 (re-apply against the new AGOL by-reference item): pass --agol -- a PRESET that targets the AGOL
org with APPLY="item", APPLY_TAGS=False, and SYNC_MAP_IMAGE_LAYER=False, so NO CONFIG edits are needed.
It is ledger-driven, re-applying to every row's agol_byref_item_id; add an item id to limit to one:

    python migration_poc_step6_apply_symbology.py --agol
    python migration_poc_step6_apply_symbology.py <new_agol_item_id> --agol

Granular overrides: --apply both|item|service, --no-tags, --no-map-sibling, --no-thumbnail,
--map-image-id <id>, --target-portal-url <url>, --target-layer <id> (default: resolved automatically).
"""

import os
import re
import sys
import copy
import json
import types
import getpass
import datetime as dt

from arcgis.gis import GIS

# This script lives in ArcGIS Admin\docs\plan\completed. The helpers moved: migration_status_ledger.py is in
# ArcGIS Admin\Migrate and credential_store.py is in the ArcGIS Admin root -- add both to sys.path.
_ADMIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for _p in (_ADMIN_DIR, os.path.join(_ADMIN_DIR, "Migrate")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import migration_status_ledger as ledger_mod
import credential_store
# Step 6b thumbnail regeneration, callable so the symbology apply also refreshes the thumbnail in one pass
# (the thumbnail renders with the item /data renderer + is framed to the default view this step just set).
# Best-effort import (RegenerateItemThumbnails.py is in the ArcGIS Admin root, on sys.path above).
try:
    from RegenerateItemThumbnails import regenerate_thumbnail
except Exception as _thumb_imp_err:
    regenerate_thumbnail = None

# file + console logging (replaces print so every run leaves an audit trail under Output/)
logger = ledger_mod.setup_logging(__file__)


# The source item_id currently being processed. Set at the top of each main-loop iteration so log_message()
# can attribute any 'error'-level log to the right migration-ledger row. Blank during setup/connect (and when
# apply_symbology is imported + called by another script, e.g. the publish step, which owns its own ledger
# capture) so those errors are NOT recorded against any item here.
current_src_id = ''
# Reentrancy guard + per-run de-dupe so the auto-record-on-error in log_message neither loops nor appends
# the same message to a row's error column more than once.
_recording_ledger_error = False
_recorded_ledger_errors = set()


def log_message(msg, level="info"):
    """Log to file AND console. level in info|warning|error|debug (defaults to info)."""
    getattr(logger, level if level in ("info", "warning", "error", "debug") else "info")(msg)
    if level == "error":
        _record_error_to_ledger(msg)


def _record_error_to_ledger(message):
    """Best-effort: when an 'error' is logged WHILE a specific item's symbology is being applied, append it to
    that item's migration-status-ledger row (current_src_id). CENTRALIZES the 'on error, record against the
    row' pattern so individual error sites don't each need their own record_error block. Skipped when no item
    is in flight (setup errors, or import-by-another-script) or the ledger helper is unavailable; de-duped per
    run + reentrancy-guarded; never raises (logging must not depend on the ledger)."""
    global _recording_ledger_error
    if ledger_mod is None or not current_src_id or _recording_ledger_error:
        return
    key = (current_src_id.lower(), str(message)[:300])
    if key in _recorded_ledger_errors:
        return
    _recording_ledger_error = True
    try:
        ledger_mod.record_error(current_src_id, str(message)[:300], phase="symbology", logger=logger)
        _recorded_ledger_errors.add(key)
    except Exception:
        pass   # never let ledger recording break logging
    finally:
        _recording_ledger_error = False


# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
SRC_ITEM_ID = "4d6aff488b9e48bf8a1f204c05d6f53d"   # source AGOL item (single-mode fallback only; ledger
                                                   # mode reads the source per row)
SRC_LAYER_ID = 1                                    # source layer id (single-mode fallback; ledger mode
                                                   # auto-resolves per source item from the Step-1 report)
# ----------------------------------------------------------------------------
# CLI flags  (so the Phase-8 AGOL re-apply needs NO CONFIG edits -- see --agol)
# ----------------------------------------------------------------------------
#   --agol            PRESET for the Phase-8 re-apply against the new AGOL by-reference item: target the
#                     AGOL org, apply="item", apply_tags=False, sync_map_image_layer=False (no Map Image
#                     sibling on AGOL). Replaces hand-editing the CONFIG below.
#   --apply MODE      override APPLY (both|item|service)   --no-tags / --no-map-sibling / --no-thumbnail
#   --map-image-id ID explicit Map Image Layer item id    --target-portal-url URL  override target portal
#   --target-layer N  force the target layer for the primary source layer (default: resolved automatically)
# A leading non-flag argument is still the explicit single target item id (ledger-driven otherwise).
AGOL_ORG_URL = "https://rrg.maps.arcgis.com"        # the AGOL org (also the source org, below)


def _has_flag(name):
    return name in sys.argv[1:]


def _flag_val(name, default=""):
    argv = sys.argv[1:]
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            return argv[i + 1].strip()
    return default


def _positional_target():
    """First bare argument that is neither a flag nor a flag's value -> the explicit single target id."""
    _value_flags = {"--apply", "--map-image-id", "--target-portal-url", "--target-layer"}
    skip = False
    for a in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if a.startswith("--"):
            if a in _value_flags:
                skip = True
            continue
        return a.strip()
    return ""


_AGOL_PRESET = _has_flag("--agol")
# LEDGER-DRIVEN by default: main() applies symbology to EVERY ledger row -- the Enterprise item
# (enterprise_item_id) when targeting the portal, or the AGOL by-reference item (agol_byref_item_id) with
# --agol. A leading non-flag CLI arg limits to that one target (its source resolved from the ledger).
TARGET_ITEM_ID = _positional_target()
# Target layer for the primary source layer. None = resolve automatically (the only layer, else the same
# name, else the same id -- see resolve_target_layer); --target-layer N forces one.
TARGET_LAYER_ID = int(_flag_val("--target-layer")) if _flag_val("--target-layer").isdigit() else None

PORTAL_URL = "https://maps.rrgnbs.com/arcgisportal"
PORTAL_USERNAME = ""        # blank -> prompted (not SSO) when Pro session isn't this portal

# Target portal for the item /data + extent edits. --agol targets the AGOL org; --target-portal-url
# overrides outright; otherwise the Enterprise portal. APPLY_TAGS is forced off by --agol (the AGOL item's
# tags were already set at share-back by AddItemWithStoredCredentials.py).
TARGET_PORTAL_URL = _flag_val("--target-portal-url") or (AGOL_ORG_URL if _AGOL_PRESET else PORTAL_URL)
APPLY_TAGS = not (_AGOL_PRESET or _has_flag("--no-tags"))   # False -> leave target item tags untouched

# Source AGOL org -- only used as a LIVE fallback to read the source item's default extent
# when it isn't in the cached description JSON. Pro session is used if it IS this org,
# otherwise an anonymous connection (works for public items).
SOURCE_PORTAL_URL = AGOL_ORG_URL

APPLY = (_flag_val("--apply") or ("item" if _AGOL_PRESET else "both")).lower()   # "service" | "item" | "both"
PRUNE_STALE_FIELDINFOS = True   # True = drop popup fieldInfos for fields missing on the target

# Map Image Layer sync (decision #9): a referenced publish from Pro creates a Map Service
# (.../MapServer) item alongside the Feature Service (.../FeatureServer) item. Keep them in sync by
# applying the SAME renderer + pop-ups + default view to the Map Image Layer item's /data + extent.
#   SYNC_MAP_IMAGE_LAYER = True  -> also update the sibling Map Image Layer item
#   MAP_IMAGE_ITEM_ID    = ""    -> auto-discover (swap FeatureServer->MapServer, match portal url);
#                                   set an explicit id to skip the search.
# NOTE: pop-ups + extent sync unconditionally; the renderer override only redraws the map image if the
# MapServer reports supportsDynamicLayers=true (else the image keeps the Pro-baked symbology).
SYNC_MAP_IMAGE_LAYER = not (_AGOL_PRESET or _has_flag("--no-map-sibling"))
MAP_IMAGE_ITEM_ID = _flag_val("--map-image-id")

# Step 6b thumbnail: regenerate the item thumbnail right after applying symbology + default view (the
# thumbnail renders with the item /data renderer and is framed to the extent this step sets, so this is
# the correct moment). Best-effort -- a thumbnail failure never affects the symbology apply. The same PNG
# is applied to the Map Image sibling when SYNC_MAP_IMAGE_LAYER is on. Set False to skip (run
# RegenerateItemThumbnails.py manually instead).
REGEN_THUMBNAIL = not _has_flag("--no-thumbnail")

# Tags (decision #10): the Enterprise item gets the source AGOL tags + these migration defaults.
# These are ENTERPRISE-ONLY -- Phase 8 strips them so they do not propagate to the AGOL by-reference item.
MIGRATION_TAGS = ["Migrated from AGOL", "Migrated"]

OUTPUT_DIR = os.path.join(_ADMIN_DIR, "Migrate", "Output")
# Migration ledger path + writes are handled by migration_status_ledger (ledger_mod.set_state); the
# canonical path resolves to OUTPUT_DIR\migration_status_ledger.csv (env MIGRATION_LEDGER_PATH overrides).
METADATA_DUMP_DIR = r"T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\DataDump"


def find_cached_data(item_id):
    """Locate the cached item _data JSON (AGOL_<id>_data_*.json) in the DataDump."""
    if os.path.isdir(METADATA_DUMP_DIR):
        for fn in os.listdir(METADATA_DUMP_DIR):
            low = fn.lower()
            if item_id.lower() in low and "_data" in low and low.endswith(".json"):
                return os.path.join(METADATA_DUMP_DIR, fn)
    return None


def find_cached_desc(item_id):
    """Locate the cached item description/_get JSON in the DataDump. This carries the item-level
    'extent' (the default view), as [[xmin,ymin],[xmax,ymax]] in WGS84. Excludes the _data file."""
    if os.path.isdir(METADATA_DUMP_DIR):
        for fn in os.listdir(METADATA_DUMP_DIR):
            low = fn.lower()
            if (item_id.lower() in low and low.endswith(".json")
                    and "_data" not in low and ("_description" in low or "_get" in low)):
                return os.path.join(METADATA_DUMP_DIR, fn)
    return None


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_src_layer_id(src_item_id):
    """Determine the source layer id when a caller does not pass one: prefer the Step-1 report
    (`<src>_step1_report.json` -> layer_id), else parse it from a captured renderer filename
    (`<src>_layer<n>_renderer.json`). Falls back to 0."""
    rpt_path = os.path.join(OUTPUT_DIR, f"{src_item_id}_step1_report.json")
    if os.path.isfile(rpt_path):
        try:
            return int(load_json(rpt_path).get("layer_id", 0))
        except Exception:
            pass
    if os.path.isdir(OUTPUT_DIR):
        for fn in os.listdir(OUTPUT_DIR):
            m = re.match(rf"{re.escape(src_item_id)}_layer(\d+)_renderer\.json$", fn)
            if m:
                return int(m.group(1))
    return 0


def connect_portal(portal_url):
    """Connect to the target portal via the shared credential_store.connect(): stored credential FIRST
    (key by host: 'agol' for *.arcgis.com, else 'portal'), then the active ArcGIS Pro session, then a
    username/password prompt."""
    return credential_store.connect(portal_url, default_username=PORTAL_USERNAME, log=log_message)


def fetch_source_item(src_item_id, source_portal_url):
    """Live fallback to read source item properties (default extent + tags) when the cached
    description JSON is missing or incomplete. Uses the active Pro session if it IS the source org,
    otherwise an anonymous connection (works for public items). Returns the Item or None."""
    host = source_portal_url.split("//")[-1].split("/")[0].lower()
    src_gis = None
    try:
        pro = GIS("pro")
        if pro.url and host in pro.url.lower() and pro.users.me:
            src_gis = pro
            log_message(f"   (live source: using Pro session {pro.url})")
    except Exception:
        pass
    if src_gis is None:
        try:
            src_gis = GIS(source_portal_url)   # anonymous; resolves public items
            log_message(f"   (live source: anonymous connection to {source_portal_url})")
        except Exception as e:
            log_message(f"   (live source: could not connect to source org: {e})")
            return None
    try:
        src_item = src_gis.content.get(src_item_id)
        if src_item is None:
            log_message(f"   (live source: item {src_item_id} not accessible on {src_gis.url} "
                  f"-- not public? sign Pro into the source org)")
        return src_item
    except Exception as e:
        log_message(f"   (live source: lookup failed: {e})")
        return None


# fieldInfos that are NOT layer fields and so are never "stale": a pop-up Arcade expression is listed as
# 'expression/<name>' (its code lives in the popupInfo's expressionInfos, which is copied as-is)
_NON_FIELD_PREFIXES = ("expression/",)


def _is_layer_field_ref(name):
    return not (name or "").startswith(_NON_FIELD_PREFIXES)


def popup_field_names(popup):
    """All LAYER-field fieldName values referenced in a popupInfo (top-level + popupElements); Arcade
    expression entries ('expression/...') are not layer fields and are left out."""
    names = set()
    for fi in (popup.get("fieldInfos") or []):
        if fi.get("fieldName") and _is_layer_field_ref(fi["fieldName"]):
            names.add(fi["fieldName"])
    for el in (popup.get("popupElements") or []):
        for fi in (el.get("fieldInfos") or []):
            if fi.get("fieldName") and _is_layer_field_ref(fi["fieldName"]):
                names.add(fi["fieldName"])
    return names


def prune_popup(popup, valid_names):
    """Drop fieldInfos whose fieldName is not in valid_names (both top-level and popupElements). Arcade
    expression entries ('expression/...') are always kept -- they are not layer fields."""
    def keep(fi):
        return fi.get("fieldName") in valid_names or not _is_layer_field_ref(fi.get("fieldName"))
    if popup.get("fieldInfos"):
        popup["fieldInfos"] = [fi for fi in popup["fieldInfos"] if keep(fi)]
    for el in (popup.get("popupElements") or []):
        if el.get("fieldInfos"):
            el["fieldInfos"] = [fi for fi in el["fieldInfos"] if keep(fi)]
    return popup


def reserved_renames(target_fields):
    """{X: X_} for every target field 'X_' whose 'X' the target lacks (compared case-insensitively): loading
    into SDE renames a field named like an SQL Server reserved word (LEVEL, PRIMARY, COUNT, USE, ...) to
    '<name>_', so the source pop-up's LEVEL is the target's LEVEL_. Harmless for a field that really ends in
    '_': a reference to the missing 'X' would only have been pruned."""
    upper = {n.upper() for n in target_fields}
    return {n[:-1]: n for n in target_fields if n.endswith("_") and len(n) > 1 and n[:-1].upper() not in upper}


_FIELD_KEYS = ("fieldName", "field", "normalizeField", "tooltipField")


def rename_popup_fields(popup, renames):
    """A copy of popupInfo with every reference to a renamed field pointed at its new name: fieldInfos /
    element fieldNames (+ field / normalizeField / tooltipField, chart 'fields' lists), '{X}' tokens in any text
    (title, description, text elements, media captions), and Arcade '$feature.X' / '$feature["X"]' (expression
    infos + Arcade elements). Names match case-insensitively. Returns (popup, [X -> X_ actually used])."""
    if not renames:
        return popup, []
    by_upper = {k.upper(): v for k, v in renames.items()}
    alt = "|".join(re.escape(k) for k in sorted(renames, key=len, reverse=True))
    token_re = re.compile(r"\{(" + alt + r")\}", re.I)
    dot_re = re.compile(r"(\$feature\s*\.\s*)(" + alt + r")\b", re.I)
    idx_re = re.compile(r"(\$feature\s*\[\s*)([\"'])(" + alt + r")\2(\s*\])", re.I)
    used = set()

    def name(v):
        new = by_upper.get(v.upper()) if isinstance(v, str) else None
        if new:
            used.add(v)
        return new or v

    def text(s):
        def sub(rx, repl):
            nonlocal s
            for m in rx.finditer(s):
                used.add(m.group(1) if rx is token_re else (m.group(2) if rx is dot_re else m.group(3)))
            s = rx.sub(repl, s)
        sub(token_re, lambda m: "{" + by_upper[m.group(1).upper()] + "}")
        sub(dot_re, lambda m: m.group(1) + by_upper[m.group(2).upper()])
        sub(idx_re, lambda m: m.group(1) + m.group(2) + by_upper[m.group(3).upper()] + m.group(2) + m.group(4))
        return s

    def walk(o, key=None):
        if isinstance(o, dict):
            return {k: (name(v) if k in _FIELD_KEYS else walk(v, k)) for k, v in o.items()}
        if isinstance(o, list):
            return [name(v) if key == "fields" and isinstance(v, str) else walk(v, key) for v in o]
        if isinstance(o, str):
            return text(o)
        return o

    new = walk(popup)
    return new, sorted(f"{k} -> {by_upper[k.upper()]}" for k in used)


def source_popups(data_path):
    """{(kind, source id): popupInfo} for every layer / table in the cached source item /data that has one."""
    out = {}
    if data_path:
        data = load_json(data_path)
        for kind, key in (("layer", "layers"), ("table", "tables")):
            for lyr in data.get(key) or []:
                if lyr.get("popupInfo"):
                    out[(kind, int(lyr.get("id", -1)))] = lyr["popupInfo"]
    return out


def _layer_key(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def pair_layers(src, tgt):
    """Pair source and target layers (or tables) of ONE kind: by normalized name first, then by the same id
    (a hand-published multi-layer service keeps the source ids), then the rest by service order (a referenced
    republish renumbers the ids). Returns [(src, tgt)]."""
    by_name = {}
    for t in tgt:
        by_name.setdefault(_layer_key(t.properties.name), t)
    paired, used = {}, set()
    for s in src:
        t = by_name.get(_layer_key(s.properties.name))
        if t is not None and id(t) not in used:
            paired[id(s)] = t
            used.add(id(t))
    by_id = {int(t.properties.id): t for t in tgt}
    for s in src:
        t = by_id.get(int(s.properties.id))
        if id(s) not in paired and t is not None and id(t) not in used:
            paired[id(s)] = t
            used.add(id(t))
    rest = iter([t for t in tgt if id(t) not in used])
    for s in src:
        if id(s) not in paired:
            t = next(rest, None)
            if t is not None:
                paired[id(s)] = t
    return [(s, paired[id(s)]) for s in src if id(s) in paired]


def _layer_ns(layer_id, name):
    """A stand-in with the .properties.id / .properties.name shape pair_layers expects."""
    return types.SimpleNamespace(properties=types.SimpleNamespace(id=int(layer_id), name=name or ""))


def archived_source_layers(src_item_id):
    """{"layers": [...], "tables": [...]} of the source layers / tables Step 1 captured
    (<src>_layer<n>_service.json: id, name, type), sorted by id. Works after the source was deleted."""
    out = {"layers": [], "tables": []}
    if not os.path.isdir(OUTPUT_DIR):
        return out
    pat = re.compile(rf"{re.escape(src_item_id)}_layer(\d+)_service\.json$", re.IGNORECASE)
    for fn in os.listdir(OUTPUT_DIR):
        m = pat.match(fn)
        if not m:
            continue
        try:
            svc = load_json(os.path.join(OUTPUT_DIR, fn))
        except Exception:
            continue
        key = "tables" if (svc.get("type") or "").lower() == "table" else "layers"
        out[key].append(_layer_ns(svc.get("id", m.group(1)), svc.get("name")))
    for v in out.values():
        v.sort(key=lambda l: l.properties.id)
    return out


def source_layer_definition(src_item_id, src_id):
    """layerDefinition {drawingInfo, minScale, maxScale} of ONE source layer from its Step-1 captures
    (<src>_layer<n>_renderer.json, else the drawingInfo in _service.json), or {} when none was captured."""
    ld = {}
    svc = {}
    svc_path = os.path.join(OUTPUT_DIR, f"{src_item_id}_layer{src_id}_service.json")
    if os.path.isfile(svc_path):
        svc = load_json(svc_path)
    rend_path = os.path.join(OUTPUT_DIR, f"{src_item_id}_layer{src_id}_renderer.json")
    drawing_info = load_json(rend_path).get("drawingInfo") if os.path.isfile(rend_path) else None
    drawing_info = drawing_info or svc.get("drawingInfo")
    if drawing_info:
        ld["drawingInfo"] = drawing_info
    for k in ("minScale", "maxScale"):
        if svc.get(k) is not None:
            ld[k] = svc[k]
    return ld


def renderer_field_names(drawing_info):
    """The layer fields a renderer is keyed on (field, field1-3)."""
    rnd = (drawing_info or {}).get("renderer", {}) or {}
    return {rnd.get("field"), rnd.get("field1"), rnd.get("field2"), rnd.get("field3")} - {None, ""}


def resolve_target_layer(by_id, target_layer_id, src_layer_id, src_layer_name):
    """The target layer id that gets the PRIMARY source layer's renderer + pop-up, as (id, how), or
    (None, why). An explicit target_layer_id must exist. Otherwise: the service's only layer; else the layer
    with the source layer's name; else the layer with the source layer's id. No blind fallback to layer 0 on
    a multi-layer service -- that is what put the wrong layer's style on layer 0."""
    if target_layer_id is not None:
        if target_layer_id in by_id:
            return target_layer_id, "given"
        return None, f"given id {target_layer_id} not in service layers {sorted(by_id)}"
    if len(by_id) == 1:
        return next(iter(by_id)), "the service's only layer"
    key = _layer_key(src_layer_name)
    if key:
        for tid, lyr in by_id.items():
            if _layer_key(lyr.properties.name) == key:
                return tid, f"same name as source layer {src_layer_id}"
    if src_layer_id in by_id:
        return src_layer_id, f"same id as source layer {src_layer_id}"
    return None, (f"no target layer matches source layer {src_layer_id} '{src_layer_name}' by name or id "
                  f"(service layers {sorted(by_id)}) -- pass --target-layer <id>")


def other_layer_blocks(item, src_item_id, src_layer_id, target_layer_id, data_path, source_portal_url,
                       prune_stale_fieldinfos):
    """Item /data blocks {"layers": [...], "tables": [...]} for every source layer / table OTHER than the
    primary one. Each is paired with a target layer / table of the same kind (pair_layers); a layer block
    carries ITS OWN renderer + visibility range (source_layer_definition) and its pop-up, a table block its
    pop-up. Pop-ups are pruned against THAT target's own fields. Source names come from the Step-1 captures
    (archived_source_layers); the live source item is read only when a pop-up belongs to a layer / table
    Step 1 did not capture."""
    out = {"layers": [], "tables": []}
    pops = source_popups(data_path)
    pops.pop(("layer", src_layer_id), None)
    src_lists = archived_source_layers(src_item_id)
    captured = {("layer", l.properties.id) for l in src_lists["layers"]} | \
               {("table", l.properties.id) for l in src_lists["tables"]}
    if not set(pops) <= captured:
        live = fetch_source_item(src_item_id, source_portal_url)
        if live is not None:
            src_lists = {key: list(getattr(live, key, None) or []) for key in ("layers", "tables")}
        else:
            log_message(f"!! source item not readable live -- pairing only the {len(captured)} layer(s) / table(s) "
                        f"Step 1 captured", "warning")
    for kind, key in (("layer", "layers"), ("table", "tables")):
        src = [l for l in src_lists[key] if not (kind == "layer" and int(l.properties.id) == src_layer_id)]
        tgt = [l for l in (getattr(item, key, None) or [])
               if not (kind == "layer" and int(l.properties.id) == target_layer_id)]
        for s, t in pair_layers(src, tgt):
            s_id, t_id = int(s.properties.id), int(t.properties.id)
            t_fields = {f["name"] for f in (t.properties.fields or [])}
            block, parts = {"id": t_id}, []
            if kind == "layer":
                ld = source_layer_definition(src_item_id, s_id)
                if ld:
                    block["layerDefinition"] = ld
                if ld.get("drawingInfo"):
                    rtype = (ld["drawingInfo"].get("renderer") or {}).get("type")
                    parts.append(f"renderer ({rtype})")
                    missing = renderer_field_names(ld["drawingInfo"]) - t_fields
                    if missing:
                        log_message(f"!! {kind} {t_id}: renderer references field(s) missing on target: {missing}",
                                    "warning")
            popup = pops.pop((kind, s_id), None)
            if popup:
                # a field renamed by the SDE load (reserved word: LEVEL -> LEVEL_) is renamed, not pruned
                popup, used = rename_popup_fields(popup, reserved_renames(t_fields))
                if used:
                    parts.append(f"pop-up field(s) renamed by SDE: {', '.join(used)}")
                if prune_stale_fieldinfos:
                    popup = prune_popup(copy.deepcopy(popup), t_fields)
                block["popupInfo"] = popup
                parts.append("pop-up")
            if parts or "layerDefinition" in block:
                out[key].append(block)
                log_message(f"other {kind:<6}: {s_id} '{s.properties.name}' -> {t_id} '{t.properties.name}'  "
                            f"[{', '.join(parts) or 'visibility range'}]")
    for kind, s_id in sorted(pops):
        log_message(f"!! source {kind} {s_id} has a pop-up but no matching {kind} on the target -- not applied",
                    "warning")
    return out


def find_map_image_item(gis, feature_item, explicit_id=""):
    """Locate the sibling Map Image Layer item for a published Feature Layer item (decision #9).
    A referenced publish from Pro creates a Feature Service (.../FeatureServer) AND a Map Service
    (.../MapServer) sharing the service base url. If explicit_id is given, use it. Otherwise: check item
    relationships first (authoritative when registered), then derive the sibling MapServer url and match it
    against candidates found by BOTH the item title AND the url-derived service name -- portal full-text
    search indexes the title/tags, NOT the url, so a name-only search misses a map whose title differs from
    its service name (e.g. item 'Guayule Historic (v.1)' backed by service 'Guayule_Current_V1'). Kept in
    sync with ReassignMigratedItemOwners.find_backing_map_services."""
    if explicit_id:
        return gis.content.get(explicit_id)
    furl = feature_item.url or ""
    murl = re.sub(r"/FeatureServer(/\d+)?/?$", "/MapServer", furl, flags=re.IGNORECASE)
    if not murl or murl == furl:
        log_message(f"[map-image] could not derive a MapServer url from {furl!r} -- skipping.")
        return None
    target = murl.rstrip("/").lower()

    # Relationships first -- authoritative when the referenced publish registered them.
    for rel in ("Service2Service", "Map2Service", "Service2Layer"):
        for direction in ("forward", "reverse"):
            try:
                for r in (feature_item.related_items(rel, direction) or []):
                    if r and r.type == "Map Service" and (r.url or "").rstrip("/").lower() == target:
                        return r
            except Exception:
                pass

    # Fallback: search by BOTH the item title AND the url-derived service name, then match the exact url.
    name = target.rsplit("/mapserver", 1)[0].rsplit("/", 1)[-1]   # service name to narrow the search
    queries = [f'title:"{feature_item.title}"']
    if name:
        queries.append(f'{name} type:"Map Service"')
    candidates = {}
    for q in queries:
        try:
            for r in (gis.content.search(query=q, max_items=50) or []):
                candidates[r.id] = r
        except Exception as e:
            log_message(f"[map-image] portal search failed for {q!r}: {e}")
    for r in candidates.values():
        if r and r.type == "Map Service" and (r.url or "").rstrip("/").lower() == target:
            return r
    log_message(f"[map-image] no Map Image Layer item matched url {murl} "
          f"(searched title '{feature_item.title}' + name '{name}', {len(candidates)} candidate(s)) -- skipping.")
    return None


def apply_item_data_and_extent(gis, item, layer_id, drawing_info, popup,
                               src_min_scale, src_max_scale, src_item_extent, stamp, tag="item", tags=None,
                               license_info=None, extra_blocks=None):
    """Write renderer (+ visibility range + pop-ups) to the item /data and copy the default extent
    (+ tags + Terms of Use). Used for BOTH the Feature Layer item and the sibling Map Image Layer item
    (decision #9) -- the Map Viewer reads item /data drawingInfo/popupInfo + the item `extent`/`tags` for
    either item type. For a Map Image Layer the renderer override only redraws the image if the MapServer
    supports dynamic layers; pop-ups + extent + tags + Terms of Use sync regardless. `license_info` is the
    source item's Terms of Use (item `licenseInfo`) and is applied independently of `tags` so it copies on
    the AGOL re-apply too. `extra_blocks` ({"layers": [...], "tables": [...]}, from other_popup_blocks) adds
    the other layers' / tables' pop-ups. Backs up the current /data before changing it."""
    portal = gis.url if gis.url.endswith("/") else gis.url + "/"
    current = gis._con.get(f"{portal}sharing/rest/content/items/{item.id}/data", {"f": "json"})
    bpath = os.path.join(OUTPUT_DIR, f"Data_{item.id}_backup_{stamp}.json")
    with open(bpath, "w", encoding="utf-8") as fh:
        json.dump(current if current is not None else {}, fh, indent=2, ensure_ascii=False)

    layer_def = {"drawingInfo": drawing_info}
    # Carry visibility range (scale-dependent visibility) so the target matches the source.
    # 0 is a valid, meaningful value (0 = "no limit"), so copy whenever the source value is not None.
    if src_min_scale is not None:
        layer_def["minScale"] = src_min_scale
    if src_max_scale is not None:
        layer_def["maxScale"] = src_max_scale
    layer_block = {"id": layer_id, "layerDefinition": layer_def}
    if src_min_scale is not None or src_max_scale is not None:
        log_message(f"[{tag}] visibility range -> minScale={layer_def.get('minScale')} maxScale={layer_def.get('maxScale')}")
    if popup:
        layer_block["popupInfo"] = popup
    new_data = {"layers": [layer_block] + list((extra_blocks or {}).get("layers") or [])}
    if (extra_blocks or {}).get("tables"):
        new_data["tables"] = list(extra_blocks["tables"])
    if len(new_data["layers"]) > 1 or new_data.get("tables"):
        log_message(f"[{tag}] /data: {len(new_data['layers'])} layer block(s), {len(new_data.get('tables') or [])} "
                    f"table block(s)")
    ok = item.update(data=json.dumps(new_data))
    log_message(f"[{tag}] item.update(data=...): {'OK' if ok else 'FAILED'}  (backup {os.path.basename(bpath)})")

    # Default extent (the default view) + tags -- one update call.
    props = {}
    if src_item_extent:
        log_message(f"[{tag}] default extent: {getattr(item, 'extent', None)} -> {src_item_extent}")
        props["extent"] = src_item_extent
    if tags:
        log_message(f"[{tag}] tags: {getattr(item, 'tags', None)} -> {tags}")
        props["tags"] = tags
    if license_info:
        log_message(f"[{tag}] terms of use (licenseInfo): set ({len(license_info)} chars)")
        props["licenseInfo"] = license_info
    if props:
        ok_props = item.update(item_properties=props)
        log_message(f"[{tag}] item.update({'+'.join(props)}): {'OK' if ok_props else 'FAILED'}")
    else:
        log_message(f"[{tag}] no extent/tags to set; item properties unchanged")
    return ok


def apply_symbology(gis, target_item_id, src_item_id, src_layer_id=None, target_layer_id=None,
                    apply="both", prune_stale_fieldinfos=True, apply_tags=True, migration_tags=None,
                    sync_map_image_layer=True, map_image_item_id="",
                    source_portal_url=None, target_portal_url=None, enterprise_portal_url=None,
                    stamp=None, regen_thumbnail=None):
    """Apply the SOURCE AGOL item's renderer + pop-ups + visibility range + default view (+ tags) to a
    published TARGET item via its /data, optionally syncing the sibling Map Image Layer (decision #9).

    `gis` must ALREADY be connected to the TARGET portal. Reads the captured source pieces from
    OUTPUT_DIR (renderer/service JSON from Step 1) + the cached DataDump (_data/_description JSON).
    src_layer_id auto-resolves from the Step-1 report when None; target_layer_id None = resolve the matching
    target layer (resolve_target_layer). Returns True once the item /data apply
    runs, False if it could not (missing renderer file / item / target layer). Best-effort: callers may
    ignore the result. This is the importable core of Step 6 (main() wires CONFIG/CLI to it, and
    PublishFromDBToFeatureService.py calls it post-publish to symbolize the Enterprise item in one pass)."""
    if stamp is None:
        stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    if migration_tags is None:
        migration_tags = MIGRATION_TAGS
    if source_portal_url is None:
        source_portal_url = SOURCE_PORTAL_URL
    if enterprise_portal_url is None:
        enterprise_portal_url = PORTAL_URL
    if target_portal_url is None:
        target_portal_url = gis.url
    if src_layer_id is None:
        src_layer_id = resolve_src_layer_id(src_item_id)

    log_message(f"=== Step 6 apply: source {src_item_id} (layer {src_layer_id}) "
                f"-> item {target_item_id} (layer {'auto' if target_layer_id is None else target_layer_id}) ===\n")

    # --- load captured source pieces ---------------------------------------
    rend_path = os.path.join(OUTPUT_DIR, f"{src_item_id}_layer{src_layer_id}_renderer.json")
    if not os.path.isfile(rend_path):
        log_message(f"!! renderer file not found: {rend_path} (run Step 1 first). Stopping.")
        return False
    drawing_info = load_json(rend_path).get("drawingInfo")
    log_message(f"renderer     : {rend_path}  (type={((drawing_info or {}).get('renderer') or {}).get('type')})")

    # Visibility range (scale-dependent visibility) lives on the source SERVICE layer as
    # minScale/maxScale -- NOT in the cached _data.json. The full source layer def captured by
    # Step 1 (..._service.json) carries it; pull it and carry it into the item /data layerDefinition
    # (the lever portal/web-map clients honor; service-layer minScale/maxScale can't be set on a
    # by-reference service for the same updateDefinition reason as the renderer).
    src_min_scale = src_max_scale = None
    src_layer_name = ""
    svc_path = os.path.join(OUTPUT_DIR, f"{src_item_id}_layer{src_layer_id}_service.json")
    if os.path.isfile(svc_path):
        _svc = load_json(svc_path)
        src_min_scale = _svc.get("minScale")
        src_max_scale = _svc.get("maxScale")
        src_layer_name = _svc.get("name") or ""
    log_message(f"visibility   : source minScale={src_min_scale} maxScale={src_max_scale}  "
                f"({svc_path if os.path.isfile(svc_path) else 'service.json not found'})")

    data_path = find_cached_data(src_item_id)
    popup = None
    if data_path:
        for lyr in load_json(data_path).get("layers", []):
            if int(lyr.get("id", -1)) == src_layer_id:
                popup = lyr.get("popupInfo")
                break
    log_message(f"pop-ups      : {data_path or '(none found)'}  ({'present' if popup else 'none'})")

    # Source item properties (from the cached description JSON; live-AGOL fallback fills gaps):
    #   * default extent -- the item-level bounding box portal uses as the default view. Always WGS84
    #     [[xmin,ymin],[xmax,ymax]] regardless of the service SR -> copy as-is, no reprojection.
    #     (Service initialExtent/fullExtent are computed from the data and are not set here.)
    #   * tags -- copied to the Enterprise item plus the migration_tags defaults (decision #10).
    #   * licenseInfo (Terms of Use) -- the source item's use constraints; carried so the migrated items
    #     match the original. Not a tag, so applied regardless of apply_tags (incl. the AGOL re-apply).
    desc_path = find_cached_desc(src_item_id)
    desc = load_json(desc_path) if desc_path else None
    src_item_extent = (desc or {}).get("extent")
    src_tags = list((desc or {}).get("tags") or [])
    src_license_info = (desc or {}).get("licenseInfo")
    if not src_item_extent or not src_tags or not src_license_info:
        log_message(f"source props : extent/tags/licenseInfo incomplete from cache ({desc_path or 'no description file'}) -> live AGOL pull")
        live = fetch_source_item(src_item_id, source_portal_url)
        if live is not None:
            if not src_item_extent:
                src_item_extent = getattr(live, "extent", None) or None
            if not src_tags:
                src_tags = list(getattr(live, "tags", []) or [])
            if not src_license_info:
                src_license_info = getattr(live, "licenseInfo", None) or None
    log_message(f"item extent  : {src_item_extent if src_item_extent else 'none'}")
    log_message(f"source tags  : {src_tags}")
    log_message(f"terms of use : {'present (' + str(len(src_license_info)) + ' chars)' if src_license_info else 'none'}")

    # Enterprise item tags = source tags + migration defaults (decision #10).
    enterprise_tags = list(src_tags)
    for t in migration_tags:
        if t not in enterprise_tags:
            enterprise_tags.append(t)
    log_message(f"enterprise tags -> {enterprise_tags}")

    # --- target item + layer -----------------------------------------------
    item = gis.content.get(target_item_id)
    if item is None:
        log_message(f"!! target item {target_item_id} not found / not accessible. Stopping.")
        return False
    log_message(f"target item  : {item.title}  | type {item.type} | owner {item.owner}")

    target_layers = list(getattr(item, "layers", []) or [])
    by_id = {int(l.properties.id): l for l in target_layers}
    resolved, how = resolve_target_layer(by_id, target_layer_id, src_layer_id, src_layer_name)
    if resolved is None:
        log_message(f"!! {how}. Stopping.")
        return False
    target_layer_id = resolved
    tlayer = by_id[target_layer_id]
    log_message(f"target layer : {target_layer_id} '{tlayer.properties.name}' <- source layer {src_layer_id} "
                f"'{src_layer_name}' ({how})")
    target_fields = {f["name"] for f in tlayer.properties.fields}
    # These are the fields the NEW Enterprise layer actually exposes (from .../FeatureServer/0?f=json);
    # the pop-up is pruned/validated against exactly this list.
    log_message(f"target layer {target_layer_id} fields ({len(target_fields)}): {sorted(target_fields)}")

    # --- field-reference check (renderer + pop-ups) ------------------------
    rnd_fields = renderer_field_names(drawing_info)
    missing_rnd = rnd_fields - target_fields
    if missing_rnd:
        log_message(f"!! renderer references field(s) missing on target: {missing_rnd} -- renderer will not resolve.")
    else:
        log_message(f"renderer field(s) {rnd_fields or '(none)'} present on target: OK")

    if popup:
        # a field renamed by the SDE load (reserved word: LEVEL -> LEVEL_) is renamed in the pop-up, not pruned
        popup, used = rename_popup_fields(popup, reserved_renames(target_fields))
        if used:
            log_message(f"pop-up fields renamed by SDE (SQL reserved word), pointed at the new name: {', '.join(used)}")
        before_top = len(popup.get("fieldInfos") or [])
        before_els = sum(len(el.get("fieldInfos") or []) for el in (popup.get("popupElements") or []))
        missing_popup = popup_field_names(popup) - target_fields
        log_message(f"pop-up fieldInfos: top-level={before_top}, popupElements={before_els}; "
              f"referencing fields NOT on target: {len(missing_popup)}")
        if prune_stale_fieldinfos and missing_popup:
            popup = prune_popup(copy.deepcopy(popup), target_fields)
            after_top = len(popup.get("fieldInfos") or [])
            after_els = sum(len(el.get("fieldInfos") or []) for el in (popup.get("popupElements") or []))
            log_message(f"   pruned to live target fields -> top-level={after_top}, popupElements={after_els}")

    # --- the OTHER layers' renderers + pop-ups and the tables' pop-ups (multi-layer items) ---
    extra_blocks = other_layer_blocks(item, src_item_id, src_layer_id, target_layer_id, data_path,
                                      source_portal_url, prune_stale_fieldinfos)

    # --- SERVICE: push drawingInfo via updateDefinition --------------------
    # NOTE (POC finding 2026-06-08): for a BY-REFERENCE service published from a Pro map
    # (a MapServer + FeatureServer extension on the federated server), the service-level
    # renderer is baked in from the Pro authoring and the REST `updateDefinition` admin op
    # is NOT available (the federated arcgisserver exposes no rest/admin/services catalog;
    # .manager raises {'code':500,'message':'Service not found'}). So this step is best-effort:
    # it works for HOSTED feature layers, but is expected to fail for referenced services.
    # The reliable programmatic edit for renderer + pop-ups is the ITEM /data step below.
    if apply in ("service", "both") and drawing_info:
        try:
            backup = dict(tlayer.properties).get("drawingInfo")
        except Exception:
            backup = None
        bpath = os.path.join(OUTPUT_DIR, f"ServiceDrawingInfo_backup_{target_item_id}_{stamp}.json")
        with open(bpath, "w", encoding="utf-8") as fh:
            json.dump(backup, fh, indent=2, ensure_ascii=False)
        try:
            result = tlayer.manager.update_definition({"drawingInfo": drawing_info})
            ok = (isinstance(result, dict) and result.get("success")) or result is True
            log_message(f"[service] updateDefinition layer {target_layer_id}: {'OK' if ok else result}  (backup {os.path.basename(bpath)})")
        except Exception as e:
            log_message(f"[service] updateDefinition NOT applied (expected for a by-reference service "
                  f"published from Pro): {e}")
            log_message("          -> service-level renderer comes from the Pro map; item /data below carries it for portal clients.")

    # --- ITEM /data: renderer + pop-ups + default view ---------------------
    if apply in ("item", "both"):
        apply_item_data_and_extent(gis, item, target_layer_id, drawing_info, popup,
                                   src_min_scale, src_max_scale, src_item_extent, stamp, tag="item",
                                   tags=(enterprise_tags if apply_tags else None),
                                   license_info=src_license_info, extra_blocks=extra_blocks)

        # --- MAP IMAGE LAYER sibling (decision #9): keep the two items in sync -----
        # The referenced publish creates a Map Service item alongside the Feature Service item.
        # Apply the SAME renderer + pop-ups + default view to its item /data so the two match.
        # (Same underlying data/fields, so the field-validated/pruned popup applies as-is; the
        # MapServer sublayer id mirrors the feature layer id, so the same blocks fit as-is.)
        mi_item = None
        if sync_map_image_layer:
            mi_item = find_map_image_item(gis, item, map_image_item_id)
        if mi_item is not None:
            log_message(f"map-image item : {mi_item.title}  | type {mi_item.type} | id {mi_item.id}")
            apply_item_data_and_extent(gis, mi_item, target_layer_id, drawing_info, popup,
                                       src_min_scale, src_max_scale, src_item_extent, stamp, tag="map-image",
                                       tags=(enterprise_tags if apply_tags else None),
                                       license_info=src_license_info, extra_blocks=extra_blocks)
            log_message("[map-image] NOTE: renderer redraws the image only if the MapServer supports dynamic "
                  "layers (check .../MapServer?f=json supportsDynamicLayers); pop-ups + extent sync regardless.")

    # --- Step 6b: regenerate the thumbnail (now that the renderer + default view are applied) ----------
    # Best-effort -- a thumbnail failure must NOT affect the symbology apply. Renders with the item /data
    # renderer, frames to the item extent just set, and reuses the same PNG on the Map Image sibling.
    if regen_thumbnail is None:
        regen_thumbnail = REGEN_THUMBNAIL
    if regen_thumbnail:
        if regenerate_thumbnail is None:
            log_message("thumbnail: RegenerateItemThumbnails.regenerate_thumbnail not importable -- skipped", "warning")
        else:
            try:
                regenerate_thumbnail(gis, item, token=getattr(gis._con, "token", None),
                                     apply_to_map_sibling=sync_map_image_layer)
            except Exception as e:
                log_message(f"thumbnail regen failed (symbology unaffected): {e}", "warning")

    # --- migration status ledger (Phase 4/8 milestone) ---------------------
    # Enterprise target -> "portal_updated"; AGOL by-reference target -> "agol_updated".
    try:
        is_agol = target_portal_url.rstrip("/").lower() != enterprise_portal_url.rstrip("/").lower()
        if is_agol:
            ledger_mod.set_state(src_item_id, "agol_updated", logger=logger, title=item.title,
                                 agol_byref_item_id=target_item_id)
        else:
            ledger_mod.set_state(src_item_id, "portal_updated", logger=logger, title=item.title,
                                 enterprise_item_id=target_item_id,
                                 enterprise_service_url=(item.url or ""))
    except Exception as e:
        log_message(f"ledger update skipped: {e}", "warning")

    log_message("\nDone. Verify in the portal item viewer / map that the renderer + pop-ups + default view match the source.")
    log_message(f"  source AGOL item : https://rrg.maps.arcgis.com/home/item.html?id={src_item_id}")
    log_message(f"  target item      : {target_portal_url}/home/item.html?id={target_item_id}")
    return True


def resolve_targets():
    """Build the list of (target_item_id, src_item_id) pairs. With TARGET_ITEM_ID set (CLI/CONFIG),
    process just that one (its source resolved from the ledger, else SRC_ITEM_ID). Otherwise loop EVERY
    ledger row, picking the target by org: agol_byref_item_id when TARGET_PORTAL_URL is the AGOL org, else
    enterprise_item_id. src is the row's source item_id; src_layer_id auto-resolves per source."""
    is_agol = TARGET_PORTAL_URL.rstrip("/").lower() != PORTAL_URL.rstrip("/").lower()
    ledger = None
    try:
        ledger = ledger_mod.get_ledger(logger=logger)
    except Exception as e:
        log_message(f"could not open ledger ({e}); continuing", "warning")

    if TARGET_ITEM_ID:
        src = SRC_ITEM_ID
        if ledger is not None:
            for iid, r in ledger.rows.items():
                if TARGET_ITEM_ID in ((r.get("agol_byref_item_id") or "").strip(),
                                      (r.get("enterprise_item_id") or "").strip()):
                    src = iid
                    break
        return is_agol, [(TARGET_ITEM_ID, src)]

    pairs = []
    if ledger is not None:
        field = "agol_byref_item_id" if is_agol else "enterprise_item_id"
        # The milestone this run sets: 'agol_updated' for the AGOL by-reference item, else 'portal_updated'
        # for the Enterprise item. A row already at/past it has had its symbology applied -> skip (below).
        done_state = "agol_updated" if is_agol else "portal_updated"
        for iid, r in ledger.rows.items():
            # Single work-selection gate (ledger_mod.row_eligible_to_advance, done_state=this run's milestone):
            # skips a row outside the run-scope allowlist (MIGRATION_ITEM_ALLOWLIST -- silent), carrying a
            # recorded error (must be fixed + cleared first), or already at/past this run's milestone
            # (symbology already applied). The milestone check also covers an already-deprecated source, since
            # the terminal state ranks past both 'portal_updated' and 'agol_updated'. The SAME helper the
            # deprecate / publish / share-back stages use, so one place decides "is this row workable".
            ok, why = ledger_mod.row_eligible_to_advance(r, done_state)
            if not ok:
                if why:
                    log_message(f"skip {iid}: {why}")
                continue
            tgt = (r.get(field) or "").strip()
            if tgt:
                pairs.append((tgt, iid))
    return is_agol, pairs


def main():
    global current_src_id
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    is_agol, pairs = resolve_targets()
    if not pairs:
        log_message("no target items resolved (pass a target id, or populate the ledger). Stopping.", "warning")
        return
    gis = connect_portal(TARGET_PORTAL_URL)
    me = gis.users.me
    log_message(f"connected as : {me.username if me else '?'} on {gis.url}  "
                f"(target = {'AGOL by-reference' if is_agol else 'Enterprise'}; {len(pairs)} item(s))")
    for target_item_id, src_item_id in pairs:
        current_src_id = src_item_id   # so any 'error' logged during this item's apply auto-records to its row
        log_message(f"\n=== target {target_item_id}  <- source {src_item_id} ===")
        try:
            apply_symbology(gis, target_item_id, src_item_id,
                            src_layer_id=None, target_layer_id=TARGET_LAYER_ID,
                            apply=APPLY, prune_stale_fieldinfos=PRUNE_STALE_FIELDINFOS,
                            apply_tags=APPLY_TAGS, migration_tags=MIGRATION_TAGS,
                            sync_map_image_layer=SYNC_MAP_IMAGE_LAYER, map_image_item_id=MAP_IMAGE_ITEM_ID,
                            source_portal_url=SOURCE_PORTAL_URL, target_portal_url=TARGET_PORTAL_URL,
                            enterprise_portal_url=PORTAL_URL, stamp=stamp)
        except Exception as e:
            log_message(f"!! apply_symbology failed for target {target_item_id} (source {src_item_id}): {e}", "error")   # auto-recorded


if __name__ == "__main__":
    main()

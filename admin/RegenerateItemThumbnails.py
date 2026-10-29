# -*- coding: utf-8 -*-
"""
Name: RegenerateItemThumbnails.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-08

================================================================================
WHAT THIS SCRIPT DOES
================================================================================
Regenerates the THUMBNAIL of ArcGIS Enterprise (or AGOL) feature-service items by
rendering each item's layer(s) on a basemap with the print service and saving the
result as the item thumbnail. Run it AFTER applying symbology/pop-ups (e.g. after
the migration Step 6) so the thumbnail reflects the corrected symbology.

PREREQUISITE -- the item's DEFAULT VIEW must be set first. The thumbnail is framed to
`item.extent`, so the default extent has to be applied (migration Step 6 copies it from
the source item) BEFORE this runs; otherwise the thumbnail is framed to the world extent
and the script WARNS. Order: Step 6 (symbology + default view) -> this script.

It is the headless equivalent of the portal's "Update Thumbnail -> Create Thumbnail
from Map" button (arcgis API `Item.create_thumbnail()`), but it renders with the
item's *item-level* `/data` renderer instead of the service renderer. That matters
for BY-REFERENCE services whose service renderer stays `simple` (the corrected
symbology lives only in the item `/data`); rendering the service renderer alone
would produce a single-color thumbnail.

How it works, per item:
  1. Read the item `/data` to get each layer's `layerDefinition.drawingInfo` (the
     applied renderer).
  2. Build a Web Map JSON: the portal default basemap + one operational layer per
     feature layer, injecting (a) a token so the print service can read the secured
     layer and (b) the item `/data` drawingInfo so it renders with the right symbology.
     (minScale/maxScale are deliberately NOT injected, so the layer always draws in the
     thumbnail regardless of its visibility range.)
  3. POST to the enterprise print service (Export Web Map Task, MAP_ONLY) -> PNG url.
  4. Download the PNG and set it as the item thumbnail (`item.update(thumbnail=...)`).
  5. (decision #9) With SYNC_MAP_IMAGE_LAYER, push the SAME PNG to the sibling Map Image Layer
     item (the .../MapServer item the referenced publish creates alongside .../FeatureServer) --
     same data/symbology/extent => identical thumbnail, so no re-render. Auto-discovered by url.

================================================================================
AUTH: GIS("pro") FIRST, ELSE USERNAME/PASSWORD
================================================================================
The print service must authenticate to the secured feature layer with a TOKEN passed
in each operational layer, so connect_portal() needs a session that exposes one. It
tries the active `GIS("pro")` session first and uses it ONLY if it is this portal AND
exposes a usable token (`gis._con.token`). On many Pro installs that token is None (auth
is managed by Pro/IWA) -- in that case it falls back to username/password, which does
yield a token. Fill in PORTAL_USERNAME / PORTAL_PASSWORD below, or leave PASSWORD blank
to be prompted. (Observed 2026-06-08: the Pro session on this machine exposes no token,
so it falls back to username/password.)

================================================================================
HOW TO RUN  (ArcGIS Pro conda env)
================================================================================
    python RegenerateItemThumbnails.py
    python RegenerateItemThumbnails.py <itemid1> <itemid2> ...   # overrides ITEM_IDS

Set DRY_RUN=True to render + save PNGs locally WITHOUT changing any item.

COPY MODE (use an EXISTING thumbnail instead of re-rendering)
------------------------------------------------------------
Instead of rendering via the print service, copy a thumbnail that already exists onto the target item(s):

    # 1) Ledger-driven (Phase 4b, ENTERPRISE side): set each ENTERPRISE item's thumbnail FROM the ORIGINAL
    #    AGOL item's thumbnail (copy). If the copy fails (AGOL item has no thumbnail), FALL BACK to
    #    regenerating on the server (print service). Also syncs the Map Image Layer sibling.
    python RegenerateItemThumbnails.py --copy-agol-to-portal

    # 2) Ledger-driven (Phase 8, AGOL side): copy each ENTERPRISE Portal item's thumbnail onto its AGOL
    #    by-reference item, so the shared-to-AGOL item reuses the Portal thumbnail (no AGOL re-render).
    python RegenerateItemThumbnails.py --copy-portal-to-agol

    # 3) Explicit: copy one item's thumbnail onto one or more targets (all on PORTAL_URL).
    python RegenerateItemThumbnails.py --copy-from <source_item_id> <target_id> [<target_id> ...]

The importable copy_thumbnail(source_item, target_item) does the work and is cross-portal safe.

================================================================================
IF YOU GET 503 "Wait timeout for the request exceeded" ERRORS
================================================================================
That 503 comes from the enterprise PrintingTools GP service, not this script's HTTP client: the
service is SYNCHRONOUS with only a few dedicated instances, so when they are all busy a render request
waits up to the service's maxWaitTime and then fails. This script already RETRIES the print /execute
call with backoff (see PRINT_MAX_ATTEMPTS / PRINT_RETRY_BACKOFF). If the errors PERSIST, tune the print
service in Server Manager:
    https://maps.rrgnbs.com/arcgisserver/manager/service.html?name=PrintingTools.GPServer&folder=Utilities
    (Pooling tab; or admin .../admin/services/Utilities/PrintingTools.GPServer/edit)
      - maxWaitTime         60  -> 300   the property the 503 names: how long a request waits for an instance
      - minInstancesPerNode  1  -> 2     keep instances warm (ArcObjects print instances cold-start slowly)
      - maxInstancesPerNode  2  -> 3-4   more concurrent renders = less queuing (only if the server has RAM)
      - maxUsageTime        600          leave -- that is the per-render budget, not the queue wait that fails

================================================================================
FAILURES ARE RECORDED TO THE MIGRATION LEDGER (so you can redo them by hand)
================================================================================
When an item still fails after the retries above, the failure is recorded to the migration status ledger
(Migrate\Output\migration_status_ledger.csv, override with env MIGRATION_LEDGER_PATH) so it is not lost,
via the SHARED ledger helper ledger_mod.record_error(id, reason, phase="thumbnail") -- the same generic
error API every phase uses (this is NOT a thumbnail-special path). The processed id is a DESTINATION item;
the helper matches it against each row's enterprise_item_id / agol_byref_item_id and appends a timestamped
"[thumbnail] <reason>" entry to that row's `error` column (a later success clears the thumbnail entries via
clear_errors(id, phase="thumbnail")). The row's pipeline `state` is left untouched. To find what to redo
later, filter the ledger's `error` column for "[thumbnail]" and re-run this script with those item ids.
Best-effort + RECORD_FAILURES_TO_LEDGER=True: if the ledger helper isn't importable or no row maps the id,
the run is unaffected and the full detail is still in the .log. Skipped under DRY_RUN.
"""

import os
import re
import sys
import json
import time
import getpass
import logging
import datetime as dt

from arcgis.gis import GIS

# Windows Credential Manager logins (key 'portal' -> nbs_arcgis_admin, 'agol' -> nbs_agol_user), with an
# interactive prompt fallback. Best-effort -- if not importable, connect_portal() prompts as before.
try:
    import credential_store
except Exception:
    credential_store = None

# Migration status ledger (shared helper in ArcGIS Admin\Migrate). Best-effort: used only to RECORD a
# thumbnail FAILURE against the matching migration row so a failed item can be regenerated by hand later
# (see RECORD_FAILURES_TO_LEDGER below). All path/instance/error handling lives in the module -- we just
# call its generic ledger_mod.record_error(id, reason, phase="thumbnail") / clear_errors(id,
# phase="thumbnail"). If it is not importable, thumbnails are unaffected.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Migrate"))
try:
    import migration_status_ledger as ledger_mod
except Exception:
    ledger_mod = None

# init logging (matches the repo log_message pattern, e.g. copyFeaturesFromService.py)
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Output")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"RegenerateItemThumbnails_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG, format='%(message)s')


def log_message(msg, level='info', print_msg=True):
    if level == 'info':
        logging.info(msg)
    elif level == 'error':
        print_msg = True
        msg = f"ERROR: {msg}"
        logging.error(msg)
    elif level == 'warning':
        msg = f"WARNING: {msg}"
        logging.warning(msg)
    else:
        logging.debug(msg)
    if print_msg:
        print(msg)

# ----------------------------------------------------------------------------
# CONFIG  -- edit these
# ----------------------------------------------------------------------------
PORTAL_URL = "https://maps.rrgnbs.com/arcgisportal"
PORTAL_USERNAME = "rrgadmin"          # <-- fill in (a publisher/admin who owns/can edit the items)
PORTAL_PASSWORD = ""          # <-- fill in, or leave "" to be prompted (not echoed)

# AGOL org -- the COPY-MODE write target for --copy-portal-to-agol (the by-reference items live here).
AGOL_URL = "https://rrg.maps.arcgis.com"

# WHICH ITEMS:
#   MODE = "list"  -> use ITEM_IDS below (or item ids passed on the command line)
#   MODE = "query" -> use ITEM_QUERY (a portal search); MAX_ITEMS caps the result
MODE = "list"
ITEM_IDS = [
    "6b887c6b9395471fb7c88dc115037ec6",   # WS_Change_in_SW_Supply_by_2030 (migration POC target)
]
ITEM_QUERY = 'type:"Feature Service" owner:{user}'   # {user} -> PORTAL_USERNAME at runtime
MAX_ITEMS = 100               # safety cap for query mode

# THUMBNAIL render options
THUMB_SIZE = [600, 400]       # width, height (px); portal shows ~200x133, 600x400 is crisp
THUMB_DPI = 96
BASEMAP_OVERRIDE = None       # None = portal default basemap; else a dict baseMap definition
DRY_RUN = False               # True = render + save PNG locally, do NOT update the item

# Print-service resilience (decision: retry, not async). The enterprise PrintingTools GP service is
# SYNCHRONOUS with only a few dedicated instances (maxInstancesPerNode). When every instance is busy a
# render request waits up to the service's maxWaitTime and then fails with HTTP 503 "Wait timeout for
# the request exceeded." That is transient -- an instance frees the moment a prior render finishes -- so
# we re-POST the /execute call with backoff rather than failing the item. A true async submitJob is NOT
# an option here: a Synchronous GP service exposes only /execute (no /submitJob), and flipping the SHARED
# print service to executionType=Asynchronous would change the contract for every other client of it.
# If 503 errors PERSIST despite this retry, tune the print service -- see the header note above.
PRINT_MAX_ATTEMPTS = 2               # total tries for the print /execute call (1 original + 1 retry)
PRINT_RETRY_BACKOFF = [20, 45, 90]   # seconds to wait before each retry (last value reused if more retries)

# Record FAILURES to the migration status ledger (so a thumbnail that still fails after the retries above
# -- e.g. the print service stayed busy -- leaves a durable note to regenerate that item by hand later).
# The processed id is a DESTINATION item (Enterprise or AGOL by-reference); the ledger module matches it
# against the enterprise_item_id / agol_byref_item_id columns and writes the note to that row's `error`
# column (a matching success CLEARS it), never changing the row's pipeline `state`. The canonical ledger
# path is resolved by the module (env MIGRATION_LEDGER_PATH overrides). Best-effort: if the module isn't
# importable or no row matches, the run is unaffected (the .log still has the full detail).
RECORD_FAILURES_TO_LEDGER = True
_LAST_THUMB_ERROR = {}                 # item_id -> last failure reason, set by regenerate_thumbnail()

# Map Image Layer sync (decision #9): a referenced publish from Pro creates a Map Service
# (.../MapServer) item alongside the Feature Service (.../FeatureServer) item. The thumbnail is
# identical (same data/symbology/extent), so push the SAME rendered PNG to the sibling Map Image
# Layer item rather than re-rendering it. Auto-discovered per item (FeatureServer->MapServer url).
SYNC_MAP_IMAGE_LAYER = True

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Output", "Thumbnails")


# ----------------------------------------------------------------------------
def connect_portal():
    """Try the active ArcGIS Pro session first; fall back to username/password. The print service
    needs a real TOKEN passed in each operational layer, so a Pro session is only usable here when it
    IS this portal AND exposes a token (`gis._con.token`). On many Pro installs that token is None
    (auth is managed by Pro/IWA) -- then we must use username/password, which does yield a token."""
    # The print service needs a real TOKEN, which a username/password login always yields. Use the shared
    # credential_store.connect() (CREDENTIALS FIRST -> always a token; the active Pro session is only a
    # same-portal fallback and may be tokenless). An explicit PORTAL_PASSWORD still wins (ad-hoc account).
    if PORTAL_PASSWORD:
        gis = GIS(PORTAL_URL, PORTAL_USERNAME, PORTAL_PASSWORD)
    elif credential_store is not None:
        gis = credential_store.connect(PORTAL_URL, default_username=PORTAL_USERNAME,
                                       log=lambda m: log_message(m, 'info'))
    else:
        user = PORTAL_USERNAME or input(f"** Portal Username for {PORTAL_URL}: ").strip()
        pwd = getpass.getpass(f"** Portal Password for {user}: ")
        gis = GIS(PORTAL_URL, user, pwd)
    if not (gis.users.me and gis._con.token):
        log_message("Login failed or no token returned -- check credentials / portal URL.", level='error')
        raise SystemExit(1)
    return gis


def _has_flag(name):
    return name in sys.argv[1:]


def _flag_val(name, default=""):
    argv = sys.argv[1:]
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            return argv[i + 1].strip()
    return default


def connect_basic(portal_url, key=None, default_username=""):
    """Connect for the COPY path (which does NOT need a print-service token) via the shared
    credential_store.connect(): stored credential FIRST (key by host when not given), then the active Pro
    session, then a prompt. Falls back to a direct prompt + GIS if credential_store isn't importable."""
    if credential_store is not None:
        return credential_store.connect(portal_url, key=key, default_username=default_username,
                                        log=lambda m: log_message(m, 'info'))
    user = default_username or input(f"** Username for {portal_url}: ").strip()
    pwd = getpass.getpass(f"** Password for {user}: ")
    return GIS(portal_url, user, pwd)


def resolve_items(gis):
    """Return a list of item ids to process, from CLI args, ITEM_IDS, or a query. Flag tokens (and a
    --copy-from value) are ignored so the render path coexists with the copy-mode flags."""
    cli_ids = [a.strip() for a in sys.argv[1:] if a.strip() and not a.startswith("--")]
    cf = _flag_val("--copy-from")
    if cf and cf in cli_ids:
        cli_ids.remove(cf)
    if cli_ids:
        return cli_ids
    if MODE == "query":
        q = ITEM_QUERY.replace("{user}", gis.users.me.username)
        found = gis.content.search(q, max_items=MAX_ITEMS)
        log_message(f"query [{q}] matched {len(found)} item(s)")
        return [it.id for it in found]
    return list(ITEM_IDS)


def find_map_image_item(gis, feature_item):
    """Find the sibling Map Image Layer item for a Feature Layer item (decision #9): a referenced
    publish creates .../FeatureServer and .../MapServer items sharing the service name. Derive the
    MapServer url and match a portal Map Image Layer item by url. Returns the Item or None (and is a
    no-op for items that are not feature services)."""
    furl = feature_item.url or ""
    murl = re.sub(r"/FeatureServer(/\d+)?/?$", "/MapServer", furl, flags=re.IGNORECASE)
    if not murl or murl == furl:
        return None
    target = murl.rstrip("/").lower()
    name = target.rsplit("/mapserver", 1)[0].rsplit("/", 1)[-1]   # service name to narrow the search
    try:
        candidates = gis.content.search(name, item_type="Map Image Layer", max_items=25)
    except Exception as e:
        log_message(f"map-image search failed for {name}: {e}", level='warning')
        return None
    for it in candidates:
        if (it.url or "").rstrip("/").lower() == target:
            return it
    return None


def build_web_map(gis, item, token):
    """Web Map JSON: default basemap + each feature layer (with item /data renderer + token)."""
    portal = gis.url.rstrip("/") + "/"
    data = gis._con.get(f"{portal}sharing/rest/content/items/{item.id}/data", {"f": "json"}) or {}
    dd_by_id = {int(l.get("id", -1)): l for l in (data.get("layers") or [])}

    op_layers = []
    for idx, lyr in enumerate(item.layers):
        lid = int(lyr.properties.id)
        ld = (dd_by_id.get(lid, {}).get("layerDefinition") or {})
        ol = {
            "id": f"lyr{idx}",
            "url": lyr.url,
            "title": getattr(lyr.properties, "name", f"layer {lid}"),
            "opacity": 1,
            "visibility": True,
            "token": token,          # lets the print service read the secured layer
        }
        # Render with the APPLIED (item /data) symbology, not the service renderer.
        if ld.get("drawingInfo"):
            ol["layerDefinition"] = {"drawingInfo": ld["drawingInfo"]}
        op_layers.append(ol)

    if not op_layers:
        return None

    # Extent (item.extent is [[xmin,ymin],[xmax,ymax]] in WGS84). The thumbnail is framed to this
    # default view, so it MUST be set first (migration Step 6 copies it from the source item). If it
    # is missing we fall back to a world extent and WARN -- a thumbnail framed to the world is the
    # signal that the default view was not applied before this script ran.
    ext = item.extent
    if ext and len(ext) == 2:
        extent = {"xmin": ext[0][0], "ymin": ext[0][1], "xmax": ext[1][0], "ymax": ext[1][1],
                  "spatialReference": {"wkid": 4326}}
        log_message(f"    default view (item extent): {ext}")
    else:
        extent = {"xmin": -180, "ymin": -85, "xmax": 180, "ymax": 85,
                  "spatialReference": {"wkid": 4326}}
        log_message("item has NO default extent -> framing the WORLD. Set the item's default view "
                    "(migration Step 6) BEFORE regenerating the thumbnail.", level='warning')

    basemap = BASEMAP_OVERRIDE or gis.properties.get("defaultBasemap", {})
    return {
        "mapOptions": {"extent": extent},
        "operationalLayers": op_layers,
        "baseMap": {"title": basemap.get("title", "basemap"),
                    "baseMapLayers": basemap.get("baseMapLayers", [])},
        "exportOptions": {"outputSize": THUMB_SIZE, "dpi": THUMB_DPI},
    }


def _is_busy_print_error(exc):
    """True when a print-service exception is the transient 'all instances busy' 503/wait-timeout
    (vs. a real error like a bad Web_Map_as_JSON) -- the only case worth retrying."""
    s = repr(exc).lower()
    return ("503" in s) or ("wait timeout" in s) or ("timeout for the request" in s)


def export_thumbnail(gis, web_map, out_path):
    """Run the print service (Export Web Map Task, MAP_ONLY) and download the PNG to out_path.
    Retries the synchronous /execute on a transient 503 'Wait timeout' (all dedicated print instances
    busy); other errors raise immediately."""
    print_url = (gis.properties.get("helperServices", {}).get("printTask", {}) or {}).get("url")
    if not print_url:
        raise RuntimeError("portal has no helperServices.printTask url configured")
    exec_url = print_url.rstrip("/") + "/execute"
    params = {"f": "json",
              "Web_Map_as_JSON": json.dumps(web_map),
              "Format": "PNG32",
              "Layout_Template": "MAP_ONLY"}
    res = None
    for attempt in range(1, PRINT_MAX_ATTEMPTS + 1):
        try:
            res = gis._con.post(exec_url, params)
            break
        except Exception as e:
            if attempt >= PRINT_MAX_ATTEMPTS or not _is_busy_print_error(e):
                raise
            wait = PRINT_RETRY_BACKOFF[min(attempt - 1, len(PRINT_RETRY_BACKOFF) - 1)]
            log_message(f"    print service busy (attempt {attempt}/{PRINT_MAX_ATTEMPTS}): "
                        f"{repr(e)[:120]} -- retrying in {wait}s", level='warning')
            time.sleep(wait)
    img_url = None
    for r in (res.get("results") or []):
        val = r.get("value")
        if isinstance(val, dict) and val.get("url"):
            img_url = val["url"]
            break
    if not img_url:
        raise RuntimeError(f"print service returned no image url: {json.dumps(res)[:300]}")
    folder, name = os.path.dirname(out_path), os.path.basename(out_path)
    gis._con.get(img_url, try_json=False, out_folder=folder, file_name=name)
    return out_path


def regenerate_thumbnail(gis, item, token=None, out_dir=None, apply_to_map_sibling=True, dry_run=False):
    """Render `item` on the portal basemap via the print service using the item /data renderer, set the
    result as the item thumbnail, and (optionally) apply the SAME PNG to the backing Map Image Layer
    sibling (decision #9). Importable so Step 6 (apply_symbology) can regenerate the thumbnail right after
    applying the renderer + default view. Requires a real token for the print service (pass
    `gis._con.token`). Returns the PNG path on success, or None if skipped/failed. Never raises."""
    if token is None:
        token = getattr(getattr(gis, "_con", None), "token", None)
    if out_dir is None:
        out_dir = OUTPUT_DIR
    try:
        os.makedirs(out_dir, exist_ok=True)
        if item is None or not getattr(item, "layers", None):
            log_message(f"thumbnail: {getattr(item, 'id', '?')} has no feature layers -- skipped", level='warning')
            return None
        web_map = build_web_map(gis, item, token)
        if web_map is None:
            log_message(f"thumbnail: {item.id} has no operational layers -- skipped", level='warning')
            return None
        png = os.path.join(out_dir, f"{item.id}.png")
        export_thumbnail(gis, web_map, png)
        size_kb = os.path.getsize(png) / 1024.0 if os.path.isfile(png) else 0
        if dry_run:
            log_message(f"thumbnail: {item.id} ({item.title}) rendered -> {png}  ({size_kb:.0f} KB)  [not applied]")
            return png
        item.update(thumbnail=png)
        log_message(f"thumbnail: {item.id} ({item.title}) UPDATED  ({size_kb:.0f} KB)")
        if apply_to_map_sibling:
            mi = find_map_image_item(gis, item)
            if mi is not None:
                mi.update(thumbnail=png)
                log_message(f"    map-image sibling {mi.id} ({mi.title}): thumbnail UPDATED (same PNG)")
        return png
    except Exception as e:
        reason = repr(e)[:300]
        # Stash the reason so main() can write it to the migration ledger. (We record from main(), NOT
        # here, so an importer like Step 6 that holds its own MigrationLedger instance isn't clobbered by
        # a second one opened mid-call.)
        _LAST_THUMB_ERROR[getattr(item, 'id', '?')] = reason
        log_message(f"thumbnail: {getattr(item, 'id', '?')} FAILED -- {reason}", level='error')
        return None


def _download_item_thumbnail(item, out_dir):
    """Download an item's existing thumbnail to out_dir; return the local file path, or None if the item
    has no thumbnail / the download fails. Tries Item.download_thumbnail() then the get_thumbnail() bytes."""
    try:
        p = item.download_thumbnail(out_dir)
        if p and os.path.isfile(p):
            return p
    except Exception as e:
        log_message(f"    download_thumbnail failed for {item.id}: {e}", level='warning')
    try:
        data = item.get_thumbnail()
        if data:
            tn = getattr(item, "thumbnail", None) or ""
            ext = "." + tn.rsplit(".", 1)[-1] if "." in tn else ".png"
            path = os.path.join(out_dir, f"{item.id}_thumb{ext}")
            with open(path, "wb") as fh:
                fh.write(data)
            return path
    except Exception as e:
        log_message(f"    get_thumbnail failed for {item.id}: {e}", level='warning')
    return None


def copy_thumbnail(source_item, target_item, out_dir=None, dry_run=False):
    """Copy source_item's EXISTING thumbnail onto target_item -- no print-service re-render. source_item and
    target_item may live on DIFFERENT portals (each Item uses its own gis), e.g. an Enterprise Portal item
    -> the AGOL by-reference item. Downloads the source thumbnail to out_dir and sets it via
    target_item.update(thumbnail=...). Importable. Returns the local PNG path on success, else None. Never
    raises. On failure stashes the reason in _LAST_THUMB_ERROR[target id] so callers can record it."""
    if out_dir is None:
        out_dir = OUTPUT_DIR
    try:
        os.makedirs(out_dir, exist_ok=True)
        if source_item is None or target_item is None:
            log_message("copy-thumbnail: source or target item is None -- skipped", level='warning')
            return None
        if not getattr(source_item, "thumbnail", None):
            log_message(f"copy-thumbnail: source {source_item.id} ({source_item.title}) has NO thumbnail "
                        f"-- skipped (render it first)", level='warning')
            return None
        path = _download_item_thumbnail(source_item, out_dir)
        if not path:
            log_message(f"copy-thumbnail: could not download thumbnail from {source_item.id} -- skipped",
                        level='warning')
            return None
        size_kb = os.path.getsize(path) / 1024.0
        if dry_run:
            log_message(f"copy-thumbnail: {source_item.id} -> {target_item.id} ({target_item.title}) "
                        f"downloaded {os.path.basename(path)} ({size_kb:.0f} KB)  [not applied]")
            return path
        target_item.update(thumbnail=path)
        log_message(f"copy-thumbnail: {target_item.id} ({target_item.title}) thumbnail UPDATED from "
                    f"{source_item.id} ({size_kb:.0f} KB)")
        return path
    except Exception as e:
        reason = repr(e)[:300]
        _LAST_THUMB_ERROR[getattr(target_item, 'id', '?')] = reason
        log_message(f"copy-thumbnail: {getattr(target_item, 'id', '?')} FAILED -- {reason}", level='error')
        return None


def main_copy_from():
    """--copy-from <source_id> <target_id> ...: copy source's thumbnail onto each target (all on PORTAL_URL)."""
    src_id = _flag_val("--copy-from")
    targets = [a.strip() for a in sys.argv[1:] if a.strip() and not a.startswith("--") and a.strip() != src_id]
    if not (src_id and targets):
        log_message("--copy-from needs: --copy-from <source_id> <target_id> [<target_id> ...]", level='error')
        return
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    gis = connect_basic(PORTAL_URL, key="portal", default_username=PORTAL_USERNAME)
    log_message(f"connected as {gis.users.me.username} on {gis.url}{'  [DRY RUN]' if DRY_RUN else ''}\n")
    src = gis.content.get(src_id)
    if src is None:
        log_message(f"source item {src_id} not found / not accessible -- stopping", level='error')
        return
    for tid in targets:
        tgt = gis.content.get(tid)
        if tgt is None:
            log_message(f"- target {tid}: NOT FOUND / not accessible -- skipped", level='warning')
            continue
        copy_thumbnail(src, tgt, out_dir=OUTPUT_DIR, dry_run=DRY_RUN)


def main_copy_portal_to_agol():
    """--copy-portal-to-agol: for each migration-ledger row, copy the ENTERPRISE Portal item's thumbnail
    onto the AGOL by-reference item (so the shared-to-AGOL item reuses the Portal thumbnail, no re-render)."""
    if ledger_mod is None:
        log_message("--copy-portal-to-agol needs migration_status_ledger (not importable) -- stopping", level='error')
        return
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ent = connect_basic(PORTAL_URL, key="portal", default_username=PORTAL_USERNAME)
    log_message(f"enterprise (source): {ent.users.me.username} on {ent.url}")
    agol = connect_basic(AGOL_URL, key="agol")
    log_message(f"agol (target)      : {agol.users.me.username} on {agol.url}{'  [DRY RUN]' if DRY_RUN else ''}\n")

    ledger = ledger_mod.get_ledger()
    # Honor the run-scope allowlist (MIGRATION_ITEM_ALLOWLIST, keyed by SOURCE item_id) so a --max-items
    # batch run only touches its scoped items; no-op when the env var is unset.
    rows = []
    for r in ledger.rows.values():
        # Single work-selection gate (ledger_mod.row_eligible_to_advance): skips a row outside the run-scope
        # allowlist (MIGRATION_ITEM_ALLOWLIST -- silent), carrying a recorded error (must be fixed + cleared
        # first; a thumbnail failure recorded here is itself an error), or -- via the default done_state --
        # already fully deprecated. The SAME helper the deprecate / publish / share-back stages use.
        ok, why = ledger_mod.row_eligible_to_advance(r)
        if not ok:
            if why:
                log_message(f"- skip {(r.get('item_id') or '').strip()}: {why}", level='warning')
            continue
        # This direction needs BOTH the Enterprise item and its AGOL by-reference copy.
        if not ((r.get("enterprise_item_id") or "").strip() and (r.get("agol_byref_item_id") or "").strip()):
            continue
        rows.append(r)
    log_message(f"ledger rows with both enterprise + by-reference ids: {len(rows)}\n")
    record = (RECORD_FAILURES_TO_LEDGER and not DRY_RUN)
    ok, failed = [], []
    for r in rows:
        ent_id = r["enterprise_item_id"].strip()
        by_id = r["agol_byref_item_id"].strip()
        src = ent.content.get(ent_id)
        tgt = agol.content.get(by_id)
        if src is None or tgt is None:
            log_message(f"- {ent_id} -> {by_id}: source or target not accessible -- skipped", level='warning')
            failed.append(by_id)
            continue
        png = copy_thumbnail(src, tgt, out_dir=OUTPUT_DIR, dry_run=DRY_RUN)
        (ok if png else failed).append(by_id)
        if record:
            try:
                if png:
                    ledger_mod.clear_errors(by_id, phase="thumbnail")
                else:
                    ledger_mod.record_error(by_id, _LAST_THUMB_ERROR.get(by_id, "copy-thumbnail failed"),
                                            phase="thumbnail")
            except Exception as e:
                log_message(f"    ledger update skipped for {by_id}: {e}", level='warning')
    log_message(f"\n=== done {dt.datetime.now():%Y-%m-%d %H:%M:%S} (copy-portal-to-agol) ===")
    log_message(f"   copied/ok : {len(ok)}  {ok if ok else ''}")
    log_message(f"   failed    : {len(failed)}  {failed if failed else ''}")
    log_message(f"   PNGs in   : {OUTPUT_DIR}")
    log_message(f"   log file  : {LOG_FILE}")


def main_copy_agol_to_portal():
    """--copy-agol-to-portal: for each migration-ledger row, set the ENTERPRISE item's thumbnail FROM the
    ORIGINAL AGOL item's thumbnail (copy). If the copy fails (AGOL item has no thumbnail / download fails),
    FALL BACK to regenerating the Enterprise thumbnail on the server (print service). Applies the resulting
    thumbnail to the Map Image Layer sibling too (decision #9)."""
    if ledger_mod is None:
        log_message("--copy-agol-to-portal needs migration_status_ledger (not importable) -- stopping", level='error')
        return
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    agol = connect_basic(AGOL_URL, key="agol")
    log_message(f"agol (source)      : {agol.users.me.username if agol.users.me else '?'} on {agol.url}")
    # Enterprise connection needs a TOKEN for the regenerate fallback + print service (connect_portal()
    # enforces a token; it also writes the thumbnail).
    ent = connect_portal()
    token = ent._con.token
    log_message(f"enterprise (target): {ent.users.me.username} on {ent.url}"
                f"{'  [DRY RUN]' if DRY_RUN else ''}\n")

    ledger = ledger_mod.get_ledger()
    # Honor the run-scope allowlist (MIGRATION_ITEM_ALLOWLIST, keyed by SOURCE item_id) so a --max-items
    # batch run only touches its scoped items; no-op when the env var is unset.
    rows = []
    for r in ledger.rows.values():
        # Single work-selection gate (ledger_mod.row_eligible_to_advance): skips a row outside the run-scope
        # allowlist (MIGRATION_ITEM_ALLOWLIST -- silent), carrying a recorded error (must be fixed + cleared
        # first; a thumbnail failure recorded here is itself an error), or -- via the default done_state --
        # already fully deprecated. The SAME helper the deprecate / publish / share-back stages use.
        ok, why = ledger_mod.row_eligible_to_advance(r)
        if not ok:
            if why:
                log_message(f"- skip {(r.get('item_id') or '').strip()}: {why}", level='warning')
            continue
        # This direction needs the ORIGINAL AGOL source item and its Enterprise copy.
        if not ((r.get("item_id") or "").strip() and (r.get("enterprise_item_id") or "").strip()):
            continue
        rows.append(r)
    log_message(f"ledger rows with source + enterprise ids: {len(rows)}\n")
    record = (RECORD_FAILURES_TO_LEDGER and not DRY_RUN)
    ok, failed = [], []
    for r in rows:
        src_id = r["item_id"].strip()
        ent_id = r["enterprise_item_id"].strip()
        src = agol.content.get(src_id)
        tgt = ent.content.get(ent_id)
        if tgt is None:
            log_message(f"- {ent_id}: enterprise item not accessible -- skipped", level='warning')
            failed.append(ent_id)
            continue
        # 1) try to COPY the original AGOL item's thumbnail onto the Enterprise item.
        png = copy_thumbnail(src, tgt, out_dir=OUTPUT_DIR, dry_run=DRY_RUN)
        how = "copied from AGOL"
        if png and not DRY_RUN and SYNC_MAP_IMAGE_LAYER:
            mi = find_map_image_item(ent, tgt)
            if mi is not None:
                try:
                    mi.update(thumbnail=png)
                    log_message(f"    map-image sibling {mi.id}: thumbnail set (same PNG)")
                except Exception as e:
                    log_message(f"    map-image sibling thumbnail failed: {e}", level='warning')
        # 2) FALLBACK: regenerate on the server when the copy was unavailable.
        if not png:
            log_message(f"  AGOL thumbnail unavailable for {ent_id} -> regenerating on the server")
            png = regenerate_thumbnail(ent, tgt, token=token, out_dir=OUTPUT_DIR,
                                       apply_to_map_sibling=SYNC_MAP_IMAGE_LAYER, dry_run=DRY_RUN)
            how = "regenerated on server"
        if png:
            log_message(f"- {ent_id} ({tgt.title}): thumbnail {how}")
            ok.append(ent_id)
        else:
            log_message(f"- {ent_id} ({tgt.title}): thumbnail FAILED (copy AND regenerate)", level='error')
            failed.append(ent_id)
        if record:
            try:
                if png:
                    ledger_mod.clear_errors(ent_id, phase="thumbnail")
                else:
                    ledger_mod.record_error(ent_id, _LAST_THUMB_ERROR.get(ent_id, "copy+regenerate failed"),
                                            phase="thumbnail")
            except Exception as e:
                log_message(f"    ledger update skipped for {ent_id}: {e}", level='warning')
    log_message(f"\n=== done {dt.datetime.now():%Y-%m-%d %H:%M:%S} (copy-agol-to-portal) ===")
    log_message(f"   ok     : {len(ok)}  {ok if ok else ''}")
    log_message(f"   failed : {len(failed)}  {failed if failed else ''}")
    log_message(f"   PNGs in: {OUTPUT_DIR}")
    log_message(f"   log    : {LOG_FILE}")


def main():
    # Copy modes (use an existing thumbnail instead of rendering) dispatch first.
    if _has_flag("--copy-agol-to-portal"):
        return main_copy_agol_to_portal()
    if _has_flag("--copy-portal-to-agol"):
        return main_copy_portal_to_agol()
    if _has_flag("--copy-from"):
        return main_copy_from()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    gis = connect_portal()
    token = gis._con.token
    log_message(f"connected as {gis.users.me.username} on {gis.url}  (token: {'yes' if token else 'NO'})\n")

    item_ids = resolve_items(gis)
    log_message(f"processing {len(item_ids)} item(s){'  [DRY RUN]' if DRY_RUN else ''}\n")

    # Record failures to the migration ledger (best-effort, via the centralized module functions) so a
    # failed item leaves a durable, manual-redo note. Skipped in DRY_RUN -- nothing is changed on the
    # items, so a render failure isn't a real migration gap.
    record_to_ledger = (RECORD_FAILURES_TO_LEDGER and ledger_mod is not None and not DRY_RUN)
    if record_to_ledger:
        log_message(f"migration ledger: {ledger_mod.default_ledger_path()} (failures recorded there)")

    ok, skipped, failed = [], [], []
    for iid in item_ids:
        item = gis.content.get(iid)
        if item is None:
            log_message(f"- {iid}: NOT FOUND / not accessible -- skipped", level='warning')
            skipped.append(iid)
            continue
        if not getattr(item, "layers", None):
            log_message(f"- {iid} ({item.title}): no feature layers ({item.type}) -- skipped", level='warning')
            skipped.append(iid)
            continue
        png = regenerate_thumbnail(gis, item, token=token, out_dir=OUTPUT_DIR,
                                   apply_to_map_sibling=SYNC_MAP_IMAGE_LAYER, dry_run=DRY_RUN)
        (ok if png else failed).append(iid)
        if record_to_ledger:
            try:
                if png:
                    ledger_mod.clear_errors(iid, phase="thumbnail")
                else:
                    ledger_mod.record_error(iid, _LAST_THUMB_ERROR.get(iid, "see log file"), phase="thumbnail")
            except Exception as e:
                log_message(f"    ledger update skipped for {iid}: {e}", level='warning')

    log_message(f"\n=== done {dt.datetime.now():%Y-%m-%d %H:%M:%S} ===")
    log_message(f"   updated/ok : {len(ok)}")
    log_message(f"   skipped    : {len(skipped)}  {skipped if skipped else ''}")
    log_message(f"   failed     : {len(failed)}  {failed if failed else ''}")
    if record_to_ledger and failed:
        log_message(f"   ledger     : failures recorded to {ledger_mod.default_ledger_path()} "
                    f"(where a source row maps the item id)")
    log_message(f"   PNGs in    : {OUTPUT_DIR}")
    log_message(f"   log file   : {LOG_FILE}")


if __name__ == "__main__":
    main()

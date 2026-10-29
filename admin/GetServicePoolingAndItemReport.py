'''
Name: GetServicePoolingAndItemReport.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-11

================================================================================
WHAT THIS SCRIPT DOES
================================================================================
Inventories every service published on the ArcGIS Enterprise site at
maps.rrgnbs.com and reports, for each one, the configuration you would otherwise
have to read off the ArcGIS Server Manager service page
(https://maps.rrgnbs.com/arcgisserver/manager/service.html), with a focus on:

  POOLING / INSTANCES
    - instance type (Shared vs Dedicated)
    - minInstancesPerNode, maxInstancesPerNode  (min/max instances per machine)
    - instancesPerContainer

  TIMEOUTS
    - maxUsageTime  -- the maximum time a client can use a service
    - maxWaitTime   -- the maximum time a client will wait to get a service
    - maxIdleTime   -- the maximum time an idle instance can be kept running
    - maxStartupTime

  OPERATIONS ALLOWED
    - capabilities (e.g. Map, Query, Data; Create/Delete/Query/Update/Editing/
      Sync/Extract; Image/Catalog/Mensuration/Pixels/Edit/Download)

  RECYCLING
    - recycleInterval (every # hours), recycleStartTime (starting at HH:MM)
    - keepAliveInterval (the "periodically check and repair instances" health
      check; -1 / 0 means disabled). NOTE: the public admin API exposes a single
      keep-alive interval; the Manager UI's "check every # minutes" maps to this
      value (seconds in the API, shown as minutes in the UI).

  CACHING
    - isCached, singleFusedMapCache (tiled vs dynamic for map services)
    - cacheControlMaxAge, clientCachingAllowed, cacheOnDemand, cacheDir

Then, for the portal item(s) backing each service (resolved via the service's
portalProperties.portalItems), it reports:
    - item Title, URL, Owner, Owner Folder, Tags
    - Created Date, Modified Date, Last View Date, View Count

A service may back more than one portal item (e.g. a Feature Service plus its
sibling Map Image Layer). One row is written per service; the "primary" item
(matching the service type, else the first) populates the item columns, and the
related item ids/titles/count are listed alongside. Services with no portal item
(many raster-published image services) still get a full service-properties row.

================================================================================
HOW TO OPERATE IT
================================================================================
1. Run inside the ArcGIS Pro conda env (so arcgis, requests, pandas are
   available), e.g.:
       python GetServicePoolingAndItemReport.py
2. Authentication (no prompt if a credential is stored):
   - Tries the Windows Credential Manager 'portal' entry (nbs_arcgis_admin) via
     credential_store.py first -- this should be an ArcGIS Enterprise account
     with admin privileges so the admin services API is readable.
   - Falls back to GIS("pro") (the active ArcGIS Pro session) if the store is
     unavailable or the login fails.
   Store the credential once with:  python credential_store.py set portal
3. Output is written under ./Output/ relative to the current working directory
   (gitignored). Each run is stamped with a timestamp:
     - ServicePoolingReport_<ts>.csv    -- the flat per-service report (main deliverable)
     - ServicePoolingReport_<ts>.json   -- the same rows as JSON
     - ServicePoolingReport_<ts>.log    -- the run log

Summary:   Reports pooling, timeout, operations-allowed, recycling, and caching
           settings for every service on maps.rrgnbs.com, joined to the backing
           portal item's title/url/owner/folder/tags/dates/view-count.
Usage:     python GetServicePoolingAndItemReport.py  (stored creds, else GIS("pro")).
'''

import os
import sys
import json
import logging
import datetime as dt

import requests
import pandas as pd
from arcgis.gis import GIS

# --- configuration -----------------------------------------------------------
PORTAL_URL = 'https://maps.rrgnbs.com/arcgisportal'
REST_BASE = 'https://maps.rrgnbs.com/arcgisserver/rest/services'
DEFAULT_ADMIN_USER = 'rrgadmin'
MAX_PORTAL_ITEMS = 10000

# ArcGIS Server "system" folders to skip (they hold utility/system services, not content).
SYSTEM_FOLDERS = ['System', 'Utilities']

DEBUG_MODE = False

TIMESTAMP = dt.datetime.now().strftime('%Y%m%d%H%M%S')

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(os.getcwd(), 'Output')
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Credential store (Windows Credential Manager) helper lives in this directory; best-effort import
# so logins can come from the store with a GIS("pro") fallback. If unavailable, we fall straight to pro.
sys.path.insert(0, CURRENT_DIR)
try:
    import credential_store
except Exception:
    credential_store = None

logging.basicConfig(
    filename=os.path.join(OUTPUT_DIR, f"ServicePoolingReport_{TIMESTAMP}.log"),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def log_message(message, log_level='info'):
    # Log to file; print ERROR/WARNING always, INFO to console, DEBUG only when DEBUG_MODE.
    if log_level == 'debug' and not DEBUG_MODE:
        return
    try:
        lvl = log_level.lower()
        if lvl == 'error':
            logging.error(message)
        elif lvl == 'warning':
            logging.warning(message)
        elif lvl == 'debug':
            logging.debug(message)
        else:
            logging.info(message)
        if lvl == 'info':
            print(message)
        else:
            print(f"{lvl.upper()}: {message}")
    except Exception as e:
        print(f"Failed to log message: {e}")


def convert_ms_timestamp(timestamp_ms):
    # Convert a millisecond epoch timestamp to 'YYYY-MM-DD HH:MM:SS', or None if invalid/out of range.
    if not timestamp_ms:
        return None
    try:
        seconds = timestamp_ms / 1000
        if 0 <= seconds <= 32503680000:  # up to year 3000
            return dt.datetime.fromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        log_message(f"Failed to convert timestamp {timestamp_ms}: {e}", 'debug')
    return None


def seconds_to_human(seconds):
    # Render a duration in seconds as a short human string (e.g. '600 s (10 min)'). -1/None -> 'not set'.
    if seconds is None or seconds == '':
        return ''
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    if s < 0:
        return f"{s} (disabled)"
    if s == 0:
        return '0'
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s} s ({s / 60:.0f} min)"
    return f"{s} s ({s / 3600:.1f} hr)"


def connect():
    # Connect to the ArcGIS Enterprise portal via the shared credential_store.connect() helper:
    # CREDENTIALS FIRST (the stored 'portal' admin login -- needed to read the admin services API), with
    # the active ArcGIS Pro session only as a fallback. If credential_store is unavailable, tries GIS('pro').
    if credential_store is not None:
        try:
            gis = credential_store.connect(PORTAL_URL, key='portal',
                                           default_username=DEFAULT_ADMIN_USER,
                                           log=lambda m: log_message(m, 'info'))
            log_message(f"Connected to {PORTAL_URL} as {gis.properties.user.username}")
            return gis
        except Exception as e:
            log_message(f"Failed to connect to {PORTAL_URL} via credential_store.connect(): {e}", 'error')
            return None
    log_message("credential_store unavailable; trying GIS('pro')", 'warning')
    try:
        gis = GIS('pro')
        log_message(f"Connected via GIS('pro') as {gis.properties.user.username}")
        return gis
    except Exception as e:
        log_message(f"Failed to connect via GIS('pro'): {e}", 'error')
        return None


# Per-user folder-id -> folder-title cache (for resolving an item's Owner Folder name).
user_folders = {}


def get_owner_folder_title(gis, owner, folder_id):
    # Resolve the folder title for an item's owner + ownerFolder id (cached per user). Root folder -> ''.
    if not owner or not folder_id:
        return ''
    try:
        if owner not in user_folders:
            user_folders[owner] = {}
            gis_user = gis.users.get(username=owner)
            for folder in (gis_user.folders or []):
                if isinstance(folder, dict):
                    fid = folder.get('id')
                    ftitle = folder.get('title') or folder.get('name')
                else:
                    fid = getattr(folder, 'id', None)
                    ftitle = getattr(folder, 'name', None) or getattr(folder, 'title', None)
                if fid is not None:
                    user_folders[owner][fid] = ftitle
    except Exception as e:
        log_message(f"Failed to get folders for owner '{owner}': {e}", 'debug')
    return user_folders.get(owner, {}).get(folder_id, '')


def prefetch_items(gis):
    # Build an {item_id: item_properties_dict} map of every portal item, so service->item lookups
    # don't require a REST call per service. Returns {} on failure.
    items_by_id = {}
    try:
        results = gis.content.search(query='', max_items=MAX_PORTAL_ITEMS)
        for it in results:
            try:
                items_by_id[it.id] = dict(it)
            except Exception:
                items_by_id[it.id] = {'title': getattr(it, 'title', None),
                                      'url': getattr(it, 'url', None),
                                      'owner': getattr(it, 'owner', None)}
        log_message(f"Prefetched {len(items_by_id)} portal items for service->item matching")
    except Exception as e:
        log_message(f"Failed to prefetch portal items: {e}; will fall back to content.get per service", 'warning')
    return items_by_id


def get_prop(props, key, default=None):
    # Read a key from an arcgis PropertyMap or dict, tolerating either.
    try:
        if hasattr(props, 'get'):
            return props.get(key, default)
        return getattr(props, key, default)
    except Exception:
        return default


def to_plain(obj):
    # Convert an arcgis PropertyMap (or nested) into plain dict/list for JSON dumping.
    try:
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        if isinstance(obj, dict):
            return {k: to_plain(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [to_plain(v) for v in obj]
    except Exception:
        pass
    return obj


def fetch_rest_def(gis, rest_url):
    # Best-effort fetch of a service's public REST definition (?f=json) via the authenticated
    # connection, used to read caching flags (singleFusedMapCache, cacheControlMaxAge) that are
    # not always present in the admin properties. Returns a dict or {}.
    if not rest_url:
        return {}
    try:
        data = gis._con.get(rest_url.split('?')[0], {'f': 'json'})
        if isinstance(data, dict) and not data.get('error'):
            return data
    except Exception as e:
        log_message(f"REST def fetch failed for {rest_url}: {e}", 'debug')
    return {}


def build_rest_url(folder, service_name, service_type):
    # Construct the public REST URL for a service from its folder/name/type.
    seg = f"{folder}/{service_name}" if folder else service_name
    return f"{REST_BASE}/{seg}/{service_type}"


def primary_item_id(portal_items, service_type):
    # Choose the 'primary' backing item: the one whose type matches the service type, else the first.
    if not portal_items:
        return None
    stype = (service_type or '').lower()
    for pi in portal_items:
        if (pi.get('type') or '').lower() == stype:
            return pi.get('itemID') or pi.get('itemId')
    first = portal_items[0]
    return first.get('itemID') or first.get('itemId')


def get_item_dict(gis, items_by_id, item_id):
    # Return the item properties dict for an id (from the prefetched map, else content.get fallback).
    if not item_id:
        return None
    if item_id in items_by_id:
        return items_by_id[item_id]
    try:
        it = gis.content.get(item_id)
        if it is not None:
            d = dict(it)
            items_by_id[item_id] = d
            return d
    except Exception as e:
        log_message(f"content.get failed for item {item_id}: {e}", 'debug')
    return None


def build_service_row(gis, items_by_id, server, folder, svc):
    # Assemble one report row (dict) for a single service from its admin properties + backing item.
    props = svc.properties
    service_name = get_prop(props, 'serviceName')
    service_type = get_prop(props, 'type')
    provider = get_prop(props, 'provider')

    # Pooling / instances
    min_per_node = get_prop(props, 'minInstancesPerNode')
    max_per_node = get_prop(props, 'maxInstancesPerNode')
    instances_per_container = get_prop(props, 'instancesPerContainer')
    instance_type = 'Shared' if (max_per_node == 0) else 'Dedicated'

    # Timeouts (seconds)
    max_usage = get_prop(props, 'maxUsageTime')
    max_wait = get_prop(props, 'maxWaitTime')
    max_idle = get_prop(props, 'maxIdleTime')
    max_startup = get_prop(props, 'maxStartupTime')

    # Operations allowed
    capabilities = get_prop(props, 'capabilities')

    # Recycling
    recycle_interval = get_prop(props, 'recycleInterval')      # hours
    recycle_start = get_prop(props, 'recycleStartTime')        # HH:MM
    keep_alive = get_prop(props, 'keepAliveInterval')          # seconds (health check)

    configured_state = get_prop(props, 'configuredState')
    description = get_prop(props, 'description')

    # Caching: pull from the admin 'properties' sub-dict, supplemented by the public REST def.
    inner = get_prop(props, 'properties') or {}
    rest_url = build_rest_url(folder, service_name, service_type)
    rest_def = fetch_rest_def(gis, rest_url)
    is_cached = inner.get('isCached')
    if is_cached is None:
        is_cached = rest_def.get('singleFusedMapCache')
    single_fused = rest_def.get('singleFusedMapCache')
    cache_max_age = inner.get('cacheControlMaxAge', rest_def.get('cacheControlMaxAge'))
    client_caching = inner.get('clientCachingAllowed')
    cache_on_demand = inner.get('cacheOnDemand')
    cache_dir = inner.get('cacheDir')

    # Backing portal item(s)
    portal_props = get_prop(props, 'portalProperties') or {}
    portal_items = portal_props.get('portalItems') or []
    related_ids = [pi.get('itemID') or pi.get('itemId') for pi in portal_items]
    related_ids = [i for i in related_ids if i]

    item_title = item_url = item_owner = item_owner_folder = None
    item_tags = item_created = item_modified = item_last_viewed = item_view_count = None
    related_titles = []

    prim_id = primary_item_id(portal_items, service_type)
    for iid in related_ids:
        idict = get_item_dict(gis, items_by_id, iid)
        if idict:
            related_titles.append(idict.get('title') or iid)
            if iid == prim_id:
                item_title = idict.get('title')
                item_url = idict.get('url')
                item_owner = idict.get('owner')
                item_owner_folder = get_owner_folder_title(gis, item_owner, idict.get('ownerFolder'))
                tags = idict.get('tags')
                item_tags = ', '.join(tags) if isinstance(tags, list) else tags
                item_created = convert_ms_timestamp(idict.get('created'))
                item_modified = convert_ms_timestamp(idict.get('modified'))
                item_last_viewed = convert_ms_timestamp(idict.get('lastViewed'))
                item_view_count = idict.get('numViews')

    return {
        'server': getattr(server, 'url', None),
        'folder': folder or '(root)',
        'service_name': service_name,
        'service_type': service_type,
        'provider': provider,
        'configured_state': configured_state,
        'service_rest_url': rest_url,
        # Pooling
        'instance_type': instance_type,
        'min_instances_per_node': min_per_node,
        'max_instances_per_node': max_per_node,
        'instances_per_container': instances_per_container,
        # Timeouts
        'max_usage_time_sec': max_usage,
        'max_usage_time': seconds_to_human(max_usage),
        'max_wait_time_sec': max_wait,
        'max_wait_time': seconds_to_human(max_wait),
        'max_idle_time_sec': max_idle,
        'max_idle_time': seconds_to_human(max_idle),
        'max_startup_time_sec': max_startup,
        # Operations allowed
        'operations_allowed': capabilities,
        # Recycling
        'recycle_interval_hours': recycle_interval,
        'recycle_start_time': recycle_start,
        'keep_alive_interval_sec': keep_alive,
        'keep_alive_interval': seconds_to_human(keep_alive),
        # Caching
        'is_cached': is_cached,
        'single_fused_map_cache': single_fused,
        'cache_control_max_age': cache_max_age,
        'client_caching_allowed': client_caching,
        'cache_on_demand': cache_on_demand,
        'cache_dir': cache_dir,
        # Backing portal item (primary) + related
        'item_title': item_title,
        'item_url': item_url,
        'item_owner': item_owner,
        'item_owner_folder': item_owner_folder,
        'item_tags': item_tags,
        'item_created': item_created,
        'item_modified': item_modified,
        'item_last_viewed': item_last_viewed,
        'item_view_count': item_view_count,
        'related_item_count': len(related_ids),
        'related_item_ids': '; '.join(related_ids),
        'related_item_titles': '; '.join(str(t) for t in related_titles),
        'description': description,
        'service_properties_json': json.dumps(to_plain(props), default=str),
    }


def gather(gis):
    # Walk every federated server, every folder + root, every service; build a report row each.
    rows = []
    try:
        servers = gis.admin.servers.list()
    except Exception as e:
        log_message(f"Failed to list admin servers (need an admin account): {e}", 'error')
        return rows
    if not servers:
        log_message("No federated servers returned. Ensure the account has admin privileges.", 'error')
        return rows
    log_message(f"Found {len(servers)} federated server(s)")

    items_by_id = prefetch_items(gis)

    for server in servers:
        try:
            folders = list(server.services.folders)
        except Exception as e:
            log_message(f"Failed to list folders on {getattr(server, 'url', '?')}: {e}", 'error')
            folders = []
        # Include the root (folder=None) plus every non-system folder.
        scopes = [None] + [f for f in folders if f not in SYSTEM_FOLDERS]
        for folder in scopes:
            try:
                services = server.services.list(folder=folder) if folder else server.services.list()
            except Exception as e:
                log_message(f"Failed to list services in folder '{folder}': {e}", 'error')
                continue
            log_message(f"Folder '{folder or '(root)'}': {len(services)} service(s)")
            for svc in services:
                try:
                    row = build_service_row(gis, items_by_id, server, folder, svc)
                    rows.append(row)
                    log_message(f"  {row['service_name']} ({row['service_type']}) "
                                f"[{row['instance_type']}] caps={row['operations_allowed']}", 'debug')
                except Exception as e:
                    sname = get_prop(svc.properties, 'serviceName') if hasattr(svc, 'properties') else '?'
                    log_message(f"Failed to read service '{sname}': {e}", 'error')
    return rows


def export(rows):
    # Write the report rows to CSV and JSON in OUTPUT_DIR.
    if not rows:
        log_message("No service rows to export.", 'warning')
        return
    base = os.path.join(OUTPUT_DIR, f"ServicePoolingReport_{TIMESTAMP}")
    json_path = f"{base}.json"
    csv_path = f"{base}.csv"
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=2, ensure_ascii=True)
        log_message(f"Wrote JSON report: {json_path}")
    except Exception as e:
        log_message(f"Failed to write JSON report: {e}", 'error')
    try:
        df = pd.DataFrame(rows)
        # Drop the bulky raw-properties column from the CSV (kept in JSON) for readability.
        if 'service_properties_json' in df.columns:
            df = df.drop(columns=['service_properties_json'])
        df.to_csv(csv_path, index=False, encoding='utf-8')
        log_message(f"Wrote CSV report: {csv_path}")
    except Exception as e:
        log_message(f"Failed to write CSV report: {e}", 'error')


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
log_message("Starting service pooling + item report")
start = dt.datetime.now()

gis = connect()
if gis is None:
    log_message("Could not connect to the portal; exiting.", 'error')
    sys.exit(1)

rows = gather(gis)
export(rows)

elapsed = (dt.datetime.now() - start).total_seconds()
log_message(f"Done. {len(rows)} service(s) reported in {elapsed:.0f}s. Output in: {OUTPUT_DIR}")

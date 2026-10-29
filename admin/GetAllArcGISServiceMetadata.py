'''
Name: GetAllArcGISServiceMetadata.py
Developed by: Julie Tripp
Date: 09/20/2024

================================================================================
WHAT THIS SCRIPT DOES
================================================================================
Inventories an entire ArcGIS Online (AGOL) or ArcGIS Enterprise portal and
exports a catalog of every content item, along with key metadata for each one.
It is primarily an auditing / reporting tool: use it to get a full picture of
what is published on a portal (titles, owners, sharing levels, URLs, source
data links, stored-credential flags, view counts, created/modified dates, etc.).

For each item the portal returns, the script:
  - Reads the item's properties (type, owner, owner folder, URL, title, summary,
    tags, credits, description, categories, size, content status, view count,
    last-viewed / created / modified dates).
  - Resolves the owner's folder name (caches each user's folder list).
  - Determines how the item is shared (everyone / org / private) and which
    groups it belongs to.
  - Attempts to detect a back-end data "sourceUrl" and whether the item appears
    to have stored credentials (checks Feature Service /sources and item
    typeKeywords for credential indicators).
  - For Feature/Map service items, inspects the REST service to record its
    layers and tables, which of them have attachments, and any relationships
    between layers/tables within the same service (see INCLUDE_LAYER_DETAILS).

Two run modes are controlled by module-level flags near the top of the file:
  - SUMMARY_ONLY = True  (default): fast catalog run. Pulls the item list and
    the summary metadata above. Does NOT download per-item data or crawl the
    ArcGIS Server REST services tree.
  - SUMMARY_ONLY = False (full run): in addition to the summary, saves each
    JSON-bearing item's 'description' and 'data' JSON (the two documents shown in
    ArcGIS Assistant -- see SAVE_ITEM_JSON), and crawls the full ArcGIS Server
    services directory (BASE_URL) -- every service in the root and in every
    folder -- fetching each service's definition JSON (?f=pjson) and its metadata
    XML (/info/metadata), pulling out fields like itemName, linkage, protocol,
    geographic coordinate system, and distribution format.

  - DEBUG_MODE = False (default): set True for verbose console output and to
    write traceback/debug detail to the log.
  - INCLUDE_LAYER_DETAILS = True (default): for each Feature/Map service item,
    makes one lightweight REST call to its /layers endpoint and adds these
    columns to the item catalog:
      * layer_count, table_count
      * layers / tables: per item -> id, name, type, geometryType,
        hasAttachments, objectIdField, globalIdField
      * has_attachments (any) and attachments_on (which layers/tables carry them)
      * relationship_count
      * relationships: the FULL definition of each relationship class within the
        service, with both endpoints paired by relationship id ->
          name, origin (id:name) + origin_keyField (origin primary key),
          destination (id:name) + destination_keyField (foreign key),
          cardinality (OneToOne/OneToMany/ManyToMany), composite (simple vs
          composite), attributed + relationshipTableId + keyFieldInRelationshipTable
          (for attributed / many-to-many), forwardPathLabel, backwardPathLabel.
      * relationships_summary: a readable one-line form of the above.
    These fields carry the information needed to recreate relationship classes in
    a target geodatabase (e.g. arcpy CreateRelationshipClass). NOTE: the ArcGIS
    REST API does NOT expose a relationship's message/notification direction
    (none/forward/backward/both), so that one property cannot be captured here.
    Runs in BOTH summary and full mode. Set False to skip the extra network
    calls. A single-layer item URL (.../FeatureServer/35) reports just that layer
    but still resolves relationship targets by name.
  - INCLUDE_SERVICE_ADMIN_DETAILS = True (default): query the ArcGIS Server ADMIN
    services API (gis.admin.servers) once per run and merge each service's admin
    configuration into the matching item's relevant_items row, joined by the
    service's portalProperties.portalItems item id (service-URL fallback). Adds:
      * Pooling: instance_type (Shared/Dedicated), min_instances_per_node,
        max_instances_per_node, instances_per_container
      * Timeouts: max_usage_time (max time a client can use a service),
        max_wait_time (max time a client will wait to get a service),
        max_idle_time (max time an idle instance is kept running),
        max_startup_time_sec -- each as raw *_sec plus a human-readable string
      * operations_allowed (the service 'capabilities', e.g. Map,Query,Data /
        Create,Delete,Query,Update,Editing,Sync,Extract / Image,Pixels,Edit,Download)
      * Recycling: recycle_interval_hours, recycle_start_time, keep_alive_interval
        (the "periodically check and repair instances" health check)
      * Caching: is_cached, single_fused_map_cache, cache_control_max_age,
        client_caching_allowed, cache_on_demand, cache_dir
      * service_folder, service_name_admin, service_provider, service_configured_state
    This is the ONLY source for the pooling/timeout/recycling properties (the
    public REST ?f=json definition does not expose them). Requires an admin
    account + a federated server; for AGOL (no admin server) the join is skipped
    and these columns are present but null. Runs in BOTH summary and full mode.
  - INCLUDE_APP_USAGE = True (default): lists the apps each item is used in. Scans
    the data JSON of every app -- Web AppBuilder, Instant Apps, other Web Mapping
    Applications (incl. classic Story Maps), Experience Builder (Web Experience),
    StoryMaps, Dashboards -- and every Web Map / Web Scene, matching referenced item
    ids and service URLs back to catalog items. References are followed
    transitively, so a feature layer in a web map that an app uses is credited to
    that app. Adds to every row:
      * used_in_app_count
      * used_in_apps: "<category>: <app title> (<app id>)", "; "-joined, e.g.
        "Web AppBuilder: Opportunity Viewer (98765...)"
      * used_in_app_ids: list of the app item ids
    Only apps in this portal's catalog are seen. Runs in BOTH summary and full
    mode (one extra REST call per app/map). Set False to skip.
  - SAVE_ITEM_JSON = True (default; full runs only): for each JSON-bearing item,
    saves the two JSON documents ArcGIS Assistant exposes to the DataDump folder:
      * <id>_description.json  -- the item's properties
        ({portal}/sharing/rest/content/items/{id}?f=json)
      * <id>_data.json         -- the item's data: renderer, popupInfo,
        mosaicRule, layerDefinition, etc.
        ({portal}/sharing/rest/content/items/{id}/data?f=json)
    The catalog records the saved filenames (description_json_file,
    data_json_file). If a REST call fails or returns nothing, falls back to the
    arcgis API (item.get_data() for the data document, the item object's own
    properties for the description). Honors the incremental manifest, so unchanged
    items are not re-downloaded. Set False to skip saving item JSON.

================================================================================
HOW TO OPERATE IT
================================================================================
1. Run inside the ArcGIS Pro conda env so `arcgis`, `requests`,
   `xmltodict`, `pandas`, and `tqdm` are available, e.g.:
       python GetAllArcGISServiceMetadata.py
2. Answer the interactive prompts:
   a. "Which ArcGIS portal (AGOL, NBS)"  -- press Enter for the default NBS
      (ArcGIS Enterprise at maps.rrgnbs.com), or type AGOL for ArcGIS Online
      (rrg.maps.arcgis.com). Portal URLs are hard-coded in connect_to_arcgis().
   b. Credentials: the script first tries the Windows Credential Manager (via
      credential_store.py) -- the 'portal' entry (nbs_arcgis_admin) for NBS or the
      'agol' entry (nbs_agol_user) for AGOL -- so a stored login runs unattended.
      Store once with: python credential_store.py set portal  (or  set agol).
      When no entry is stored it falls back to the interactive prompt:
        - "ArcGIS Username (not SSO)" -- a built-in portal account (NOT a single
          sign-on login); defaults to 'rrgadmin'. Use an admin account for the
          most complete inventory (and for the service ADMIN properties).
        - Password -- entered hidden via getpass; not echoed or logged.
3. The script connects with arcgis.gis.GIS(url, user, pwd) and also generates a
   REST token (used for the raw service/metadata REST calls in a full run).
4. Progress is shown with tqdm bars and console log lines; full detail goes to
   the log file. The run prints a summary banner (item count, elapsed time,
   output dir, log file name) when finished.

To switch modes or targets, edit the flags/values at the top of the file:
   SUMMARY_ONLY, DEBUG_MODE, max_arcgis_items (item cap, default 10000), and the
   portal URLs / default username inside connect_to_arcgis().

NOTE: Output is keyed by SELECTED_PORTAL, so AGOL and NBS results are kept in
separate subfolders and do not overwrite each other. Re-running appends a new
timestamp to every generated file, so prior runs are preserved.

INCREMENTAL EXPORT (full runs only): On a full run the script maintains a
per-portal manifest file and skips the expensive per-item JSON download
(description + data) for any item whose 'modified' date has NOT advanced since
the last full run, reusing the files captured then. The complete item catalog is
still rebuilt every run -- only the per-item JSON downloads are skipped -- so each
run's output is a full inventory (note: deletions are not specially tracked).
Summary-only runs neither read nor write the manifest (they never download item
JSON), so they can never falsely mark an item as already-downloaded. Delete the
manifest to force a complete re-download on the next full run.

================================================================================
WHAT IT DOWNLOADS / GENERATES
================================================================================
All output is written under a per-portal folder relative to the current working
directory:  ./Output/<PORTAL>/   (e.g. Output/NBS/ or Output/AGOL/), with a
DataDump/ subfolder for raw per-item / per-service dumps. (The Output/ tree is
gitignored.)

Files produced (each stamped with the run timestamp YYYYMMDDHHMMSS):

  Always (both modes):
   - GetAllArcGISServiceMetadata_<ts>.log
        Run log (in ./Output/, written immediately on startup).
   - ArcGIS_Items_<PORTAL>_<ts>_gis_items.json / .csv
        Raw dump of the item objects returned by gis.content.search.
   - ArcGIS_Items_<PORTAL>_<ts>_relevant_items.json / .csv
        The curated per-item metadata catalog (one row per item) -- the main
        deliverable. JSON is keyed by "<PORTAL>_<itemId>"; CSV is the flat table.
   - ArcGIS_Items_<PORTAL>_<ts>_all_gis_items.json
        The processed item dicts (with bulky 'layers'/'tables' stripped).

  Full run only (SUMMARY_ONLY = False):
   - DataDump/ArcGIS_Items_<PORTAL>_<itemId>_description.json
        The item's properties JSON (ArcGIS Assistant's /json/description), for
        JSON-bearing item types (Web Maps, Dashboards, Feature Services,
        StoryMaps, etc. -- see arcgis_items_w_json list). [SAVE_ITEM_JSON]
   - DataDump/ArcGIS_Items_<PORTAL>_<itemId>_data.json
        The item's data JSON (ArcGIS Assistant's /json/data): renderer,
        popupInfo, mosaicRule, layerDefinition, etc. [SAVE_ITEM_JSON]
   - DataDump/...<service path>..._json.json and ....xml
        Per-service definition JSON and raw metadata XML for every service in
        the ArcGIS Server REST directory (root + all folders).
   - ArcGIS_Items_<PORTAL>_<ts>_services_data.json
        Consolidated services + metadata tree crawled from BASE_URL.
   - ArcGIS_Items_<PORTAL>_manifest.json   (NOT timestamped; overwritten each run)
        Incremental-export state: per-item 'modified' date + saved JSON filenames,
        used to decide which items need re-downloading on the next full run.

Summary:   Inventories an AGOL or ArcGIS Enterprise portal and exports a catalog
           of every content item (JSON + CSV) plus, in full mode, per-item data
           and a crawl of the ArcGIS Server services directory with metadata.

Usage:     Run the script and follow the prompts (portal, username, password).
           Toggle SUMMARY_ONLY / DEBUG_MODE at the top of the file to control
           depth and verbosity. Output lands in ./Output/<PORTAL>/.

'''
import requests
import json
import xmltodict
import getpass
import os
import sys
import re
from arcgis.gis import GIS
from datetime import datetime
from tqdm import tqdm
from pprint import pprint
import pandas as pd
import traceback
import logging
import time
import warnings
import urllib3

# The arcgis API hard-codes verify_cert=False on some of its own internal portal requests, which makes
# urllib3 print an InsecureRequestWarning for each one (e.g. for rrg.maps.arcgis.com). This script's own
# requests keep normal certificate verification; silence only this warning category so the console stays
# readable. Remove this line to see the warnings again.
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

# Credential store (Windows Credential Manager) helper lives in this script's directory; best-effort
# import so logins can come from the store first, with the same interactive prompt as the fallback when
# an entry is not stored. If the module is unavailable, behavior is unchanged (always prompt).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
try:
    import credential_store
except Exception:
    credential_store = None

DEBUG_MODE = False
SUMMARY_ONLY = True
# When True, query each Feature/Map service's REST endpoint to record its layers, tables,
# attachment flags, and intra-service relationships in the item catalog. One lightweight REST
# call per service; runs in BOTH summary and full mode. Set False to skip this extra network work.
INCLUDE_LAYER_DETAILS = True
# When True, query the ArcGIS Server ADMIN services API (gis.admin.servers) once per run and merge each
# service's pooling / timeout / operations-allowed / recycling / caching settings into the matching item's
# relevant_items row (joined by the service's portalProperties.portalItems item id, with a service-URL
# fallback). This is the only source for the pooling/timeout/recycling admin properties (the public REST
# ?f=json definition does NOT expose them). Requires an admin account and a federated server (Enterprise);
# for AGOL there is no admin server, so the join is simply skipped. Runs in BOTH summary and full mode.
INCLUDE_SERVICE_ADMIN_DETAILS = True
# When True, scan every app (Web AppBuilder, Instant Apps, other Web Mapping Applications, Experience
# Builder, StoryMaps, Dashboards) plus every Web Map / Web Scene for the items they reference, and add
# used_in_app_count / used_in_apps / used_in_app_ids to each item's row. An item reached through a web
# map counts as used by the app. One data-JSON call per app/map; runs in BOTH summary and full mode.
INCLUDE_APP_USAGE = True
# When True (full runs only), save the two JSON documents ArcGIS Assistant shows for each item --
# the item 'description' (.../items/<id>?f=json) and the item 'data' (.../items/<id>/data?f=json,
# e.g. renderer / popupInfo / mosaicRule) -- to the DataDump folder. Honors the incremental
# manifest, so unchanged items are not re-downloaded.
SAVE_ITEM_JSON = True
# When True, ignore the incremental manifest and re-download EVERY item's description/data JSON
# to the DataDump folder, even for items unchanged since the last run. Use this to rebuild a
# DataDump whose files are wrong/incomplete. Full runs only (requires SUMMARY_ONLY = False).
# Can also be enabled on the command line: add --force-redownload (or --force) when launching.
FORCE_REDOWNLOAD = ('--force-redownload' in sys.argv) or ('--force' in sys.argv)

# Command-line overrides for the run-mode flags above, so a full re-download can be launched
# without editing this file: --full forces a full run (saves description/data JSON to DataDump);
# --summary forces a summary-only run.
if '--full' in sys.argv:
    SUMMARY_ONLY = False
elif '--summary' in sys.argv:
    SUMMARY_ONLY = True


ARCGIS_URL = ''
BASE_URL = ''

TIMESTAMP = datetime.now().strftime('%Y%m%d%H%M%S')

FILENAME_BASE = 'ArcGIS_Items_'
SELECTED_PORTAL = None

gis = None
token = None
arcgis_username = None
arcgis_password = None
max_arcgis_items = 10000

# hard-coded list of ArcGIS item types that are Text/JSON or JSON from https://developers.arcgis.com/rest/users-groups-and-items/items-and-item-types/
# arcgis_items_w_json = ['Dashboard', 'Web Map', 'Feature Collection']
arcgis_items_w_json = ['Dashboard', 'Web Map', 'Feature Collection', '360 VR Experience', 'Map Area', 'Web Scene', 
                       'Feature Collection Template', 'Feature Service', 'Group Layer', 'Image Service', 'Map Service',
                       'Oriented Imagery Catalog', 'Relational Database Connection', '3DTilesService', 'Scene Service',
                       'Vector Tile Service', 'WFS', 'WMTS', 'Dashboard', 'Data Pipeline', 'Deep Learning Studio Project',
                       'Esri Classification Schema', 'Excalibur Imagery Project','GeoBIM Application', 'GeoBIM Project',
                       'Hub Event', 'Hub Initiative', 'Hub Initiative Template', 'Hub Page', 'Hub Project', 'Hub Site Application', 
                       'Insights Workbook', 'Insights Model', 'Insights Page', 'Insights Theme', 'Investigation', 'Knowledge Studio Project',
                       'Mission', 'Mobile Application', 'Ortho Mapping Project', 'Ortho Mapping Template', 'Solution', 'StoryMap',
                       'Web AppBuilder Widget', 'Web Experience', 'Web Experience Template', 'Web Mapping Application', 'Workforce Project', 
                       'Color Set', 'Content Category Set', 'StoryMap Theme', 'Style', 'Symbol Set']

user_folders = {}

CURRENT_DIR = os.getcwd()
OUTPUT_DIR = CURRENT_DIR
OUTPUT_DIR = os.path.join(CURRENT_DIR, 'Output')
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
DUMP_OUTPUT_DIR = OUTPUT_DIR


logging.basicConfig(
        filename=os.path.join(OUTPUT_DIR, f"GetAllArcGISServiceMetadata_{TIMESTAMP}.log"),
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
def log_message(message, log_level='info'):
    """Log a message to file and optionally print to console.
    
    Always prints ERROR and WARNING messages. Prints INFO messages to console
    so the user can see progress. DEBUG messages only print when DEBUG_MODE is True.
    """
    if log_level == 'debug' and not DEBUG_MODE:
        return
    try:
        if log_level.lower() == 'error':
            logging.error(message)
        elif log_level.lower() == 'warning':
            logging.warning(message)
        elif log_level.lower() == 'debug':
            logging.debug(message)
        else:
            logging.info(message)
        if DEBUG_MODE:
            print(f"DEBUG: {message}")
        elif log_level.lower() != 'info':
            print(f"{log_level.upper()}: {message}")
        # else:
        #     print(f"  {message}")
    except Exception as e:
        print(f"Failed to log message: {e}", 'error')

def convert_ms_timestamp(timestamp_ms, item_id='', field_name='timestamp'):
    # Convert a millisecond epoch timestamp to a formatted datetime string.
    # Returns None if the timestamp is invalid or out of range (before 1970 or after year 3000).
    if not timestamp_ms:
        return None
    try:
        timestamp_seconds = timestamp_ms / 1000
        if 0 <= timestamp_seconds <= 32503680000:  # Unix timestamp for year 3000
            return datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S')
        else:
            log_message(f"Invalid {field_name} timestamp for {item_id}: {timestamp_ms}", 'debug')
            return None
    except Exception as e:
        log_message(f"Failed to convert {field_name} timestamp of {timestamp_ms} for {item_id}: {e}", 'debug')
        return None

def get_user_folder_title(user, folder_id):
    """
    Get the folder title for a user and folder ID.
    """
    global user_folders
    # log_message(user)
    # log_message(folder_id)
    try:
        if user not in user_folders:
            user_folders[user] = {}
            gis_user = gis.users.get(username=user)
            # log_message(gis_user)
            # log_message(gis_user.folders)
            for folder in gis_user.folders:
                # arcgis API >= 2.3 returns Folder objects (not dicts) from User.folders.
                # Support both: object attributes (id/name/title) and the legacy dict form.
                if isinstance(folder, dict):
                    folder_key = folder.get('id')
                    folder_title = folder.get('title') or folder.get('name')
                else:
                    folder_key = getattr(folder, 'id', None)
                    folder_title = getattr(folder, 'name', None) or getattr(folder, 'title', None)
                    # Fall back to the raw properties if the attributes were not present.
                    if (folder_key is None or folder_title is None) and hasattr(folder, 'properties'):
                        try:
                            props = folder.properties
                            if folder_key is None:
                                folder_key = props.get('id')
                            if folder_title is None:
                                folder_title = props.get('title') or props.get('name')
                        except Exception:
                            pass
                if folder_key is not None:
                    user_folders[user][folder_key] = folder_title
    except Exception as e:
        log_message(f"Failed to get user folders for {user}: {e}", 'error')
        
    return user_folders[user].get(folder_id, '')

def get_user_input(prompt, default_value='', value_to_check=''):
    # Prompt the user for input with an optional default value. Skips prompt if value_to_check is provided.
    if value_to_check != '' and not value_to_check is None:
        return value_to_check
    input_prompt = prompt
    # if input_prompt does not begin with a tab
    if not input_prompt.startswith('\t'):
        input_prompt = '**  ' + input_prompt
    if default_value != '':
        input_prompt += f" (Press enter to default to '{default_value}')"
    user_input = input(f"{input_prompt}: ")
    user_input = user_input.strip()
    if user_input == '' or user_input is None:
        user_input = default_value
    print(f"{prompt}: {user_input}")
    return user_input

def _resolve_cred(key, label, default_username=''):
    """Return (username, password) from the Windows Credential Manager via credential_store, falling back
    to the same interactive prompt as before when the store is unavailable or the entry is not stored.
    `key` is 'agol' (AGOL -> nbs_agol_user) or 'portal' (Enterprise -> nbs_arcgis_admin)."""
    if credential_store is not None:
        try:
            return credential_store.resolve(key, label, default_username=default_username,
                                            log=lambda m: log_message(m, 'info'))
        except Exception as e:
            log_message(f"credential_store.resolve failed ({e}); prompting instead", 'warning')
    user = get_user_input("ArcGIS Username (not SSO)", default_value=default_username)
    pwd = getpass.getpass(f"**  ArcGIS Password for {user}: ")
    return user, pwd

def connect_to_arcgis():
    # Prompt the user to select a portal and authenticate. Returns True if connected successfully.
    global ARCGIS_URL, BASE_URL, SELECTED_PORTAL, FILENAME_BASE, gis, arcgis_username, arcgis_password
    connected = False

    # ArcGIS Online
    arcgis_url_agol = 'https://rrg.maps.arcgis.com'
    base_url_agol = 'https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services'
    # New ArcGIS Enterprise
    arcgis_url_nbs = 'https://maps.rrgnbs.com/arcgisportal'
    base_url_nbs = 'https://maps.rrgnbs.com/arcgisserver/rest/services'
    # base_url_nbs = 'https://maps.rrgnbs.com/arcgisserver/rest/services/'
    # # Old ArcGIS Enterprise
    # arcgis_url_rrg = 'https://gis.renewablegroup.com/portal'
    # base_url_rrg = 'https://gis.renewablegroup.com/server/rest/services'
    
    which_portal = get_user_input("Which ArcGIS portal (AGOL, NBS)", default_value='NBS')   # RRG, 
    which_portal = which_portal.upper()
    if which_portal.startswith('A'):
        ARCGIS_URL = arcgis_url_agol
        BASE_URL = base_url_agol
        SELECTED_PORTAL = 'AGOL'
        FILENAME_BASE = 'ArcGIS_Items_AGOL'
    else:
        ARCGIS_URL = arcgis_url_nbs
        BASE_URL = base_url_nbs
        SELECTED_PORTAL = 'NBS'
        FILENAME_BASE = 'ArcGIS_Items_NBS'
    '''
    elif which_portal.startswith('R'):
        ARCGIS_URL = arcgis_url_rrg
        BASE_URL = base_url_rrg
        SELECTED_PORTAL = 'RRG'
        FILENAME_BASE = 'ArcGIS_Items_RRG'
    '''
    
    # # Get ArcGIS URL from the user or default to 'https://maps.rrgnbs.com/arcgisportal'
    # ARCGIS_URL = get_user_input("ArcGIS URL", default_value=ARCGIS_URL)
    
    # Connect via the shared credential_store.connect() helper: CREDENTIALS FIRST (the Windows Credential
    # Manager entry keyed by the selected portal -- 'agol' for AGOL, 'portal' for the NBS Enterprise admin),
    # with the active ArcGIS Pro session only as a fallback. credential_store.connect() prompts (and offers
    # to save) when nothing is stored. Store once with `python credential_store.py set <key>`. When the
    # shared module isn't importable, fall back to the prompt + GIS() login as before.
    cred_key = 'agol' if SELECTED_PORTAL == 'AGOL' else 'portal'
    cred_label = 'ArcGIS Online' if SELECTED_PORTAL == 'AGOL' else 'ArcGIS Enterprise portal admin'
    if credential_store is not None:
        try:
            gis = credential_store.connect(ARCGIS_URL, key=cred_key, default_username='rrgadmin',
                                           log=lambda m: log_message(m, 'info'))
            connected = True
            arcgis_username = gis.properties.user.username
            log_message(f"Connected to {ARCGIS_URL} as {arcgis_username}")
        except Exception as e:
            log_message(f"Failed to connect to {ARCGIS_URL} via credential_store.connect(): {e}", 'error')
    else:
        # Fallback when the shared module isn't importable: prompt, then log in directly.
        arcgis_username, arcgis_password = _resolve_cred(cred_key, cred_label, default_username='rrgadmin')
        if arcgis_username == "" or arcgis_password == "":
            log_message("Missing username or password.", 'error')
        else:
            try:
                gis = GIS(ARCGIS_URL, arcgis_username, arcgis_password)
                connected = True
                log_message(f"Connected to {ARCGIS_URL} using GIS")
            except Exception as e:
                log_message(f"Failed to connect to {ARCGIS_URL} using GIS: {e}", 'error')
    return connected

def get_arcgis_token():
    # Acquire a REST API token from the ArcGIS portal.
    global token, ARCGIS_URL, arcgis_username, arcgis_password
    if token != '' and token is not None:
        return token
    # Preferred: reuse the token from the already-authenticated GIS connection (set in connect_to_arcgis()).
    # This is the only path when the login came from credential_store.connect() (which does not retain the
    # password), and avoids a second generateToken round-trip / prompt in the username/password case too.
    try:
        if gis is not None and getattr(gis, '_con', None) is not None and gis._con.token:
            token = gis._con.token
            return token
    except Exception as e:
        log_message(f"Could not get token from the GIS connection; will generate one: {e}", 'debug')
    # Fallback: generate a token from username/password (legacy path; used only if the module-level login
    # did not yield a reusable token).
    arcgis_username = get_user_input("ArcGIS Username", default_value='rrgadmin', value_to_check=arcgis_username)
    if arcgis_username == '':
        log_message("Username is required", 'error')
        return token
    if arcgis_password is None or arcgis_password == '':
        arcgis_password = getpass.getpass(f"Password for {arcgis_username}: ")
    if arcgis_password == '':
        log_message("Password is required", 'error')
        return token
    url = f"{ARCGIS_URL}/sharing/rest/generateToken"
    data = {
        'username': arcgis_username,
        'password': arcgis_password,
        'referer': ARCGIS_URL,
        'f': 'json'
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            token = json.loads(response.text)['token']
        else:
            log_message(f"Failed to get token: {response.status_code}", 'error')
    except Exception as e:
        log_message(f"Failed to get token: {e}", 'error')
    return token

def get_headers():
    # Return authorization headers using the current REST API token.
    token = get_arcgis_token()
    if token == '':
        return {}
    return {"Authorization": f"Bearer {token}"}

def get_all_values_from_key(data, key):
    # Recursively search nested dicts/lists for all values matching the given key.
    values = []
    
    if data is None:
        return values
    
    try:
        if hasattr(data, 'to_dict'):
            data = data.to_dict()
    except Exception as e:
        data = data
        
    try:
        # If data is a dictionary, look for the key
        if isinstance(data, dict):
            # check if key is in the dictionary
            if key in data:
                for k, v in data.items():
                    if k == key:
                        values.append(v)
                    # Recursively search nested dictionaries or lists
                    if isinstance(v, (dict, list)):
                        values.extend(get_all_values_from_key(v, key))

        # If data is a list, iterate through the list and search each item
        elif isinstance(data, list):
            for item in data:
                values.extend(get_all_values_from_key(item, key))
    except Exception as e:
        log_message(f"Failed to get all values from key: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
            
    return values

def get_value_from_key(data, key):
    # Return a single value for the key if found once, a list if found multiple times, or None.
    value = get_all_values_from_key(data, key)
    try:
        if value is None or value == [] or value == '' or len(value) == 0:
            return None
        if len(value) == 1:
            return value[0]
        else:
            return value
    except Exception as e:
        return value

def fetch_rest_json(url):
    # GET JSON from an ArcGIS REST endpoint for lightweight service introspection.
    # Unlike get_json(), this does NOT save the response to disk.
    #
    # Routes the request through the authenticated arcgis API connection (gis._con) when one
    # is available. That connection handles the portal token, referer binding, and the
    # federated hosting / proxy hosts (services.arcgis.com hosted layers, utility.arcgis.com
    # /usrsvcs/ stored-credential proxies) that a hand-rolled Bearer header does NOT. Without
    # it, secured and proxied services return "Token Required" / "Invalid token" and the item
    # ends up with no layer_count/table_count. Falls back to an unauthenticated request for
    # external services not on our portal (e.g. a public ArcGIS Server an item points at).
    if not url:
        return None
    base = url.split('?')[0]
    # 1) Preferred: the authenticated portal connection.
    if gis is not None and getattr(gis, '_con', None) is not None:
        try:
            data = gis._con.get(base, {'f': 'json'})
            if isinstance(data, dict):
                if data.get('error'):
                    log_message(f"REST error from {base} (authenticated): {data.get('error')}", 'debug')
                else:
                    return data
            elif data is not None:
                return data
        except Exception as e:
            log_message(f"Authenticated fetch of {base} failed ({e}); retrying unauthenticated", 'debug')
    # 2) Fallback: unauthenticated request (external/public services, or no active session).
    sep = '&' if '?' in url else '?'
    full_url = f"{url}{sep}f=json"
    try:
        response = requests.get(full_url, timeout=30)
        if response.status_code == 200 and response.content.strip():
            data = response.json()
            if isinstance(data, dict) and data.get('error'):
                log_message(f"REST error from {full_url}: {data.get('error')}", 'debug')
                return None
            return data
        log_message(f"Failed to fetch {full_url}: status {response.status_code}", 'debug')
    except Exception as e:
        log_message(f"Failed to fetch REST JSON from {full_url}: {e}", 'debug')
    # 3) Fallback: with headers
    try:
        for known in (BASE_URL, ARCGIS_URL):
            if known:
                known_host = known.split('/rest/')[0].lower().rstrip('/')
                if known_host and url.lower().startswith(known_host):
                    headers = get_headers()
                    break
        try:
            response = requests.get(full_url, headers=headers, timeout=30)
            if response.status_code == 200 and response.content.strip():
                data = response.json()
                if isinstance(data, dict) and data.get('error'):
                    log_message(f"REST error from {full_url}: {data.get('error')}", 'debug')
                    return None
                return data
            log_message(f"Failed to fetch {full_url}: status {response.status_code}", 'debug')
        except Exception as e:
            log_message(f"Failed to fetch REST JSON from {full_url}: {e}", 'debug')
    except Exception:
        log_message(f"Failed to get headers for {full_url}", 'debug')
    return None

def summarize_service_layers(service_url):
    # Inspect a Feature/Map service and summarize its layers, tables, attachment flags,
    # and intra-service relationships. Returns a dict (see keys below) or None.
    #
    # Handles both a service-root URL (.../FeatureServer -> all layers/tables) and a
    # single-layer URL (.../FeatureServer/35 -> just that layer, while still resolving
    # relationship targets against the full service). Uses the service's /layers endpoint,
    # which returns every layer and table definition (with hasAttachments + relationships)
    # in a single request; falls back to per-layer requests if /layers is unavailable.
    if not service_url:
        return None
    base = service_url.split('?')[0].rstrip('/')
    # A trailing /<number> means the item points at one specific layer or table.
    m = re.search(r'/(\d+)$', base)
    single_id = int(m.group(1)) if m else None
    service_root = base[:m.start()] if m else base

    layers_raw = []
    tables_raw = []
    data = fetch_rest_json(f"{service_root}/layers")
    if isinstance(data, dict) and ('layers' in data or 'tables' in data):
        layers_raw = data.get('layers') or []
        tables_raw = data.get('tables') or []
    else:
        # Fallback: read the service root's layer/table lists, then each definition.
        root = fetch_rest_json(service_root)
        if isinstance(root, dict):
            for entry in (root.get('layers') or []):
                detail = fetch_rest_json(f"{service_root}/{entry.get('id')}")
                layers_raw.append(detail if isinstance(detail, dict) else entry)
            for entry in (root.get('tables') or []):
                detail = fetch_rest_json(f"{service_root}/{entry.get('id')}")
                tables_raw.append(detail if isinstance(detail, dict) else entry)
    if not layers_raw and not tables_raw:
        return None

    # id -> name map across the whole service (used to resolve relationship targets).
    id_name = {}
    for obj in layers_raw + tables_raw:
        if isinstance(obj, dict) and obj.get('id') is not None:
            id_name[obj['id']] = obj.get('name', f"id {obj['id']}")

    def summarize(obj, default_type):
        return {
            'id': obj.get('id'),
            'name': obj.get('name'),
            'type': obj.get('type', default_type),
            'geometryType': obj.get('geometryType'),
            'hasAttachments': bool(obj.get('hasAttachments', False)),
            # Key fields a migration needs: relationships/attachments in an Enterprise
            # GDB are typically keyed on GlobalID, so record both ID fields.
            'objectIdField': obj.get('objectIdField'),
            'globalIdField': obj.get('globalIdField'),
        }

    # Build the full relationship definitions. A relationship class is shared by its two
    # endpoints (same relationship 'id' on both the origin and destination layer/table), but
    # each side reports only its OWN keyField. We pair both sides by id so we capture the
    # origin primary key AND the destination foreign key -- both required to recreate the
    # relationship in an Enterprise GDB (e.g. arcpy CreateRelationshipClass).
    rel_map = {}
    for obj in layers_raw + tables_raw:
        if not isinstance(obj, dict):
            continue
        oid = obj.get('id')
        oname = id_name.get(oid, '?')
        for rel in (obj.get('relationships') or []):
            rid = rel.get('id')
            related_id = rel.get('relatedTableId')
            role = rel.get('role')
            entry = rel_map.setdefault(rid, {
                'id': rid,
                'name': rel.get('name'),
                'cardinality': rel.get('cardinality'),            # OneToOne / OneToMany / ManyToMany
                'composite': rel.get('composite'),                # True=composite, False=simple
                'attributed': bool(rel.get('relationshipTableId')),
                'relationshipTableId': rel.get('relationshipTableId'),         # intermediate table (M:N / attributed)
                'keyFieldInRelationshipTable': rel.get('keyFieldInRelationshipTable'),
                'forwardPathLabel': rel.get('forwardPathLabel'),
                'backwardPathLabel': rel.get('backwardPathLabel'),
                'origin_id': None, 'origin': None, 'origin_keyField': None,
                'destination_id': None, 'destination': None, 'destination_keyField': None,
            })
            # Fill in any field that is still empty from whichever side reports it.
            for k in ('name', 'cardinality', 'composite', 'relationshipTableId',
                      'keyFieldInRelationshipTable', 'forwardPathLabel', 'backwardPathLabel'):
                if entry.get(k) in (None, '') and rel.get(k) not in (None, ''):
                    entry[k] = rel.get(k)
            if rel.get('relationshipTableId'):
                entry['attributed'] = True
            if role == 'esriRelRoleOrigin':
                entry['origin_id'] = oid
                entry['origin'] = f"{oid}:{oname}"
                entry['origin_keyField'] = rel.get('keyField')       # origin primary key
                if entry['destination_id'] is None:
                    entry['destination_id'] = related_id
                    entry['destination'] = f"{related_id}:{id_name.get(related_id, '?')}"
            elif role == 'esriRelRoleDestination':
                entry['destination_id'] = oid
                entry['destination'] = f"{oid}:{oname}"
                entry['destination_keyField'] = rel.get('keyField')  # foreign key on destination
                if entry['origin_id'] is None:
                    entry['origin_id'] = related_id
                    entry['origin'] = f"{related_id}:{id_name.get(related_id, '?')}"
            else:
                # Role not reported: best-effort, treat this object as the origin.
                if entry['origin_id'] is None:
                    entry['origin_id'] = oid
                    entry['origin'] = f"{oid}:{oname}"
                    entry['origin_keyField'] = rel.get('keyField')
                if entry['destination_id'] is None:
                    entry['destination_id'] = related_id
                    entry['destination'] = f"{related_id}:{id_name.get(related_id, '?')}"
    relationships = list(rel_map.values())

    layers = [summarize(o, 'Feature Layer') for o in layers_raw if isinstance(o, dict)]
    tables = [summarize(o, 'Table') for o in tables_raw if isinstance(o, dict)]

    # If the item points at a single layer/table, report only that one (but keep the
    # full id->name map above so relationship targets still resolve to real names).
    if single_id is not None:
        layers = [x for x in layers if x['id'] == single_id]
        tables = [x for x in tables if x['id'] == single_id]
        relationships = [r for r in relationships
                         if r['origin_id'] == single_id or r['destination_id'] == single_id]

    attachments_on = [f"{x['id']}:{x['name']}" for x in (layers + tables) if x['hasAttachments']]

    def _rel_str(r):
        kind = 'composite' if r.get('composite') else 'simple'
        attr = ', attributed' if r.get('attributed') else ''
        return (f"{r.get('name')}: {r.get('origin')}({r.get('origin_keyField')}) "
                f"-{r.get('cardinality')}-> "
                f"{r.get('destination')}({r.get('destination_keyField')}) [{kind}{attr}]")
    relationships_summary = "; ".join(_rel_str(r) for r in relationships)

    return {
        'service_root': service_root,
        'single_layer_id': single_id,
        'layer_count': len(layers),
        'table_count': len(tables),
        'layers': layers,
        'tables': tables,
        'has_attachments': len(attachments_on) > 0,
        'attachments_on': attachments_on,
        'relationship_count': len(relationships),
        'relationships': relationships,
        'relationships_summary': relationships_summary,
    }

def get_manifest_filepath():
    # Path to the per-portal incremental-export manifest (NOT timestamped; overwritten each full run).
    return os.path.join(OUTPUT_DIR, f"{FILENAME_BASE}_manifest.json")

def load_manifest():
    # Load the previous run's per-item state {item_id: {modified_ms, modified, getdata_filename}}.
    # Returns {} if no manifest exists or it can't be read. Used only on full (non-summary) runs
    # to decide which items still need a get_data() download.
    manifest_path = get_manifest_filepath()
    if not os.path.exists(manifest_path):
        log_message("No prior manifest found; all items will be downloaded this run.")
        return {}
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        manifest_items = manifest.get('items', {})
        log_message(f"Loaded manifest with {len(manifest_items)} items from '{manifest_path}' "
                    f"(last export {manifest.get('last_export_timestamp', 'unknown')})")
        return manifest_items
    except Exception as e:
        log_message(f"Failed to load manifest from '{manifest_path}': {e}. Treating all items as new.", 'warning')
        log_message(traceback.format_exc(), 'debug')
        return {}

def save_manifest(manifest_items):
    # Persist per-item modified dates + dump filenames so the next full run can skip unchanged items.
    manifest_path = get_manifest_filepath()
    try:
        manifest = {
            'portal': SELECTED_PORTAL,
            'last_export_timestamp': TIMESTAMP,
            'items': manifest_items
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=4)
        log_message(f"Saved manifest with {len(manifest_items)} items to '{manifest_path}'")
    except Exception as e:
        log_message(f"Failed to save manifest to '{manifest_path}': {e}", 'error')
        log_message(traceback.format_exc(), 'debug')

def save_item_json(item_id, item=None):
    # Fetch and save the two JSON documents ArcGIS Assistant exposes for an item (the same
    # requests as docs/plan/AGOAssistant/get_item_json.py), via the authenticated connection:
    #   description -> {ARCGIS_URL}/sharing/rest/content/items/{id}?f=json       (item properties)
    #   data        -> {ARCGIS_URL}/sharing/rest/content/items/{id}/data?f=json  (renderer/popup/etc.)
    # Both are saved to the DataDump folder, named:
    #   <portal>_<itemID>_<data|description>_<truncated title>.json
    # If an arcgis Item object is supplied, it is used as a fallback when REST fails or returns
    # nothing: item.get_data() for the data document, and the item's own properties for the
    # description. Returns (description_filename, data_filename, data_obj); any filename is None
    # if that document was empty or could not be fetched/saved.
    description_filename = None
    data_filename = None
    data_obj = None
    base = f"{ARCGIS_URL}/sharing/rest/content/items/{item_id}"

    def _is_empty(obj):
        return obj is None or obj == {} or obj == [] or obj == ''

    def _slugify_title(title, maxlen=50):
        # Make a filesystem-safe, truncated slug from an item title (or 'untitled').
        if not title:
            return 'untitled'
        s = re.sub(r'[\\/:*?"<>|]+', '_', str(title).strip())
        s = re.sub(r'\s+', '_', s)
        s = re.sub(r'_+', '_', s).strip('_')
        if len(s) > maxlen:
            s = s[:maxlen].rstrip('_')
        return s or 'untitled'

    # Filenames: <portal>_<itemID>_<data|description>_<truncated title>.json
    # The title slug is set once the description (or item) gives us a title.
    title_slug = 'untitled'

    def _write_json(obj, suffix):
        # Write a dict/list as JSON, or other content (str/bytes) as text. Returns filename or None.
        fname = f"{SELECTED_PORTAL}_{item_id}_{suffix}_{title_slug}.json"
        try:
            with open(os.path.join(DUMP_OUTPUT_DIR, fname), 'w', encoding='utf-8') as f:
                if isinstance(obj, (dict, list)):
                    json.dump(obj, f, indent=4, ensure_ascii=False)
                elif isinstance(obj, bytes):
                    f.write(obj.decode('utf-8', errors='replace'))
                else:
                    f.write(str(obj))
            return fname
        except Exception as e:
            log_message(f"Failed to save {suffix} JSON for {item_id}: {e}", 'warning')
            return None

    # --- Item description (item properties; Assistant's /json/description) ---
    description = fetch_rest_json(base)
    if _is_empty(description) and item is not None:
        # Fall back to the item object's own properties.
        try:
            if hasattr(item, 'to_dict'):
                description = item.to_dict()
        except Exception as e:
            log_message(f"Item-properties fallback failed for description of {item_id}: {e}", 'debug')

    # Resolve a title for the filename slug (description first, then the item object).
    title = None
    if isinstance(description, dict):
        title = description.get('title')
    if not title and item is not None:
        title = getattr(item, 'title', None)
    title_slug = _slugify_title(title)

    if not _is_empty(description):
        description_filename = _write_json(description, 'description')

    # --- Item data (renderer/popupInfo/mosaicRule/...; Assistant's /json/data) ---
    data_obj = fetch_rest_json(f"{base}/data")
    if _is_empty(data_obj) and item is not None:
        # REST returned nothing -- fall back to the arcgis API's get_data().
        try:
            fallback = item.get_data()  # try_json=True by default -> dict for JSON items
            if not _is_empty(fallback):
                data_obj = fallback
                log_message(f"Used item.get_data() fallback for data JSON of {item_id}", 'debug')
        except Exception as e:
            log_message(f"item.get_data() fallback failed for {item_id}: {e}", 'debug')
    if not _is_empty(data_obj):
        data_filename = _write_json(data_obj, 'data')
        
    '''
                                # item download locally to \AppData\Local\Temp\
                                item_get_data = item.get_data()
                                if item_get_data is None or item_get_data == {} or item_get_data == '' or len(item_get_data) == 0:
                                    item_get_data = item
                                    # log_message("item data is None")
                                else:
                                    # log_message("Got item data")
                                    # pprint(item_get_data)
                                    # export item_get_data to file
                                    item_data_filename =  f"{FILENAME_BASE}_{item_id}_getdata.json"
                                    item_data_filepath = os.path.join(DUMP_OUTPUT_DIR, item_data_filename)
                                    with open(item_data_filepath, 'w') as f:
                                        try:
                                            if (not isinstance(item_get_data, dict)) and (not isinstance(item_get_data, list)):
                                                if hasattr(item_get_data, 'to_dict'):
                                                    item_get_data = item_get_data.to_dict()
                                        except Exception as e:
                                            item_get_data = item_get_data

                                        if isinstance(item_get_data, dict) or isinstance(item_get_data, list):
                                            # if item_data is json
                                            json.dump(item_get_data, f, indent=4)
                                            if sourceUrl is None or sourceUrl == '' or sourceUrl == [] or sourceUrl == {} or len(sourceUrl) == 0:
                                                # sourceUrl = item_get_data.get('sourceUrl', None)
                                                sourceUrl = get_value_from_key(item_get_data, 'sourceUrl')
                                                # log_message("Got sourceUrl from item get data")
                                                # pprint(sourceUrl)

                                            # append item_get_data to item_data
                                            item_data.update(item_get_data)
                                            # exit()
                                        elif isinstance(item_get_data, str):
                                            # If it's a string, write it as-is
                                            f.write(item_get_data)
                                        else:
                                            # For other data types, convert to string before writing
                                            f.write(str(item_get_data))
                                    # log_message(f"Exported item data to {item_data_filepath}")
                            except Exception as e:
                                log_message(f"Failed to get item data: {e}", 'error')
                                log_message(traceback.format_exc(), 'debug')
    '''
    return description_filename, data_filename, data_obj

# ----------------------------------------------------------------------------
# Service ADMIN properties (pooling / timeout / operations / recycling / caching)
# ----------------------------------------------------------------------------
# These admin-only properties are NOT in the public REST (?f=json) definition; they come from the
# ArcGIS Server admin services API (gis.admin.servers). Gathered once per run and joined to items.
SERVICE_ADMIN_SYSTEM_FOLDERS = ['System', 'Utilities']

# The focus fields added to each relevant_items row (initialized to None so the columns always exist,
# even for non-service items or when no admin match is found).
SERVICE_ADMIN_FIELDS = [
    'service_folder', 'service_name_admin', 'service_provider', 'service_configured_state',
    'instance_type', 'min_instances_per_node', 'max_instances_per_node', 'instances_per_container',
    'max_usage_time_sec', 'max_usage_time', 'max_wait_time_sec', 'max_wait_time',
    'max_idle_time_sec', 'max_idle_time', 'max_startup_time_sec',
    'operations_allowed',
    'recycle_interval_hours', 'recycle_start_time', 'keep_alive_interval_sec', 'keep_alive_interval',
    'is_cached', 'single_fused_map_cache', 'cache_control_max_age', 'client_caching_allowed',
    'cache_on_demand', 'cache_dir',
]

def seconds_to_human(seconds):
    # Render a duration in seconds as a short string (e.g. '600 s (10 min)'). -1 -> disabled; None/'' -> ''.
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

def _norm_service_url(u):
    # Normalize a service URL for matching: strip whitespace, drop a trailing slash, lowercase.
    return (u or '').strip().rstrip('/').lower()

def _admin_prop(props, key, default=None):
    # Read a key from an arcgis PropertyMap or dict, tolerating either.
    try:
        if hasattr(props, 'get'):
            return props.get(key, default)
        return getattr(props, key, default)
    except Exception:
        return default

def extract_admin_service_focus(props, folder, rest_caching=None):
    # Pull the pooling / timeout / operations-allowed / recycling / caching focus fields out of one admin
    # service's properties. rest_caching (optional) supplements caching with the public REST def's
    # singleFusedMapCache / cacheControlMaxAge when the admin props don't carry them.
    max_per_node = _admin_prop(props, 'maxInstancesPerNode')
    inner = _admin_prop(props, 'properties') or {}
    rest_caching = rest_caching or {}

    is_cached = inner.get('isCached')
    if is_cached is None:
        is_cached = rest_caching.get('singleFusedMapCache')
    cache_max_age = inner.get('cacheControlMaxAge', rest_caching.get('cacheControlMaxAge'))

    max_usage = _admin_prop(props, 'maxUsageTime')
    max_wait = _admin_prop(props, 'maxWaitTime')
    max_idle = _admin_prop(props, 'maxIdleTime')
    keep_alive = _admin_prop(props, 'keepAliveInterval')

    return {
        'service_folder': folder or '(root)',
        'service_name_admin': _admin_prop(props, 'serviceName'),
        'service_provider': _admin_prop(props, 'provider'),
        'service_configured_state': _admin_prop(props, 'configuredState'),
        # Pooling
        'instance_type': 'Shared' if (max_per_node == 0) else 'Dedicated',
        'min_instances_per_node': _admin_prop(props, 'minInstancesPerNode'),
        'max_instances_per_node': max_per_node,
        'instances_per_container': _admin_prop(props, 'instancesPerContainer'),
        # Timeouts
        'max_usage_time_sec': max_usage,
        'max_usage_time': seconds_to_human(max_usage),
        'max_wait_time_sec': max_wait,
        'max_wait_time': seconds_to_human(max_wait),
        'max_idle_time_sec': max_idle,
        'max_idle_time': seconds_to_human(max_idle),
        'max_startup_time_sec': _admin_prop(props, 'maxStartupTime'),
        # Operations allowed
        'operations_allowed': _admin_prop(props, 'capabilities'),
        # Recycling
        'recycle_interval_hours': _admin_prop(props, 'recycleInterval'),
        'recycle_start_time': _admin_prop(props, 'recycleStartTime'),
        'keep_alive_interval_sec': keep_alive,
        'keep_alive_interval': seconds_to_human(keep_alive),
        # Caching
        'is_cached': is_cached,
        'single_fused_map_cache': rest_caching.get('singleFusedMapCache'),
        'cache_control_max_age': cache_max_age,
        'client_caching_allowed': inner.get('clientCachingAllowed'),
        'cache_on_demand': inner.get('cacheOnDemand'),
        'cache_dir': inner.get('cacheDir'),
    }

def get_admin_service_properties():
    # Walk every federated server (root + non-system folders) via the admin API and build two lookup maps
    # of the focus fields: by backing portal-item id (from portalProperties.portalItems) and by service URL.
    # Returns (by_item_id, by_url). Best-effort: empty maps if there's no admin server (e.g. AGOL) or no
    # admin privileges.
    by_item_id = {}
    by_url = {}
    if gis is None:
        return by_item_id, by_url
    try:
        servers = gis.admin.servers.list()
    except Exception as e:
        log_message(f"Service admin properties skipped (no admin server / privileges; normal for AGOL): {e}", 'warning')
        return by_item_id, by_url
    if not servers:
        log_message("Service admin properties skipped: no federated servers returned.", 'warning')
        return by_item_id, by_url
    log_message(f"Gathering admin service properties from {len(servers)} federated server(s)")

    service_count = 0
    for server in servers:
        try:
            folders = list(server.services.folders)
        except Exception as e:
            log_message(f"Failed to list service folders on {getattr(server, 'url', '?')}: {e}", 'warning')
            folders = []
        scopes = [None] + [f for f in folders if f not in SERVICE_ADMIN_SYSTEM_FOLDERS]
        for folder in scopes:
            try:
                services = server.services.list(folder=folder) if folder else server.services.list()
            except Exception as e:
                log_message(f"Failed to list admin services in folder '{folder}': {e}", 'warning')
                continue
            for svc in services:
                try:
                    props = svc.properties
                    service_name = _admin_prop(props, 'serviceName')
                    service_type = _admin_prop(props, 'type')
                    seg = f"{folder}/{service_name}" if folder else service_name
                    rest_url = f"{BASE_URL}/{seg}/{service_type}"

                    # Best-effort caching supplement from the public REST def (singleFusedMapCache is not
                    # in the admin props). Only for map/image services; failures are silent.
                    rest_caching = None
                    try:
                        st = (service_type or '').lower()
                        if st in ('mapserver', 'imageserver'):
                            rd = fetch_rest_json(rest_url)
                            if isinstance(rd, dict):
                                rest_caching = rd
                    except Exception:
                        rest_caching = None

                    focus = extract_admin_service_focus(props, folder, rest_caching)
                    by_url[_norm_service_url(rest_url)] = focus

                    portal_props = _admin_prop(props, 'portalProperties') or {}
                    for pi in (portal_props.get('portalItems') or []):
                        iid = pi.get('itemID') or pi.get('itemId')
                        if iid:
                            by_item_id[iid] = focus
                    service_count += 1
                except Exception as e:
                    log_message(f"Failed to read admin properties for a service in '{folder}': {e}", 'warning')
                    log_message(traceback.format_exc(), 'debug')
    log_message(f"Gathered admin properties for {service_count} service(s); "
                f"{len(by_item_id)} item id(s) matched.")
    return by_item_id, by_url

# ---------------------------------------------------------------------------------------------------
# App usage: which ArcGIS apps (Web AppBuilder, Instant Apps, other Web Mapping Applications,
# Experience Builder, StoryMaps, Dashboards) reference each item, directly or through a web map/scene.
# ---------------------------------------------------------------------------------------------------
# Item types that count as "apps" for the used_in_apps fields.
APP_ITEM_TYPES = ['Web Mapping Application', 'Web Experience', 'StoryMap', 'Dashboard']
# Container types an app reaches its layers through (app -> web map -> feature service).
APP_CONTAINER_TYPES = ['Web Map', 'Web Scene']
APP_USAGE_FIELDS = ['used_in_app_count', 'used_in_apps', 'used_in_app_ids']
ITEM_ID_PATTERN = re.compile(r'(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])')
URL_PATTERN = re.compile(r'https?://[^\s"\'<>\\]+', re.IGNORECASE)

def classify_app_type(item_type, type_keywords):
    # Return a readable app category. 'Web Mapping Application' covers several builders, which are
    # told apart by typeKeywords (Web AppBuilder, Instant Apps, classic Story Maps).
    kws = ' | '.join(str(k).lower() for k in (type_keywords or []))
    if item_type == 'Web Experience':
        return 'Experience Builder'
    if item_type == 'StoryMap':
        return 'StoryMap'
    if item_type == 'Dashboard':
        return 'Dashboard'
    if 'web appbuilder' in kws or 'webappbuilder' in kws:
        return 'Web AppBuilder'
    if 'instantapp' in kws or 'instant app' in kws:
        return 'Instant App'
    if 'story map' in kws or 'storymap' in kws:
        return 'Story Map (classic)'
    return 'Web App'

def _norm_layer_service_url(u):
    # Normalize a service/layer URL for matching: drop query string and a trailing /<layerId>, so
    # .../FeatureServer/0 in a web map matches the .../FeatureServer item URL.
    u = _norm_service_url((u or '').split('?')[0])
    return re.sub(r'/\d+$', '', u)

def _get_item_data_for_refs(item_id, item=None):
    # Fetch an item's data JSON for reference scanning (not saved to disk). Falls back to get_data().
    data = fetch_rest_json(f"{ARCGIS_URL}/sharing/rest/content/items/{item_id}/data")
    if (data is None or data == {} or data == []) and item is not None:
        try:
            data = item.get_data()
        except Exception as e:
            log_message(f"get_data() fallback failed for app-usage scan of {item_id}: {e}", 'debug')
    return data

def find_item_references(text, known_ids, ids_by_url, self_id):
    # Return the set of catalog item ids referenced in a block of text: any 32-hex id that is a known
    # catalog item, plus any service URL that matches a catalog item's URL.
    refs = set()
    if not text:
        return refs
    for m in ITEM_ID_PATTERN.findall(text):
        mid = m.lower()
        if mid in known_ids:
            refs.add(mid)
    for m in URL_PATTERN.findall(text):
        for mid in ids_by_url.get(_norm_layer_service_url(m), ()):
            refs.add(mid)
    refs.discard(self_id)
    return refs

def add_app_usage(gis_items, relevant_items):
    # For every app item, scan its data JSON (and URL) for referenced items, follow any referenced
    # Web Maps / Web Scenes one level further, and record the app on each referenced item's row as:
    #   used_in_app_count, used_in_apps ("<category>: <title> (<id>)"; "; "-joined), used_in_app_ids.
    # Apps referencing other apps (e.g. a StoryMap embedding a Dashboard) are recorded too, and that
    # embedded app's own maps/layers are followed (cycle-safe).
    items_by_id = {}
    for it in gis_items:
        try:
            items_by_id[it.id.lower()] = it
        except Exception:
            pass
    known_ids = set(items_by_id.keys())
    ids_by_url = {}
    for iid, it in items_by_id.items():
        u = it.get('url', None)
        if u:
            ids_by_url.setdefault(_norm_layer_service_url(u), set()).add(iid)

    # 1) Direct references for every app and container item.
    direct_refs = {}
    scan_types = APP_ITEM_TYPES + APP_CONTAINER_TYPES
    scan_ids = [iid for iid, it in items_by_id.items() if it.get('type', None) in scan_types]
    for iid in tqdm(scan_ids, desc="Scanning apps/maps for item references"):
        it = items_by_id[iid]
        try:
            data = _get_item_data_for_refs(it.id, it)
            if isinstance(data, (dict, list)):
                text = json.dumps(data)
            else:
                text = str(data or '')
            # Some apps (classic configurable templates) carry the web map id in the item URL.
            text += ' ' + str(it.get('url', None) or '')
            direct_refs[iid] = find_item_references(text, known_ids, ids_by_url, iid)
        except Exception as e:
            log_message(f"Failed to scan {iid} for app usage: {e}", 'warning')
            log_message(traceback.format_exc(), 'debug')
            direct_refs[iid] = set()

    # 2) Transitive closure from each app through maps/scenes/embedded apps.
    usage = {}  # referenced item id -> list of (category, title, app id)
    for iid, it in items_by_id.items():
        if it.get('type', None) not in APP_ITEM_TYPES:
            continue
        category = classify_app_type(it.get('type', None), it.get('typeKeywords', None))
        reached = set()
        stack = list(direct_refs.get(iid, ()))
        while stack:
            rid = stack.pop()
            if rid in reached or rid == iid:
                continue
            reached.add(rid)
            stack.extend(direct_refs.get(rid, ()))
        for rid in reached:
            usage.setdefault(rid, []).append((category, it.get('title', None) or '', it.id))

    # 3) Write the fields onto every row (None/0 when unused, so the columns are always present).
    for ri in relevant_items.values():
        rid = (ri.get('id') or '').lower()
        apps = sorted(usage.get(rid, []), key=lambda a: (a[0], a[1].lower()))
        ri['used_in_app_count'] = len(apps)
        ri['used_in_apps'] = '; '.join(f"{c}: {t} ({a})" for c, t, a in apps) if apps else None
        ri['used_in_app_ids'] = [a for _, _, a in apps] if apps else None
    log_message(f"App usage: {len(usage)} item(s) are referenced by at least one app")

def get_all_gis_items():
    # Query the portal for all content items, extract relevant metadata, and export to JSON/CSV.
    log_message("Getting all GIS items")
    
    relevant_items = {}
    items = []
    error_count = 0

    # Incremental export state (full runs only): prev_manifest carries each item's last-exported
    # 'modified' date + dump filename so unchanged items can skip the get_data() download.
    # Summary-only runs neither read nor write the manifest (they never call get_data()).
    prev_manifest = load_manifest() if not SUMMARY_ONLY else {}
    if FORCE_REDOWNLOAD and not SUMMARY_ONLY:
        log_message("FORCE_REDOWNLOAD enabled: ignoring manifest; re-downloading every item's "
                    "description/data JSON to the DataDump folder.")
    manifest_items = {}

    # Gather the service ADMIN properties (pooling/timeout/operations/recycling/caching) once, then join
    # them onto each service-backed item below. Best-effort: empty maps for AGOL / non-admin accounts.
    admin_by_item_id = {}
    admin_by_url = {}
    if INCLUDE_SERVICE_ADMIN_DETAILS:
        try:
            admin_by_item_id, admin_by_url = get_admin_service_properties()
        except Exception as e:
            log_message(f"Failed to gather admin service properties: {e}", 'warning')
            log_message(traceback.format_exc(), 'debug')

    if gis is None:
        return items
    try:
        query_string = ""
        # query_string = "item_type:('Geoprocesing Service', 'Image Service', 'Feature Service', 'Map Service', 'Vector Tile Package', 'Vector Tile Service', 'Web Map', 'CSV', 'CSV Collection', 'Dashboard', 'Feature Collection')"
        gis_items = gis.content.search(query=query_string, max_items=max_arcgis_items)
        log_message(f"Retrieved {len(gis_items)} GIS items")
        # export all gis_items to file
        gis_items_filename = f"{FILENAME_BASE}_{TIMESTAMP}_gis_items"
        gis_items_filepath = os.path.join(OUTPUT_DIR, f"{gis_items_filename}.json")
        gis_items_list = []
        for item in gis_items:
            gis_items_list.append(item)
        with open(gis_items_filepath, 'w') as f:
            json.dump(gis_items_list, f, indent=4)
        log_message(f"Exported GIS items to '{gis_items_filepath}'")
        # export as a csv file
        gis_items_df = pd.DataFrame(gis_items_list)
        gis_items_csv_filepath = os.path.join(OUTPUT_DIR, f"{gis_items_filename}.csv")
        gis_items_df.to_csv(gis_items_csv_filepath, index=False)
        log_message(f"Exported GIS items to '{gis_items_csv_filepath}'")
        # return items
        
        for item in tqdm(gis_items, desc="Retrieving GIS items"):
            # log_message(item)
            item_data = item
            
            # initialize relevant_item data
            item_id = None
            item_type = None
            item_owner = None
            owner_folder_name = None
            item_url = None
            item_title = None
            item_summary = None
            item_tags = None
            item_credits = None
            item_description = None
            item_size = None
            item_content_status = None
            item_categories = None
            item_group_categories = None
            item_num_views = None
            item_name = None
            item_spatial_reference = None
            item_extent = None
            item_protected = None
            item_access = None
            item_lastviewed = None
            item_created = None
            item_modified = None
            item_modified_ms = None
            service_details = None
            sourceUrl = None
            groups = []
            share_with_everyone = False
            share_with_org = False
            
            item_data_filename = None
            description_json_filename = None
            data_json_filename = None

            try:
                item_id = item_data.id
                if not SUMMARY_ONLY:
                    log_message(f"Getting item data for {item_id}", 'debug')
                    try:
                        item_data_get = gis.content.get(item_id)
                        # pprint(item_data_get)
                        if not SUMMARY_ONLY:
                            export_json_to_file(item_data_get, f"{FILENAME_BASE}_{item_id}_get")
                        item_data = item_data_get
                        log_message(f"Got item data for {item_id}", 'debug')
                    except Exception as e:
                        # just keep going with the item_data that was already retrieved
                        log_message(f"Failed to get item data from GIS.content for {item_id}: {e}", 'error')
                        log_message(traceback.format_exc(), 'debug')

                log_message(f"Pulling relevant item data for {item_id}", 'debug')
                try:
                    item_type = item_data.get('type', None)
                    item_owner = item_data.get('owner', None)
                    item_url = item_data.get('url', None)
                    item_title = item_data.get('title', None)
                    item_summary = item_data.get('snippet', None)
                    item_tags = item_data.get('tags', None)
                    item_credits = item_data.get('accessInformation', None)
                    item_description = item_data.get('description', None)
                    # pprint(sourceUrl)
                    item_size = item_data.get('size', None)
                    item_content_status = item_data.get('contentStatus', None)
                    item_categories = item_data.get('categories', None)
                    item_num_views = item_data.get('numViews', None)
                    item_name = item_data.get('name', None)
                    item_spatial_reference = item_data.get('spatialReference', None)
                    item_extent = item_data.get('extent', None)
                    item_protected = item_data.get('protected', None)
                    item_access = item_data.get('access', None)
                    item_lastviewed_ms = item_data.get('lastViewed', None)
                    item_group_categories = item_data.get('groupCategories', None)
                except Exception as e:
                    log_message(f"Failed to pull some relevant item data for {item_id}: {e}", 'warning')
                    log_message(traceback.format_exc(), 'warning')
                
                try:
                    sourceUrl = get_value_from_key(item_data, 'sourceUrl')
                except Exception as e:
                    log_message(f"Failed to get sourceUrl for {item_id}: {e}", 'warning')
                    log_message(traceback.format_exc(), 'warning')
                try:
                    owner_folder_name = get_user_folder_title(item_owner, item_data.get('ownerFolder', None))
                except Exception as e:
                    log_message(f"Failed to get owner folder name for {item_id}: {e}", 'warning')
                    log_message(traceback.format_exc(), 'warning')
                
                # Check for stored credentials and data source info
                # Detect stored-credential (proxied) items and capture the real source.
                # When an AGOL item is added "by reference" with stored credentials, AGOL
                # publishes it as a Service Proxy: the item gains the "Service Proxy"
                # typeKeyword, its 'url' is rewritten to a /usrsvcs/ proxy endpoint, and a
                # 'sourceUrl' points at the underlying (secured) server. Any of these marks
                # a proxied item, and 'data_source_info' records the real source URL.
                # (Caveat: a Service Proxy can also be used purely for rate limiting without
                # stored credentials, so this may over-report in that rarer case.)
                has_stored_credentials = False
                data_source_info = None
                try:
                    type_keywords = item_data.get('typeKeywords', []) or []
                    is_service_proxy = any('service proxy' in str(kw).lower() for kw in type_keywords)
                    url_is_proxy = bool(item_url) and '/usrsvcs/' in item_url.lower()
                    if is_service_proxy or url_is_proxy or sourceUrl:
                        has_stored_credentials = True
                        data_source_info = sourceUrl
                except Exception as e:
                    log_message(f"Failed to check credentials for {item_id}: {e}", 'warning')
                    log_message(traceback.format_exc(), 'debug')
                if not has_stored_credentials:
                    try:
                        # For Feature Services, check admin info
                        if item_type == 'Feature Service' and item_url:
                            admin_url = f"{item_url}/sources?f=json"
                            admin_data = get_json(admin_url)
                            if admin_data and 'sources' in admin_data:
                                for source in admin_data['sources']:
                                    if 'connectionString' in source:
                                        data_source_info = source.get('name', 'Unknown source')
                                        # Check for authentication info
                                        if 'username' in str(source.get('connectionString', '')).lower():
                                            has_stored_credentials = True
                                            
                        # Also check the item's typeKeywords for credential indicators
                        type_keywords = item_data.get('typeKeywords', [])
                        if any('credential' in keyword.lower() for keyword in type_keywords):
                            has_stored_credentials = True
                    except Exception as e:
                        log_message(f"Failed to check credentials for {item_id}: {e}", 'error')
                        log_message(traceback.format_exc(), 'debug')
                
                item_lastviewed = convert_ms_timestamp(item_lastviewed_ms, item_id, 'lastViewed')
                item_created = convert_ms_timestamp(item_data.get('created', None), item_id, 'created')
                item_modified_ms = item_data.get('modified', None)
                item_modified = convert_ms_timestamp(item_modified_ms, item_id, 'modified')

                # Inspect Feature/Map services for layers, tables, attachments, and relationships.
                if INCLUDE_LAYER_DETAILS and item_url:
                    url_lower = item_url.lower()
                    if 'featureserver' in url_lower or 'mapserver' in url_lower:
                        try:
                            service_details = summarize_service_layers(item_url)
                            if service_details is not None:
                                log_message(
                                    f"{item_id}: {service_details['layer_count']} layer(s), "
                                    f"{service_details['table_count']} table(s), "
                                    f"{service_details['relationship_count']} relationship(s)", 'debug')
                        except Exception as e:
                            log_message(f"Failed to summarize service layers for {item_id}: {e}", 'warning')
                            log_message(traceback.format_exc(), 'debug')

                try:
                    # arcgis API >= 2.3: use Item.sharing.shared_with. The old Item.shared_with is
                    # deprecated (removed in 3.0.0). The new shared_with returns
                    # {"groups": [...], "level": SharingLevel.EVERYONE|ORG|PRIVATE}.
                    groups = []
                    share_with_everyone = False
                    share_with_org = False
                    shared_with = None
                    found = False
                    # 1) Preferred: the new sharing manager.
                    try:
                        shared_with = item.sharing.shared_with
                    except Exception as e:
                        log_message(f"Item.sharing.shared_with unavailable for {item_id}: {e}", 'debug')
                    if isinstance(shared_with, dict) and 'level' in shared_with:
                        found = True
                        # Normalize groups to JSON-safe identifiers (ids/titles), whatever the API returns.
                        for g in (shared_with.get('groups') or []):
                            if isinstance(g, str):
                                groups.append(g)
                            elif isinstance(g, dict):
                                groups.append(g.get('id') or g.get('groupid') or g.get('title') or str(g))
                            else:
                                groups.append(getattr(g, 'groupid', None) or getattr(g, 'id', None)
                                              or getattr(g, 'title', None) or str(g))
                        level_str = str(getattr(shared_with.get('level'), 'value', shared_with.get('level'))).upper()
                        if 'EVERY' in level_str or 'PUBLIC' in level_str:
                            share_with_everyone = True
                        elif 'ORG' in level_str:
                            share_with_org = True
                    # 2) Fallback: the item 'access' field (private | org | public | shared).
                    if not found:
                        access = str(item_data.get('access', '') or '').lower()
                        if access in ('public', 'org', 'private', 'shared'):
                            found = True
                            if access == 'public':
                                share_with_everyone = True
                            elif access == 'org':
                                share_with_org = True
                    # 3) Last resort: the legacy (deprecated) Item.shared_with, only if nothing else worked.
                    if not found:
                        try:
                            legacy_shared_with = item_data.shared_with
                            groups = legacy_shared_with.get("groups", [])
                            share_with_everyone = legacy_shared_with.get("everyone", False)
                            share_with_org = legacy_shared_with.get("org", False)
                        except Exception as e:
                            log_message(f"Legacy item.shared_with unavailable for {item_id}: {e}", 'debug')
                except Exception as e:
                    log_message(f"Failed to get sharing info for {item_id}: {e}", 'warning')
                    shared_with = None
                    groups = []
                    share_with_everyone = False
                    share_with_org = False
                
                '''
                item_homepage = item_data.get('homePage', None)
                item_usage = item_data.get('usage', None)
                if item_usage is not None:
                    item_month_usage = item_usage.get('30D', None)
                    item_year_usage = item_usage.get('1Y', None)
                else:
                    item_month_usage = None
                    item_year_usage = None
                '''
                
                if not SUMMARY_ONLY:
                    if SAVE_ITEM_JSON and item_type in arcgis_items_w_json:
                        # Save the item's 'description' and 'data' JSON (the two documents ArcGIS
                        # Assistant shows). Incremental export: skip the download when this item has a
                        # manifest entry from a prior full run and its 'modified' date has not advanced,
                        # reusing the JSON files recorded that run.
                        prev_entry = prev_manifest.get(item_id)
                        skip_download = False
                        if prev_entry is not None and not FORCE_REDOWNLOAD:
                            prev_modified_ms = prev_entry.get('modified_ms')
                            prev_data_filename = prev_entry.get('data_filename')
                            prev_description_filename = prev_entry.get('description_filename')
                            if (item_modified_ms is not None and prev_modified_ms is not None
                                    and item_modified_ms <= prev_modified_ms):
                                skip_download = True
                                # Reuse prior files only if they still exist on disk.
                                if prev_data_filename and os.path.exists(os.path.join(DUMP_OUTPUT_DIR, prev_data_filename)):
                                    data_json_filename = prev_data_filename
                                if prev_description_filename and os.path.exists(os.path.join(DUMP_OUTPUT_DIR, prev_description_filename)):
                                    description_json_filename = prev_description_filename
                                # If a data file was expected but is now missing, re-download to be safe.
                                if prev_data_filename and not data_json_filename:
                                    log_message(f"Prior data JSON '{prev_data_filename}' for {item_id} is missing; re-downloading", 'debug')
                                    skip_download = False
                        if skip_download:
                            log_message(f"Skipping JSON download for unchanged item {item_id} (not modified since last export)", 'debug')
                        else:
                            try:
                                description_json_filename, data_json_filename, item_get_data = save_item_json(item_id, item)
                                # Recover sourceUrl from the data JSON if we don't already have one.
                                if item_get_data and (sourceUrl is None or sourceUrl == '' or sourceUrl == []
                                                      or sourceUrl == {} or (hasattr(sourceUrl, '__len__') and len(sourceUrl) == 0)):
                                    sourceUrl = get_value_from_key(item_get_data, 'sourceUrl')
                                # Merge the data JSON into item_data for the all_gis_items export.
                                if isinstance(item_get_data, dict):
                                    try:
                                        item_data.update(item_get_data)
                                    except Exception as e:
                                        log_message(f"Failed to merge data JSON for {item_id}: {e}", 'debug')
                            except Exception as e:
                                log_message(f"Failed to get item JSON for {item_id}: {e}", 'error')
                                log_message(traceback.format_exc(), 'debug')
                        # Keep the legacy getdata_filename field pointing at the data JSON.
                        item_data_filename = data_json_filename
                        # Record this item's state for the next full run's manifest.
                        manifest_items[item_id] = {
                            'modified_ms': item_modified_ms,
                            'modified': item_modified,
                            'data_filename': data_json_filename,
                            'description_filename': description_json_filename,
                            'getdata_filename': data_json_filename
                        }
            except Exception as e:
                error_count += 1
                log_message(f"Failed to get relevant item data for {item_id}: {e}", 'error')
                log_message(traceback.format_exc(), 'debug')
            
            # record all above data
            relevant_item = {
                'SELECTED_PORTAL': SELECTED_PORTAL,
                'id': item_id,
                'type': item_type,
                'name': item_name,
                'url': item_url,
                'title': item_title,
                'access': item_access,
                'protected': item_protected,
                'spatialReference': item_spatial_reference,
                'extent': item_extent,
                'summary': item_summary,
                'tags': item_tags,
                'credits': item_credits,
                'description': item_description,
                'categories': item_categories,
                'group_categories': item_group_categories,
                'owner': item_owner,
                'owner_folder': owner_folder_name,
                'sourceUrl': sourceUrl,
                'has_stored_credentials': has_stored_credentials,
                'data_source_info': data_source_info,
                'size': item_size,
                'contentStatus': item_content_status,
                'num_views': item_num_views,
                'last_viewed': item_lastviewed,
                'created': item_created,
                'modified': item_modified,
                'groups': groups,
                'shared_with': "everyone" if share_with_everyone else "org" if share_with_org else "private",
                'layer_count': service_details.get('layer_count') if service_details else None,
                'table_count': service_details.get('table_count') if service_details else None,
                'layers': service_details.get('layers') if service_details else None,
                'tables': service_details.get('tables') if service_details else None,
                'has_attachments': service_details.get('has_attachments') if service_details else None,
                'attachments_on': service_details.get('attachments_on') if service_details else None,
                'relationship_count': service_details.get('relationship_count') if service_details else None,
                'relationships': service_details.get('relationships') if service_details else None,
                'relationships_summary': service_details.get('relationships_summary') if service_details else None
            }
            # Merge the service ADMIN focus fields (pooling / timeout / operations-allowed / recycling /
            # caching), joined by portal item id with a normalized service-URL fallback. When there's no
            # admin match (non-service item, AGOL, or non-admin account) every key is still present as None
            # so the CSV/JSON columns are stable across all rows.
            service_admin_focus = {k: None for k in SERVICE_ADMIN_FIELDS}
            admin_match = admin_by_item_id.get(item_id)
            if admin_match is None and item_url:
                admin_match = admin_by_url.get(_norm_service_url(item_url))
            if admin_match:
                service_admin_focus.update(admin_match)
            relevant_item.update(service_admin_focus)
            # 'homepage': item_homepage, 'month_usage': item_month_usage, 'year_usage': item_year_usage
            if item_data_filename is not None:
                relevant_item['getdata_filename'] = item_data_filename
            if description_json_filename is not None:
                relevant_item['description_json_file'] = description_json_filename
            if data_json_filename is not None:
                relevant_item['data_json_file'] = data_json_filename
            # append relevant_item to relevant_items with item_url as key
            item_key = SELECTED_PORTAL + '_' + item_id
            relevant_items[item_key] = relevant_item
            
            try:
                if hasattr(item_data, 'to_dict'):
                    item_dict = item_data.to_dict()
                else:
                    item_dict = item_data
            except Exception as e:
                item_dict = item_data
                log_message(f"Failed to convert item data to dict: {e}", 'warning')
            
            try:
                if item_dict is not None:
                    # log_message(item_dict)
                    # remove 'layers' from item_dict before appending to items
                    if 'layers' in item_dict:
                        # check if layers equals [] or {} or None
                        if not(item_dict['layers'] == [] or item_dict['layers'] == {} or item_dict['layers'] is None):
                            item_dict.pop('layers')
                            # add laers back with a note that it was removed
                            item_dict['layers'] = 'removed from export'
                    if 'tables' in item_dict:
                        if not(item_dict['tables'] == [] or item_dict['tables'] == {} or item_dict['tables'] is None):
                            item_dict.pop('tables')
                            # add tables back with a note that it was removed
                            item_dict['tables'] = 'removed from export'
                    items.append(item_dict)
                    # log_message("Appended item to items")
            except Exception as e:
                log_message(f"Failed to append item_dict to items: {e}", 'error')
                log_message(traceback.format_exc(), 'debug')
            
            # # debugging only
            # if sourceUrl is not None:
            #   break

        if INCLUDE_APP_USAGE:
            try:
                add_app_usage(gis_items, relevant_items)
            except Exception as e:
                log_message(f"Failed to determine app usage: {e}", 'warning')
                log_message(traceback.format_exc(), 'debug')
    except Exception as e:
        log_message(f"Failed to get all GIS items: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
        
    try:
        # Print summary of item types found
        type_counts = {}
        for ri in relevant_items.values():
            t = ri.get('type', 'Unknown')
            type_counts[t] = type_counts.get(t, 0) + 1
        log_message(f"Finished processing {len(relevant_items)} items ({error_count} errors)")
        log_message("Item types found:")
        for item_type_name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            log_message(f"  {item_type_name}: {count}")
    except Exception as e:
        log_message(f"Unable to print summary of item types: {e}", 'warning')
    
    try:
        # print relevant_items to a file
        relevant_items_filename = f"{FILENAME_BASE}_{TIMESTAMP}_relevant_items"
        relevant_items_filepath = os.path.join(OUTPUT_DIR, f"{relevant_items_filename}.json")
        with open(relevant_items_filepath, 'w') as f:
            json.dump(relevant_items, f, indent=4)
            log_message(f"Exported relevant items to {relevant_items_filepath}")
        relevant_items_list = list(relevant_items.values())
        relevant_items_df = pd.DataFrame(relevant_items_list)
        relevant_items_filepath = os.path.join(OUTPUT_DIR, f"{relevant_items_filename}.csv")
        relevant_items_df.to_csv(relevant_items_filepath, index=False)
        log_message(f"Exported relevant items to {relevant_items_filepath}")
    except Exception as e:
        log_message(f"Failed to export relevant items to file: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')

    # Persist the manifest for the next run (full runs only; summary runs never download).
    if not SUMMARY_ONLY:
        save_manifest(manifest_items)

    return items

def get_json(url):
    # Fetch JSON from a URL using the portal token. Saves the response to a local file.
    headers = get_headers()
    if headers == {}:
        return None
    response_json = None
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            if response.content.strip():
                response_json = response.json()
                json_file_name = FILENAME_BASE
                try:
                    # if url starts with BASE_URL (not case sensitive), remove that part from the url
                    if url.lower().startswith(BASE_URL.lower()):
                        json_file_name = f"{json_file_name}_{url[len(BASE_URL):]}"
                    else:
                        json_file_name = f"{json_file_name}_{url}"
                except Exception as e:
                    json_file_name = f"{json_file_name}_{url}"
                    
                # clean up json_file_name
                if '?' in json_file_name:
                    json_file_name = json_file_name.split('?')[0]
                json_file_name = json_file_name.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_')
                json_file_name = json_file_name.replace('__', '_')
                if len(json_file_name) > 100:
                    json_file_name = json_file_name[-100:]
                    
                json_file_name = f"{json_file_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}_json"
                export_json_to_file(response_json, json_file_name)
            else:
                log_message(f"Failed to get JSON from {url}: Empty content", 'warning')
        else:
            log_message(f"Failed to get JSON from {url}: code ({response.status_code}) - text ({response.text})", 'error')
            log_message(traceback.format_exc(), 'debug')
    except Exception as e:
        log_message(f"Failed to get JSON from {url}: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
    return response_json

def get_json_from_xml(url):
    # Fetch XML from a URL, save raw XML, convert to dict via xmltodict, and save as JSON.
    headers = get_headers()
    if headers == {}:
        return None
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            if response.content.strip():
                # Save raw XML content first
                xml_file_name = FILENAME_BASE
                try:
                    # if url starts with BASE_URL (not case sensitive), remove that part from the url
                    if url.lower().startswith(BASE_URL.lower()):
                        xml_file_name = f"{xml_file_name}_{url[len(BASE_URL):]}"
                    else:
                        xml_file_name = f"{xml_file_name}_{url}"
                except Exception as e:
                    xml_file_name = f"{xml_file_name}_{url}"
                
                # clean up xml_file_name
                if '?' in xml_file_name:
                    xml_file_name = xml_file_name.split('?')[0]
                xml_file_name = xml_file_name.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_')
                xml_file_name = xml_file_name.replace('__', '_')
                if len(xml_file_name) > 100:
                    xml_file_name = xml_file_name[-100:]
                    
                # Save raw XML
                xml_filename = f"{xml_file_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                xml_filepath = os.path.join(DUMP_OUTPUT_DIR, f"{xml_filename}.xml")
                try:
                    with open(xml_filepath, 'w', encoding='utf-8') as f:
                        f.write(response.content.decode('utf-8'))
                    log_message(f"Exported raw XML to file '{xml_filepath}'", 'debug')
                except Exception as e:
                    log_message(f"Failed to export raw XML to file '{xml_filename}.xml': {e}", 'warning')
                
                # Convert XML to dict and save as JSON
                response_dict = xmltodict.parse(response.content)
                json_file_name = f"{xml_file_name}.json"
                export_json_to_file(response_dict, json_file_name)
                return xmltodict.parse(response.content)
            else:
                log_message(f"Failed to get JSON from {url}: Empty content")
                return None
        else:
            log_message(f"Failed to get JSON from {url}: {response.status_code}")
            return None
    except Exception as e:
        log_message(f"Failed to get JSON from XML from {url}: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
        return None

def get_service_data(service_url, service, folder):
    # Fetch service definition JSON and metadata XML for a single ArcGIS Server service.
    if service_url is None or service_url == '':
        return
    try:
        service_data_url = f"{service_url}?f=pjson"
        service_data = get_json(service_data_url)
        if service_data is not None:
            service['data'] = service_data
        # add folder to service data
        # service['folder'] = folder
        # service['url'] = service_url

        metadata_url = f"{service_url}/info/metadata"
        metadata_data = get_json_from_xml(metadata_url)
        if metadata_data is not None:
            if 'metadata' in metadata_data:
                service['metadata'] = metadata_data['metadata']
                if 'Esri' in metadata_data['metadata']:
                    if 'DataProperties' in metadata_data['metadata']['Esri']:
                        data_properties = metadata_data['metadata']['Esri']['DataProperties']
                        if data_properties:
                            if 'itemProps' in data_properties:
                                item_properties = data_properties['itemProps']
                                if item_properties:
                                    if 'itemName' in item_properties:
                                        item_name = item_properties['itemName']
                                        if item_name:
                                            service['metadata.itemName'] = item_name['#text']
                                    if 'itemLocation' in item_properties:
                                        item_location = item_properties['itemLocation']
                                        if item_location:
                                            if 'linkage' in item_location:
                                                linkage = item_location['linkage']
                                                if linkage:
                                                    service['metadata.linkage'] = linkage['#text']
                                            if 'protocol' in item_location:
                                                protocol = item_location['protocol']
                                                if protocol:
                                                    service['metadata.protocol'] = protocol['#text']
                            if 'coordRef' in data_properties:
                                coord_ref = data_properties['coordRef']
                                if coord_ref:
                                    if 'geogcsn' in coord_ref:
                                        geogcsn = coord_ref['geogcsn']
                                        if geogcsn:
                                            service['metadata.geogcsn'] = geogcsn['#text']
                if 'distInfo' in metadata_data['metadata']:
                    dist_info = metadata_data['metadata']['distInfo']
                    if dist_info:
                        if 'distFormat' in dist_info:
                            dist_format = dist_info['distFormat']
                            if dist_format:
                                if 'formatName' in dist_format:
                                    format_name = dist_format['formatName']
                                    if format_name:
                                        service['metadata.distFormat'] = format_name['#text']
            else:
                service['metadata'] = metadata_data
    except Exception as e:
        log_message(f"Failed to get service data from {service_url}: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')

def get_all_services_data(url):
    # Retrieve service definitions and metadata for all services (and folders) at the given REST endpoint.
    test_first_n_services = 0
    
    log_message('processing url: ' + url)
    data = get_json(url)
    try:
        if data is not None:
            if 'services' in data:
                if test_first_n_services > 0:
                    services = data['services'][:test_first_n_services]
                else:
                    services = data['services']
                for service in tqdm(services, desc="Retrieving service data"):
                    service_url = f"{BASE_URL}/{service['name']}/{service['type']}"
                    get_service_data(service_url, service, '')
                if 'folders' in data:
                    log_message(f'processing {len(data["folders"])} folders')
                    for folder in tqdm(data['folders'], desc="Retrieving folder data"):
                        try:
                            log_message('processing folder: ' + folder)
                            folder_url = f"{BASE_URL}/{folder}"
                            folder_data = get_json(f"{folder_url}?f=pjson")
                            if folder_data is not None:
                                if 'services' in folder_data:
                                    log_message(f'processing {len(folder_data["services"])} services in folder {folder}')
                                    if test_first_n_services > 0:
                                        folder_services = folder_data['services'][:test_first_n_services]
                                    else:
                                        folder_services = folder_data['services']
                                    for folder_service in tqdm(folder_services, desc="Retrieving folder service data"):
                                        folder_service_url = f"{BASE_URL}/{folder_service['name']}/{folder_service['type']}"
                                        get_service_data(folder_service_url, folder_service, folder)
                                    # add folder_service data to services so it can be exported to json as data in a single file
                                    services.extend(folder_services)
                        except Exception as e:
                            log_message(f"Failed to process folder '{folder}': {e}", 'error')
                            log_message(traceback.format_exc(), 'debug')
                data['services'] = services
    except Exception as e:
        log_message(f"Failed to process services data from {url}: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
    return data

def export_json_to_file(json_data, filename):
    # Write data to a JSON file (or .txt if not serializable). Filename should omit the extension.
    if (json_data is not None):
        try:
            if (not isinstance(json_data, dict)) and (not isinstance(json_data, list)):
                if hasattr(json_data, 'to_dict'):
                    json_data = json_data.to_dict()
        except Exception as e:
            json_data = json_data
            
        try:
            if isinstance(json_data, dict) or isinstance(json_data, list):
                filename = filename + '.json'
                filepath = os.path.join(DUMP_OUTPUT_DIR, filename)
                with open(filepath, 'w') as f:
                    json.dump(json_data, f, indent=4)
            else:
                filename = filename + '.txt'
                filepath = os.path.join(DUMP_OUTPUT_DIR, filename)
                with open(filepath, 'w') as f:
                    if isinstance(json_data, str):
                        # If it's a string, write it as-is
                        f.write(json_data)
                    else:
                        # For other data types, convert to string before writing
                        f.write(str(json_data))
            log_message(f"Exported JSON to file '{filepath}'", 'debug')
        except Exception as e:
            log_message(f"Failed to export JSON to file '{filename}': {e}", 'error')

def main():
    """Main entry point: connect to portal, retrieve items/services, and export results."""
    global OUTPUT_DIR, DUMP_OUTPUT_DIR
    
    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"  GetAllArcGISServiceMetadata.py")
    print(f"  Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'SUMMARY_ONLY' if SUMMARY_ONLY else 'FULL (with service data)'}")
    print(f"  Debug: {'ON' if DEBUG_MODE else 'OFF'}")
    print(f"{'='*60}\n")
    
    # def get_layerDefinition
    
    connected_to_arcgis = connect_to_arcgis()
    if not connected_to_arcgis:
        log_message("Failed to connect to ArcGIS")
        exit()
    
    # change OUTPUT_DIR to SELECTED_PORTAL directory within Output
    OUTPUT_DIR = os.path.join(OUTPUT_DIR, SELECTED_PORTAL)
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    log_message("Output directory: " + OUTPUT_DIR)
    DUMP_OUTPUT_DIR = os.path.join(OUTPUT_DIR, 'DataDump')
    if not os.path.exists(DUMP_OUTPUT_DIR):
        os.makedirs(DUMP_OUTPUT_DIR)
    
    all_gis_items = get_all_gis_items()
    # pprint(all_gis_items)
    export_json_to_file(all_gis_items, FILENAME_BASE + '_' + TIMESTAMP + '_all_gis_items')
    # exit()

    # NOTE: Previously there was a block here that iterated all_gis_items and called
    # get_service_data() for each item's URL. This has been superseded by the
    # get_all_services_data() call below (when SUMMARY_ONLY is False).
    
    '''
    for gis_item in all_gis_items:
        item_id = gis_item['id']
        service_url = gis_item['url']
        log_message(service_url)
        if service_url is None or service_url == '':
            # rest_service_url = https://rrg.maps.arcgis.com/home/item.html?id=1d1521a1fbff4cf887e21c5927a648fc&view=service
            # rest_service_url = f"{ARCGIS_URL}/home/item.html?id={item_id}&view=service"
            rest_service_url = f"{ARCGIS_URL}/sharing/rest/content/items/{item_id}?f=json"
            log_message(rest_service_url)
            
            # get_service_data(f"{ARCGIS_URL}/sharing/rest/content/items/{item_id}", gis_item, '')
            
            rest_service_json = get_json(rest_service_url)
            if rest_service_json is not None:
                log_message(rest_service_json)
                if 'url' in rest_service_json:
                    service_url = rest_service_json['url']
                    get_service_data(service_url, gis_item, '')
                else:
                    log_message(f"Failed to get service URL from {rest_service_url}")
                    
        else:
            get_service_data(service_url, gis_item, '')
    export_json_to_file(all_gis_items, FILENAME_BASE + '_' + TIMESTAMP + '_services_data')
    # exit()
    '''
    
    if not SUMMARY_ONLY:
        url = f"{BASE_URL}/?f=pjson"
        all_services_data = get_all_services_data(url)
        export_json_to_file(all_services_data, FILENAME_BASE + '_' + TIMESTAMP + '_services_data')

    elapsed = time.time() - start_time
    elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
    print(f"\n{'='*60}")
    print(f"  Completed in {elapsed_str}")
    print(f"  Portal: {SELECTED_PORTAL} ({ARCGIS_URL})")
    print(f"  Items retrieved: {len(all_gis_items)}")
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  Log file: GetAllArcGISServiceMetadata_{TIMESTAMP}.log")
    print(f"{'='*60}\n")
    log_message('completed exporting all services data')

    # url = "https://gis.renewablegroup.com/server/rest/services/Hosted/?f=pjson"
    # all_services_data = get_all_services_data(url)

if __name__ == '__main__':
    main()
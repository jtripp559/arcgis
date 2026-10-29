# https://community.esri.com/t5/arcgis-online-questions/python-add-service-to-agol-with-stored-credentials/td-p/743194
# Import the GIS
from arcgis.gis import GIS
import os
import getpass
# import arcpy
import datetime
import logging
import chardet
import csv
import requests

portal_item_ids_to_add = []
# portal_item_ids_to_add = ['f96ef04d862c4df0ba8784727444ca3c','e7e5268c903a4aec9f18d4fc620eeaf9']

# Enterprise-only migration-default tags (decision #10) that must NOT propagate to the AGOL
# by-reference item. Stripped (case-insensitive) before the "by reference" / "stored credentials"
# pair is added, so the AGOL item ends up with the ORIGINAL AGOL tags + the by-reference pair.
MIGRATION_DEFAULT_TAGS_TO_STRIP = ["migrated from agol", "migrated"]

# Sharing level for the new AGOL by-reference item (otherwise it is created private to the creating
# user). 'private' keeps it shared to the owner only (NOT the Org). 'match_source' mirrors the ORIGINAL
# AGOL item's sharing (resolved via the migration-ledger join on enterprise_item_id); or set an explicit
# 'private' | 'org' | 'everyone'.
AGOL_SHARING_LEVEL = "private"

# Timestamp for unique naming
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# set the output_path to the Output directory within the script's directory
current_dir = os.path.dirname(os.path.abspath(__file__))

# Credential store (Windows Credential Manager) helper lives in the ArcGIS Admin root (this dir); best-effort
# import so logins can come from the store with a prompt fallback. If unavailable, behavior is unchanged.
import sys
sys.path.insert(0, current_dir)
try:
    import credential_store
except Exception:
    credential_store = None

# Migration status ledger (in ArcGIS Admin\Migrate). After a by-reference AGOL item is created we record
# its id back to the ledger (state shared_to_agol), keyed by the SOURCE item_id (joined via the Enterprise
# item id) so Phase-8 reassign/deprecate can find it. The ledger path + the write are handled by the module
# (ledger_mod.set_state); env MIGRATION_LEDGER_PATH overrides the path. Best-effort -- unavailable -> CSV log.
sys.path.insert(0, os.path.join(current_dir, "Migrate"))
try:
    import migration_status_ledger as ledger_mod
except Exception:
    ledger_mod = None

output_path = os.path.join(current_dir, 'Output')
if not os.path.exists(output_path):
    os.makedirs(output_path)

output_csv_path = os.path.join(output_path, f"AddedArcGISItem_{timestamp}.csv")
# Write the header to the CSV file
with open(output_csv_path, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['portal_item_id', 'portal_item_url', 'new_agol_item_id', 'new_agol_item_url', 'item_type', 'item_title', 'has_error', 'verified', 'verify_detail'])

# initialize the logging general_logger and error_logger to empty
general_logger = None
error_logger = None
general_log_file_path = os.path.join(output_path, f"UpdateArcGISItem_{timestamp}.log")
error_log_file_path = os.path.join(output_path, f"UpdateArcGISItem_Errors_{timestamp}.log")

portal_gis = None
portal_url = None
portal_username = None
portal_password = None
agol_gis = None
agol_url = None
agol_username = None
portal_password = None

# initialize the log_hist_data variable to an empty list
log_hist_data = []
error_count = 0

# The Enterprise item id currently being shared back. Set at the top of each main-loop iteration so
# log_message() can attribute any 'error'-level log to the right migration-ledger row (record_error resolves
# this destination id back to the SOURCE row). Blank during login / work-list build so those non-per-item
# errors are NOT recorded against any item.
current_item_id = ''
# Reentrancy guard + per-run de-dupe so the auto-record-on-error in log_message neither loops nor appends
# the same message to a row's error column more than once.
_recording_ledger_error = False
_recorded_ledger_errors = set()

def init_logging():
    global general_logger, error_logger
    
    # Create a general logger
    general_logger = logging.getLogger('general')
    general_logger.setLevel(logging.INFO)

    # Create a file handler for the general logger
    general_handler = logging.FileHandler(general_log_file_path, mode='a', encoding='utf-8')
    general_handler.setLevel(logging.INFO)

    # Add the handler to the general logger
    general_logger.addHandler(general_handler)

    # Create an error logger
    error_logger = logging.getLogger('error')
    error_logger.setLevel(logging.ERROR)

    # Create a file handler for the error logger
    error_handler = logging.FileHandler(error_log_file_path, mode='a', encoding='utf-8')
    error_handler.setLevel(logging.ERROR)

    # Add the handler to the error logger
    error_logger.addHandler(error_handler)

def log_by_type(message, log_level='info', tab_count=1):
    try:
        if message:
            msg_tabs = '\t' * tab_count
            if isinstance(message, dict):
                for key, value in message.items():
                    # print(msg)
                    msg = msg_tabs + f'key: {key}'
                    general_logger.info(msg)
                    if log_level == 'error':
                        error_logger.error(msg)
                    new_tab_count = tab_count + 1
                    log_by_type(value, log_level, new_tab_count)
            elif isinstance(message, list):
                for detail in message:
                    # print(detail)
                    msg = msg_tabs + detail
                    general_logger.info(msg)
                    if log_level == 'error':
                        error_logger.error(msg)
            else:
                # print('\t' + message)
                msg = msg_tabs + str(message)
                general_logger.info(msg)
                if log_level == 'error':
                    error_logger.error(msg)
    except Exception as e:
        log_message(f"Failed to log message by type: {e}", 'info')

def log_message(message, log_level='', message_details=None, reset_log_hist=False):
    if message == '':
        return
    global general_logger, error_logger, log_hist_data, error_count
    if log_level == 'error':
        error_count += 1
        # cycle through log_hist_data and print each message to error_logger
        for msg in log_hist_data:
            error_logger.error(msg)
    # record message to a global variable storing all the messages since reset_log_hist was set to True
    if reset_log_hist or log_level == 'error':
        # restart the log_hist_data list
        log_hist_data = []
    if log_level != 'error':
        log_hist_data.append(message)
    if log_level == '' or log_level == 'error':
        print(message)
    if log_level == '':
        log_level = 'info'
    general_logger.info(message)
    if log_level == 'error':
        error_logger.error(message)
        # Centralized ledger capture: record this error against the item currently being shared back
        # (best-effort, de-duped, reentrancy-guarded -- see _record_error_to_ledger).
        _record_error_to_ledger(message)
    log_by_type(message_details, log_level)

def _record_error_to_ledger(message):
    """Best-effort: when an 'error' is logged WHILE a specific item is being shared back, append it to that
    item's migration-status-ledger row (record_error resolves the Enterprise item id current_item_id back to
    the SOURCE row). CENTRALIZES the 'on error, record against the row' pattern so individual error sites
    don't each need their own record_error block. Skipped during login / work-list build (no item in flight)
    or when the ledger helper is unavailable; de-duped per run + reentrancy-guarded; never raises."""
    global _recording_ledger_error
    if ledger_mod is None or not current_item_id or _recording_ledger_error:
        return
    key = (current_item_id.lower(), str(message)[:300])
    if key in _recorded_ledger_errors:
        return
    _recording_ledger_error = True
    try:
        ledger_mod.record_error(current_item_id, str(message)[:300], phase="share_to_agol")
        _recorded_ledger_errors.add(key)
    except Exception:
        pass   # never let ledger recording break logging
    finally:
        _recording_ledger_error = False

def get_file_encoding(file_path):
    encoding = 'ISO-8859-1'
    try:
        with open(file_path, 'rb') as f:
            rawdata = f.read()
        result = chardet.detect(rawdata)
        encoding = result['encoding']
        log_message(f"Detected file encoding for '{file_path}': {encoding}", 'info')
    except Exception as e:
        log_message(f"Failed to get file encoding for '{file_path}': {e}", 'info')
    return encoding

def get_user_input(prompt, default_value='', value_to_check=''):
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
    log_message(f"{prompt}: {user_input}", 'info')
    return user_input

def _resolve_cred(key, label, default_username=''):
    """Return (username, password) from the Windows Credential Manager via credential_store, falling
    back to the same interactive prompt as before when the store is unavailable or the entry is missing."""
    if credential_store is not None:
        return credential_store.resolve(key, label, default_username=default_username,
                                        log=lambda m: log_message(m, 'info'))
    user = get_user_input(f"{label} Username", default_value=default_username)
    pwd = getpass.getpass(f"**  {label} Password for {user}: ")
    return user, pwd


def connect_to_arcgis():
    global portal_url, portal_gis, portal_username, portal_password
    global agol_url, agol_gis, agol_username
    
    # Both connections are REQUIRED: the Enterprise/Portal login (GPUser -> embedded stored credentials)
    # AND the AGOL login (which owns the new by-reference item). Track each separately so a failure in one
    # doesn't leave a None GIS that crashes later (e.g. portal_gis.properties).
    portal_ok = False
    agol_ok = False

    # Portal URL defaults WITHOUT prompting so this runs unattended in the pipeline (credentials still
    # come from the Windows Credential Manager via _resolve_cred). Pre-set the global to override.
    if not portal_url:
        portal_url = 'https://maps.rrgnbs.com/arcgisportal'
    log_message(f"ArcGIS portal URL: {portal_url}", 'info')

    # Get portal_username and password from the user
    portal_username, portal_password = _resolve_cred('GPUser', 'ArcGIS Portal (GPUser)',
                                                     default_username=(portal_username or 'GPUser'))
    if portal_username == "" or portal_password == "":
        log_message("Missing portal username or password.", 'error')
    else:
        try:
            portal_gis = GIS(portal_url, portal_username, portal_password)
            portal_ok = True
        except Exception as e:
            log_message(f"Failed to connect to Enterprise portal as '{portal_username}': {e}", 'error')

    # AGOL URL defaults WITHOUT prompting (unattended); pre-set the global to override.
    if not agol_url:
        agol_url = 'https://rrg.maps.arcgis.com/'
    log_message(f"ArcGIS Online URL: {agol_url}", 'info')
    agol_username, agol_password = _resolve_cred('agol', 'ArcGIS Online', default_username=agol_username)
    if agol_username == "" or agol_password == "":
        log_message("Missing AGOL username or password.", 'error')
    else:
        try:
            agol_gis = GIS(agol_url, agol_username, agol_password)
            agol_ok = True
        except Exception as e:
            log_message(f"Failed to connect to {agol_url}: {e}", 'error')

    if not portal_ok:
        log_message("Enterprise portal login (GPUser) failed -- fix the 'GPUser' credential "
                    "(python credential_store.py set GPUser) and confirm the account/password are valid.",
                    'error')
    if not agol_ok:
        log_message("AGOL login failed -- fix the 'agol' credential.", 'error')
    # Require BOTH; the caller exits if this returns False.
    return portal_ok and agol_ok

def _source_item_id_for(enterprise_item_id):
    """Return the SOURCE AGOL item id (the migration-ledger row key) whose enterprise_item_id matches
    this Enterprise portal item, or None. Best-effort -- the ledger may be unavailable."""
    if ledger_mod is None or not enterprise_item_id:
        return None
    try:
        _led = ledger_mod.get_ledger()
        return next((k for k, r in _led.rows.items()
                     if (r.get('enterprise_item_id') or '').strip() == enterprise_item_id), None)
    except Exception as e:
        log_message(f"ledger lookup skipped: {e}")
        return None


def _apply_sharing(agol_item, level):
    """Apply a sharing-level string ('private'|'org'|'everyone') using the arcgis sharing manager,
    falling back to the deprecated Item.share() on older API versions."""
    try:
        from arcgis.gis import SharingLevel
        enum_map = {"private": SharingLevel.PRIVATE, "org": SharingLevel.ORG, "everyone": SharingLevel.EVERYONE}
        agol_item.sharing.sharing_level = enum_map.get(level, SharingLevel.ORG)
    except Exception:
        agol_item.share(everyone=(level == "everyone"), org=(level in ("org", "everyone")))


def set_agol_sharing(agol_item, source_item_id):
    """Set the new AGOL by-reference item's sharing. Default AGOL_SHARING_LEVEL='match_source' mirrors
    the original AGOL item's sharing (via the ledger join); else an explicit level. Best-effort -- a
    sharing failure is logged, not fatal (the item is still created, just private)."""
    level = AGOL_SHARING_LEVEL
    try:
        if level == "match_source":
            src = agol_gis.content.get(source_item_id) if source_item_id else None
            access = ((src.access if src else "") or "").lower()
            level = {"private": "private", "org": "org", "shared": "org", "public": "everyone"}.get(access, "org")
            log_message(f"Sharing: source {source_item_id} access='{access}' -> '{level}'")
        _apply_sharing(agol_item, level)
        log_message(f"Set AGOL item sharing to '{level}': {agol_item.id}")
    except Exception as e:
        log_message(f"Failed to set AGOL item sharing ('{level}'): {e}", 'error')


def ledger_enterprise_item_ids():
    """Enterprise Feature Service item ids recorded in the migration ledger -- the share-back work list
    (one Enterprise item per migrated source item). Mirrors AddItemToCoverageShareGroup.ledger_enterprise_item_ids
    so BOTH Phase-8 'once' stages drive off the SAME ledger rows. Driving off the persistent 'Coverage Share'
    group instead (the old default) re-processed EVERY item ever added to that group -- including items from
    earlier migrations that still linger in it (e.g. 'Global runoff March'), which have no row in this ledger."""
    if ledger_mod is None:
        log_message("ledger: migration_status_ledger not importable -- no enterprise ids resolved", 'error')
        return []
    try:
        path = ledger_mod.default_ledger_path()
        # Honor the run-scope allowlist (MIGRATION_ITEM_ALLOWLIST, keyed by SOURCE item id = the row key) so
        # a --max-items batch run only touches its scoped items; no-op when the env var is unset.
        ids = []
        for k, r in ledger_mod.get_ledger().rows.items():
            # Single work-selection gate (ledger_mod.row_eligible_to_advance, done_state='shared_to_agol'):
            # skips a row outside the run-scope allowlist (MIGRATION_ITEM_ALLOWLIST -- silent), carrying a
            # recorded error (must be fixed + cleared before the by-reference item is (re)created), or already
            # at/past 'shared_to_agol' (its by-reference AGOL item exists). The SAME helper the deprecate /
            # publish / coverage-share stages use, so one place decides "is this row workable".
            ok, why = ledger_mod.row_eligible_to_advance(r, "shared_to_agol")
            if not ok:
                if why:
                    log_message(f"ledger: skip {k} -- {why}")
                continue
            eid = (r.get("enterprise_item_id") or "").strip()
            if eid:
                ids.append(eid)
        log_message(f"ledger: {len(ids)} enterprise item id(s) from {path}")
        return ids
    except Exception as e:
        log_message(f"ledger read failed: {e}", 'error')
        return []


def add_referenced_item_to_agol(gis, item_properties, item_url, owner):
    """Add the AGOL by-reference item, preferring the Folder.add() API. As of arcgis 2.3.0
    ContentManager.add() is deprecated (removed in 3.0.0) in favor of Folder.add(). Folder.add() is
    ASYNCHRONOUS and returns a concurrent.futures.Future/Job -> .result() blocks for the created Item.
    For a by-reference service the URL goes in the url= parameter (the old single data= argument is gone),
    so it is removed from item_properties here. Falls back to the legacy content.add() on API versions
    without content.folders (arcgis < 2.3)."""
    folders = getattr(gis.content, "folders", None)
    if folders is not None:
        try:
            folder = folders.get(owner=owner)            # folder=None -> the owner's Root Folder
            props = {k: v for k, v in item_properties.items() if k != "url"}
            return folder.add(item_properties=props, url=item_url).result()
        except (AttributeError, TypeError) as e:
            log_message(f"Folder.add() unavailable/changed ({e!r}); using legacy content.add()", 'info')
    # Legacy (arcgis < 2.3): ContentManager.add() with the URL passed as data=.
    return gis.content.add(data=item_url, owner=owner, item_properties=item_properties)


def _norm_url(u):
    """Normalize a service url for comparison: drop surrounding whitespace, a trailing slash, and case."""
    return (u or '').strip().rstrip('/').lower()


def find_existing_byref_item(item_title, portal_item_url):
    """Find an EXISTING AGOL by-reference item that genuinely corresponds to this portal service, so we
    don't recreate it. A title match alone is NOT sufficient -- unrelated items can share a title -- so a
    real match must ALSO satisfy both: (1) it carries the 'stored credentials' tag this script stamps on
    every by-reference item (an item without it is by definition not one of ours and can't be the match);
    AND (2) it points at the SAME service -- its url is identical to this portal item's url. Returns the
    matching Item (most-recently-modified if several qualify) or None."""
    target = _norm_url(portal_item_url)
    try:
        qry = 'title:"' + item_title + '"'
        candidates = agol_gis.content.search(query=qry, max_items=25, sort_field='modified', sort_order='desc')
    except Exception as e:
        log_message(f"AGOL search failed for '{item_title}': {e}")
        return None
    for cand in (candidates or []):
        tags_lower = {(t or '').strip().lower() for t in (cand.tags or [])}
        if 'stored credentials' not in tags_lower:
            log_message(f"Skipping title match without 'stored credentials' tag: {cand.title} ({cand.id})")
            continue
        if _norm_url(cand.url) != target:
            log_message(f"Skipping title match with non-matching url: {cand.title} ({cand.id}) url={cand.url}")
            continue
        log_message(f"Matched existing by-reference item: {cand.title} ({cand.id})")
        return cand
    return None


def verify_agol_item_accessible(agol_item):
    """Confirm the new by-reference AGOL item actually WORKS end-to-end, not just that add() returned an
    Item. Two things can look like success but leave an unusable item: (1) the item is created but the
    stored service password did not persist/validate, so the federated usrsvcs proxy answers with an auth
    {'error': ...} instead of the service definition; (2) sharing failed so the layer isn't reachable by
    the intended audience. This re-fetches the item by id, then requests the (proxy) service URL with the
    AGOL token and -- when the service exposes layers -- runs a returnCountOnly query against the first
    layer to prove the proxy reaches the DATA, not just the service metadata. Returns (ok, detail)."""
    try:
        # Re-fetch by id so we test what AGOL actually persisted (fresh proxy url), not the in-memory object.
        chk = agol_gis.content.get(agol_item.id)
        if chk is None:
            return False, "item not retrievable by id after add"
        service_url = chk.url
        if not service_url:
            return False, "item has no service url"
        # Hit the service root through the (proxy) url with the AGOL token. A working secured by-reference
        # service returns its definition (currentVersion / layers / tables); a credential or proxy failure
        # returns an {'error': ...} payload even with HTTP 200.
        resp = requests.get(service_url, params={'f': 'json', 'token': agol_token}, timeout=30)
        try:
            body = resp.json()
        except ValueError:
            return False, f"non-JSON response (HTTP {resp.status_code}) from {service_url}"
        if isinstance(body, dict) and 'error' in body:
            err = body['error'] if isinstance(body['error'], dict) else {}
            return False, (f"service error code={err.get('code')} "
                           f"message={err.get('message')} details={err.get('details')}").strip()
        # If the service exposes layers, prove the first one is queryable through the proxy. Best-effort:
        # a metadata-only success (e.g. a service with no layers array) still counts as accessible.
        layers = (body.get('layers') if isinstance(body, dict) else None) or []
        if layers:
            lyr_id = layers[0].get('id', 0)
            q = requests.get(f"{service_url}/{lyr_id}/query",
                             params={'where': '1=1', 'returnCountOnly': 'true', 'f': 'json', 'token': agol_token},
                             timeout=30)
            try:
                qbody = q.json()
            except ValueError:
                qbody = {}
            if isinstance(qbody, dict) and 'error' in qbody:
                qerr = qbody['error'] if isinstance(qbody['error'], dict) else {}
                return False, f"layer {lyr_id} query error: {qerr.get('message')}"
            cnt = qbody.get('count') if isinstance(qbody, dict) else None
            return True, f"accessible (layer {lyr_id} count={cnt})"
        return True, "accessible (service metadata returned)"
    except Exception as e:
        return False, f"verification exception: {e}"


init_logging()

if not connect_to_arcgis():
    # Exit NON-ZERO so a caller (run_migration_pipeline.py) sees this stage FAILED and halts, instead of a
    # bare exit() (code 0) that looks like success and lets the pipeline continue past a broken share-back.
    sys.exit(1)

agol_user = agol_gis.properties.user.username
agol_token = agol_gis._con.token
log_message("--->Logged into AGOL as {}".format(agol_user))

# Login to Enterprise Portal

# Using Pro Instance for Example
portal_user = portal_gis.properties.user.username
log_message("--->Logged into Portal as {}".format(portal_user))

# Resolve the Enterprise items to share back. Order: explicit CLI args > portal_item_ids_to_add (module
# override) > the migration ledger's enterprise_item_id values (default). The ledger IS the correct work
# list -- exactly the items this migration produced. The old default searched the persistent 'Coverage
# Share' group, which re-processed every item ever added to it (incl. prior-migration leftovers with no
# ledger row, so their state never advanced). Now matches AddItemToCoverageShareGroup.py (ledger-driven).
cli_ids = [a.strip() for a in sys.argv[1:] if a.strip()]
if cli_ids:
    enterprise_item_ids = cli_ids
elif portal_item_ids_to_add:
    enterprise_item_ids = list(portal_item_ids_to_add)
else:
    enterprise_item_ids = ledger_enterprise_item_ids()

items_to_add = []
for _iid in enterprise_item_ids:
    _it = portal_gis.content.get(_iid)
    if _it is None:
        log_message(f"Enterprise item not found / not accessible: {_iid}", 'error')
        continue
    if any((t or '').lower() == 'test' for t in (_it.tags or [])):
        log_message(f"Skipping test-tagged item: {_it.title} ({_iid})")
        continue
    items_to_add.append(_it)

# Add the Portal Items to AGOL
for item in items_to_add:
    current_item_id = ''   # set to the Enterprise item id below so errors auto-record to its ledger row
    try:
        if item.owner == 'esri_livingatlas' or item.owner == 'esri':
            continue
        csv_error = ''
        verified = ''
        verify_detail = ''
        item_title = item.title
        '''
        # append " - NBS" to the title
        if item.owner == 'rrgadmin':
            item_title = item_title + " - NBS"
        '''
        item_id = item.id
        current_item_id = item_id   # any 'error' logged from here on auto-records against this item's row
        item_type = item.type
        item_url = item.url
        item_summary = item.snippet
        item_description = item.description
        item_credits = item.accessInformation
        item_license = item.licenseInfo          # Terms of Use / use constraints -> carried to the AGOL item
        item_tags = item.tags
        
        log_message(f"Adding item to AGOL: {item_title} ({item_id})")

        # Resolve the SOURCE AGOL item id (ledger row key) for this Enterprise item, used below for
        # the by-reference id record AND for 'match_source' sharing.
        source_item_id = _source_item_id_for(item_id)

        # Strip the Enterprise-only migration-default tags (decision #10) so they don't leak onto the
        # AGOL item, then add the by-reference pair (case-insensitive; no duplicates).
        item_tags = [t for t in item_tags if t.strip().lower() not in MIGRATION_DEFAULT_TAGS_TO_STRIP]
        _tags_lower = {t.strip().lower() for t in item_tags}
        if "by reference" not in _tags_lower:
            item_tags.append("by reference")
        if "stored credentials" not in _tags_lower:
            item_tags.append("stored credentials")
        # Folder.add() (arcgis 2.3+) sends item_properties straight to the REST addItem call without
        # normalizing a list -> the 'tags' list gets JSON-serialized into the form field, so the AGOL
        # item ends up with literal '["Water", "water stress", ...]' instead of real tags. Pass tags as
        # the comma-joined string the REST API expects (matches Import_Content_from_Portal_to_AGOL.py).
        item_tags = ", ".join(item_tags)

        # Check if a matching by-reference item already exists in AGOL. A title match alone is not enough:
        # the candidate must also carry the 'stored credentials' tag AND point at this portal item's url
        # (see find_existing_byref_item). Otherwise we create a new by-reference item.
        agol_item = find_existing_byref_item(item_title, item_url)
        if agol_item is None:
            item_properties = {"title": item_title,
                               "tags": item_tags,
                               "url": item_url,
                               "type": item.type,
                               "snippet": item_summary,
                               "description": item_description,
                               "accessInformation": item_credits,
                               "licenseInfo": item_license,
                               "serviceUsername": portal_user,
                               "servicePassword": portal_password,
                               "token": agol_token}
            owner = agol_user

            agol_item = add_referenced_item_to_agol(agol_gis, item_properties, item_url, owner)
            log_message(f"Item added to AGOL: {item_title}")
            
            # Re-assert the stored service credentials with an explicit update(). For a federated
            # secured service, addItem registers the credential proxy (serviceUsername "takes" -- the
            # item.url becomes a utility.arcgis.com/usrsvcs proxy URL) but the password often does not
            # fully persist/validate at add time, so the by-reference item can't authenticate until the
            # credentials are re-saved. Editing them in the item's Settings UI does exactly this (an Item
            # update); replicate it here so the pipeline does not require a manual step afterward.
            try:
                agol_item.update(item_properties={"serviceUsername": portal_user,
                                                  "servicePassword": portal_password})
                log_message("Re-asserted stored service credentials via update()")
            except Exception as e:
                log_message(f"Failed to re-assert stored service credentials: {e}", 'error')

            agol_item_id = agol_item.id
            agol_item_url = agol_item.url
            
            # Set the new item's sharing (it is created private to the creating user by default).
            set_agol_sharing(agol_item, source_item_id)
        else:
            agol_item_id = agol_item.id
            agol_item_url = agol_item.url
            csv_error = 'Item already exists'
            log_message(f"Item already exists in AGOL: {item_title}")
        log_message(f"AGOL Item ID: {agol_item_id}")
        log_message(f"AGOL Item URL: {agol_item_url}")

        # Verify the by-reference layer is actually accessible (proxy + stored credentials work), not just
        # that the item was created. A failure here is logged as an error so it surfaces in the error log
        # and CSV; the item still exists but needs attention (commonly: re-save the stored credentials).
        ok, verify_detail = verify_agol_item_accessible(agol_item)
        verified = str(ok)
        if ok:
            log_message(f"Verified AGOL item accessible: {agol_item_id} -- {verify_detail}")
        else:
            log_message(f"AGOL item NOT accessible after add: {agol_item_id} -- {verify_detail}", 'error')
            if not csv_error:
                csv_error = f"Not accessible: {verify_detail}"

        # Record the new AGOL by-reference id back to the migration ledger (join on the Enterprise item id
        # == this portal item's id) so Phase-8 reassign/deprecate can find it. Best-effort.
        if ledger_mod is not None and agol_item_id:
            try:
                if source_item_id:
                    ledger_mod.set_state(source_item_id, "shared_to_agol", agol_byref_item_id=agol_item_id)
                    log_message(f"ledger: {source_item_id} -> shared_to_agol (agol by-ref {agol_item_id})")
                    # A not-accessible verify was logged at 'error' above -> auto-recorded to the ledger row,
                    # so a broken by-reference item isn't mistaken for a clean share (Phase-8 still finds it).
                else:
                    log_message(f"ledger: no row with enterprise_item_id == {item_id}; by-ref id not recorded")
            except Exception as e:
                log_message(f"ledger update skipped: {e}")
    except Exception as e:
        log_message(f"Failed to add item to AGOL: {e}", 'error')   # auto-recorded to the ledger row
        csv_error = f"Failed to add item to AGOL: {e}"
        
    with open(output_csv_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([item_id, item_url, agol_item_id, agol_item_url, item_type, item_title, csv_error, verified, verify_detail])

log_message("Script completed successfully.")
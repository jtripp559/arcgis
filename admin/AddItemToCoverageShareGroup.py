# -*- coding: utf-8 -*-
"""
Name: AddItemToCoverageShareGroup.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-08

================================================================================
WHAT THIS SCRIPT DOES  (migration decision #10 -- Phase 8 prep)
================================================================================
Shares the migrated ENTERPRISE feature-service item(s) to the portal group used to
drive the share-back to AGOL (default "Coverage Share"). `AddItemWithStoredCredentials.py`
pulls its work list from that group, so an item must be a member BEFORE that step runs.

The work list is Feature Services only (ALLOWED_ITEM_TYPES): an id that resolves to a Map
Service (or anything else) is skipped with a warning. A referenced publish from Pro creates
both items (.../FeatureServer and .../MapServer); when a work-item Feature Service was published
from a Map Image Layer (it has a sibling .../MapServer Map Service), BOTH are shared to the
group -- the Feature Service as the work item, and its backing Map Service pulled in alongside
it. Set SHARE_BACKING_MAP_IMAGE_LAYER=False to share only the Feature Service.

================================================================================
HOW TO RUN  (ArcGIS Pro conda env)
================================================================================
    python AddItemToCoverageShareGroup.py
    python AddItemToCoverageShareGroup.py <itemid1> <itemid2> ...   # overrides ITEM_IDS

Connects to the ENTERPRISE portal (active Pro session if it IS that portal, else
username/password). Sharing to the group needs item ownership/admin + group membership.
Set DRY_RUN=True to report what WOULD be shared without changing anything.
"""

import sys
import getpass

from arcgis.gis import GIS

# Windows Credential Manager logins (key 'portal' -> nbs_arcgis_admin, 'agol' -> nbs_agol_user), with an
# interactive prompt fallback. Best-effort -- if not importable, connect_portal() prompts as before.
try:
    import credential_store
except Exception:
    credential_store = None

import os
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# Read-only here: the ledger path is resolved by the module (canonical ArcGIS Admin\Migrate\Output,
# env MIGRATION_LEDGER_PATH overrides); we read get_ledger().rows.
if os.path.join(_THIS_DIR, "Migrate") not in sys.path:
    sys.path.insert(0, os.path.join(_THIS_DIR, "Migrate"))
try:
    import migration_status_ledger as ledger_mod
except Exception:
    ledger_mod = None

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
PORTAL_URL = "https://maps.rrgnbs.com/arcgisportal"
PORTAL_USERNAME = ""        # blank -> prompted (not SSO) when the Pro session isn't this portal

GROUP_NAME = "Coverage Share"          # the group AddItemWithStoredCredentials.py reads from

# Only these item types are added to the group. The Map Image Layer (Map Service) is intentionally
# NOT shared back to AGOL (decision #9/#10), so it must not be added here.
ALLOWED_ITEM_TYPES = ["Feature Service"]

# When a work-item Feature Service was published from a Map Image Layer (it has a sibling .../MapServer
# Map Service item), also share that Map Service to the group. The Feature Service is still the work item;
# this just pulls in its backing Map Image Layer alongside it. Set False to share only the Feature Service.
SHARE_BACKING_MAP_IMAGE_LAYER = True

# The Feature Service item id(s) to add. Resolution order: CLI args > ITEM_IDS (if non-empty) >
# the migration ledger's enterprise_item_id values (default). Leave ITEM_IDS empty to drive off the ledger.
ITEM_IDS = []

DRY_RUN = False             # True = report only, do not change group membership


def connect_portal(portal_url):
    """Connect to the portal using the shared credential_store.connect() (CREDENTIALS FIRST, with the
    active Pro session only as a fallback when it IS this portal). Falls back to the old inline logic if
    credential_store is unavailable."""
    if credential_store is not None:
        return credential_store.connect(portal_url, default_username=PORTAL_USERNAME, log=print)
    # Best-effort fallback when the shared module isn't importable: prompt and log in directly.
    user = PORTAL_USERNAME or input(f"** Portal Username for {portal_url} (not SSO): ").strip()
    pwd = getpass.getpass(f"** Portal Password for {user}: ")
    return GIS(portal_url, user, pwd)
'''
def connect_portal(portal_url):
    """Use the active Pro session if it IS this portal; otherwise username/password login."""
    host = portal_url.split("//")[-1].split("/")[0].lower()
    try:
        gis = GIS("pro")
        if gis.url and host in gis.url.lower() and gis.users.me:
            print(f"using active Pro session: {gis.url}")
            return gis
    except Exception as e:
        print(f"   (Pro session not usable here: {e})")
    # Try the Windows Credential Manager (key by host: 'agol' for *.arcgis.com, else 'portal') before prompting.
    key = "agol" if "arcgis.com" in host else "portal"
    if credential_store is not None:
        user, pwd = credential_store.resolve(key, f"Portal {portal_url} (not SSO)",
                                             default_username=PORTAL_USERNAME, log=print)
    else:
        user = PORTAL_USERNAME or input(f"** Portal Username for {portal_url} (not SSO): ").strip()
        pwd = getpass.getpass(f"** Portal Password for {user}: ")
    return GIS(portal_url, user, pwd)
'''


def find_group(gis, group_name):
    """Return the portal Group whose title matches group_name (exact, case-insensitive), else None."""
    matches = gis.groups.search(group_name)
    for g in matches:
        if (g.title or "").strip().lower() == group_name.strip().lower():
            return g
    return matches[0] if matches else None


def ledger_enterprise_item_ids():
    """Enterprise Feature Service item ids recorded in the migration ledger (one per published item)."""
    if ledger_mod is None:
        print("ledger: migration_status_ledger not importable -- no ids resolved")
        return []
    try:
        path = ledger_mod.default_ledger_path()
        # Honor the run-scope allowlist (MIGRATION_ITEM_ALLOWLIST, keyed by SOURCE item id = the row key) so
        # a --max-items batch run only touches its scoped items; no-op when the env var is unset.
        ids = []
        for k, r in ledger_mod.get_ledger().rows.items():
            # Single work-selection gate (ledger_mod.row_eligible_to_advance): skips a row outside the
            # run-scope allowlist (MIGRATION_ITEM_ALLOWLIST -- silent), carrying a recorded error (must be
            # fixed + cleared first), or -- via the default done_state -- already fully deprecated. The SAME
            # helper the deprecate / publish / share-back stages use, so one place decides "is this row
            # workable".
            ok, why = ledger_mod.row_eligible_to_advance(r)
            if not ok:
                if why:
                    print(f"- skip {k}: {why} -- not adding to '{GROUP_NAME}'")
                continue
            eid = (r.get("enterprise_item_id") or "").strip()
            if eid:
                ids.append(eid)
        print(f"ledger: {len(ids)} enterprise item id(s) from {path}")
        return ids
    except Exception as e:
        print(f"ledger read failed ({ledger_mod.default_ledger_path()}): {e}")
        return []


def resolve_item_ids():
    if len(sys.argv) > 1:
        return [a.strip() for a in sys.argv[1:] if a.strip()]
    if ITEM_IDS:
        return list(ITEM_IDS)
    return ledger_enterprise_item_ids()


def item_group_ids(item):
    """Group ids the item is shared with. Prefer the new Item.sharing API (arcgis 2.3+); fall back to the
    deprecated Item.shared_with."""
    try:
        sw = item.sharing.shared_with          # new API
        return [g.id for g in (sw.get("groups") or [])]
    except Exception:
        try:
            return [g.id for g in (item.shared_with.get("groups", []) or [])]
        except Exception:
            return []


def share_to_group(item, group):
    """Share item to group, verifying membership afterward. Prefer Item.sharing.groups.add() (new API);
    fall back to the deprecated Item.share(). Returns (ok, detail). NOTE: the legacy share() returns
    notSharedWith=[''] (a list with an EMPTY string) on a SUCCESSFUL share, so empty strings are filtered
    out -- that empty-string quirk was previously mis-reported as a failure."""
    new_err = None
    try:
        item.sharing.groups.add(group)          # new API; raises on hard failure
        if group.id in item_group_ids(item):
            return True, "added"
        new_err = "add() returned but membership not confirmed"
    except Exception as e:
        new_err = repr(e)[:160]
    # Legacy fallback.
    try:
        res = item.share(groups=[group.id])
        ns = res.get("notSharedWith") if isinstance(res, dict) else None
        ns = [x for x in (ns or []) if x]       # drop empty strings (benign quirk = success)
        if ns:
            return False, f"notSharedWith={ns} (new: {new_err})"
        if group.id in item_group_ids(item):
            return True, "added (legacy)"
        return False, f"legacy returned but membership not confirmed (new: {new_err})"
    except Exception as e2:
        return False, f"new={new_err}; legacy={e2!r}"[:300]


def _norm_url(u):
    """Normalize a service url for comparison: strip whitespace, a trailing slash, and case."""
    return (u or "").strip().rstrip("/").lower()


def _feature_to_map_url(feature_url):
    """Given a .../FeatureServer service url, return the sibling .../MapServer url, else None."""
    if not feature_url:
        return None
    low = feature_url.lower()
    idx = low.rfind("/featureserver")
    if idx == -1:
        return None
    return feature_url[:idx] + "/MapServer" + feature_url[idx + len("/featureserver"):]


def _service_name_from_url(url):
    """The service name segment from a .../services/<...>/<Name>/FeatureServer style url, else None."""
    parts = (url or "").rstrip("/").split("/")
    return parts[-2] if len(parts) >= 2 else None


def find_backing_map_services(gis, feature_item):
    """Return the backing Map Image Layer (Map Service) item(s) for a Feature Service that was published
    from one -- i.e. the Feature Service's .../FeatureServer has a sibling .../MapServer. A Pro referenced
    publish creates both a Map Service item (MapServer) and a Feature Service item (FeatureServer), and we
    want BOTH in the group. Detection: item relationships first (authoritative when the publish registered
    them), then a fallback that matches the derived sibling MapServer url against same-named Map Service
    content. Returns a list (deduped by id), empty when the Feature Service has no backing Map Service."""
    found = {}
    # 1) Relationships -- authoritative when present. Check the plausible types in both directions.
    for rel in ("Service2Service", "Map2Service", "Service2Layer"):
        for direction in ("forward", "reverse"):
            try:
                for r in (feature_item.related_items(rel, direction) or []):
                    if r and r.type == "Map Service":
                        found[r.id] = r
            except Exception:
                pass
    # 2) URL-sibling fallback. The Feature Service's .../FeatureServer has a sibling .../MapServer when it
    # was published from a Map Image Layer. Portal full-text search indexes the item TITLE/tags, NOT the
    # service url, so a query on the url-derived service NAME misses a Map Service whose title differs from
    # its service name (e.g. service 'Asparagus_Cold_Dormancy_Current_2030_Change' vs the item title). So
    # search by BOTH the item title AND the service name, union the candidates, and keep any Map Service
    # whose url IS exactly the derived sibling (this also rejects unrelated same-titled items in other folders).
    map_url = _feature_to_map_url(feature_item.url)
    if map_url:
        target = _norm_url(map_url)
        name = _service_name_from_url(feature_item.url)
        queries = [f'title:"{feature_item.title}"']
        if name:
            queries.append(f'{name} type:"Map Service"')
        candidates = {}
        for q in queries:
            try:
                for r in (gis.content.search(query=q, max_items=50) or []):
                    candidates[r.id] = r
            except Exception:
                pass
        for r in candidates.values():
            if r and r.type == "Map Service" and _norm_url(r.url) == target:
                found[r.id] = r
    return list(found.values())


def share_one(item, group, shared, already, failed):
    """Share a single item to the group (honoring DRY_RUN) and update the tally lists. Used for the work
    Feature Service AND any backing Map Image Layer pulled in alongside it."""
    if group.id in item_group_ids(item):
        print(f"- {item.id} ({item.title}): already in '{GROUP_NAME}'")
        already.append(item.id)
        return
    if DRY_RUN:
        print(f"- {item.id} ({item.title}): WOULD add to '{GROUP_NAME}'  [not applied]")
        shared.append(item.id)
        return
    ok, detail = share_to_group(item, group)
    if ok:
        print(f"- {item.id} ({item.title}): ADDED to '{GROUP_NAME}' ({detail})")
        shared.append(item.id)
    else:
        print(f"- {item.id} ({item.title}): share FAILED -- {detail}")
        failed.append(item.id)
        if ledger_mod is not None:
            ledger_mod.record_error(item.id, f"share to '{GROUP_NAME}' failed: {detail}"[:300], phase="coverage_share")


def main():
    print(f"=== Add item(s) to portal group '{GROUP_NAME}'{'  [DRY RUN]' if DRY_RUN else ''} ===\n")

    gis = connect_portal(PORTAL_URL)
    me = gis.users.me
    print(f"connected as : {me.username if me else '?'} on {gis.url}")

    group = find_group(gis, GROUP_NAME)
    if group is None:
        print(f"!! group '{GROUP_NAME}' not found / not accessible. Stopping.")
        return
    print(f"group        : {group.title}  | id {group.id} | owner {group.owner}\n")

    item_ids = resolve_item_ids()
    shared, already, skipped, failed = [], [], [], []
    for iid in item_ids:
        item = gis.content.get(iid)
        if item is None:
            print(f"- {iid}: NOT FOUND / not accessible -- skipped")
            skipped.append(iid)
            continue
        # The work list is Feature Services only; a Map Service passed directly is skipped here (its
        # sibling Feature Service drives the sharing instead).
        if item.type not in ALLOWED_ITEM_TYPES:
            print(f"- {iid} ({item.title}): type '{item.type}' not in {ALLOWED_ITEM_TYPES} "
                  f"-- skipped (the Feature Service is the work item)")
            skipped.append(iid)
            continue
        # Share the Feature Service (the work item).
        share_one(item, group, shared, already, failed)
        # If this Feature Service was published from a Map Image Layer, share that Map Service too.
        if SHARE_BACKING_MAP_IMAGE_LAYER:
            for map_item in find_backing_map_services(gis, item):
                print(f"   -> backing Map Image Layer: {map_item.title} ({map_item.id})")
                share_one(map_item, group, shared, already, failed)

    print(f"\n=== done ===")
    print(f"   added      : {len(shared)}  {shared if shared else ''}")
    print(f"   already in : {len(already)}  {already if already else ''}")
    print(f"   skipped    : {len(skipped)}  {skipped if skipped else ''}")
    print(f"   failed     : {len(failed)}  {failed if failed else ''}")


if __name__ == "__main__":
    main()

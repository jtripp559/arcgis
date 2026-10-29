# -*- coding: utf-8 -*-
"""
poc_update_portal_items.py  -- POC one-off.

Set the friendly TITLE and the ORIGINAL AGOL DESCRIPTION on the already-published Enterprise items
(BOTH the Feature Layer and its backing Map Image Layer) for the migration POC items. This is the
standalone equivalent of PublishFromDBToFeatureService.validate_and_update_portal_item, but it operates
on items BY ID (from the migration status ledger) so it can patch items that were already published
without re-publishing.

Per ledger row that has an enterprise_item_id:
  - title       = ledger 'title'
  - description = the source AGOL item's description from the cached DataDump
                  (AGOL_<source item_id>_description_*.json) -- the same source the publish/Step 6 use
  - applied to the Enterprise Feature Layer AND its Map Image Layer sibling (FeatureServer<->MapServer)

Run on nbs-app2 (ArcGIS Pro/Server conda env). Portal login via credential_store (key 'portal'):
    python poc_update_portal_items.py
    python poc_update_portal_items.py <enterprise_item_id> [<enterprise_item_id> ...]   # limit to these
"""

import os
import sys
import json

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
sys.path.insert(0, os.path.join(_THIS_DIR, "Migrate"))

import credential_store
import migration_status_ledger as ledger_mod
from arcgis.gis import GIS

# ---- config -----------------------------------------------------------------
PORTAL_URL = "https://maps.rrgnbs.com/arcgisportal"
# Read-only here: the ledger path is resolved by the module (canonical ArcGIS Admin\Migrate\Output,
# env MIGRATION_LEDGER_PATH overrides); we read get_ledger().rows.
METADATA_DUMP_DIR = os.getenv(
    "METADATA_DUMP_DIR",
    r"T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\DataDump")
DRY_RUN = False   # True = report what would change, do not modify items


def get_source_description(src_item_id):
    """Original AGOL description (HTML) from the cached DataDump 'AGOL_<id>_description_*.json' (or '_get').
    '' if not found. Never raises."""
    if not src_item_id or not os.path.isdir(METADATA_DUMP_DIR):
        return ''
    try:
        prefix = f"agol_{src_item_id.lower()}"
        cands = [fn for fn in os.listdir(METADATA_DUMP_DIR)
                 if fn.lower().startswith(prefix) and fn.lower().endswith('.json')
                 and '_data' not in fn.lower()
                 and ('_description' in fn.lower() or '_get' in fn.lower())]
        cands.sort(key=lambda f: ('_description' not in f.lower(), f))
        for fn in cands:
            with open(os.path.join(METADATA_DUMP_DIR, fn), 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if data.get('description'):
                return data['description']
    except Exception as e:
        print(f"   (could not read source description for {src_item_id}: {e})")
    return ''


def map_sibling(gis, it):
    """The Map Image Layer item whose URL is the FeatureServer's MapServer sibling, or None."""
    url = (getattr(it, 'url', '') or '')
    if '/FeatureServer' not in url:
        return None
    map_url = url.replace('/FeatureServer', '/MapServer')
    try:
        for h in gis.content.search(f'url:"{map_url}"', max_items=5):
            if (getattr(h, 'url', '') or '').rstrip('/').lower() == map_url.rstrip('/').lower():
                return h
    except Exception as e:
        print(f"   (sibling search failed: {e})")
    return None


def update_one(it, title, description, label):
    if it is None:
        return
    props = {}
    if title and (it.title or '') != title:
        props['title'] = title
    if description and (it.description or '') != description:
        props['description'] = description
    if not props:
        print(f"   {label} {it.id} ({it.type}): already up to date")
        return
    if DRY_RUN:
        print(f"   {label} {it.id} ({it.type}): WOULD set {list(props.keys())}")
        return
    ok = it.update(item_properties=props)
    print(f"   {label} {it.id} ({it.type}): set {list(props.keys())} -> {'OK' if ok else 'FAILED'}")
    if not ok:
        # it.id is a destination id (enterprise resolves to its row; the map-sibling id won't, and no-ops).
        ledger_mod.record_error(it.id, f"{label} item.update({list(props.keys())}) returned False",
                                phase="portal_update")


def main():
    only_ids = set(sys.argv[1:])
    gis = credential_store.connect(PORTAL_URL, key="portal", default_username="rrgadmin")
    print(f"connected to {PORTAL_URL} as {gis.users.me.username if gis.users.me else '?'}  (DRY_RUN={DRY_RUN})")

    ledger = ledger_mod.get_ledger()
    rows = [r for r in ledger.rows.values() if (r.get('enterprise_item_id') or '').strip()]
    if only_ids:
        rows = [r for r in rows if r.get('enterprise_item_id') in only_ids]
    if not rows:
        print("no ledger rows with an enterprise_item_id to update.")
        return

    for r in rows:
        ent_id = r.get('enterprise_item_id', '')
        src_id = r.get('item_id', '')          # source AGOL item id (ledger key)
        title = r.get('title', '')
        print(f"\n=== {title or ent_id}  (Enterprise {ent_id}; source {src_id}) ===")
        try:
            feat = gis.content.get(ent_id)
            if feat is None:
                print(f"   Enterprise item {ent_id} not found -- skipping")
                ledger_mod.record_error(src_id or ent_id, f"Enterprise item {ent_id} not found",
                                        phase="portal_update")
                continue
            desc = get_source_description(src_id)
            if not desc:
                print(f"   (no cached source description for {src_id}; title only)")
            update_one(feat, title, desc, "Feature Layer")
            update_one(map_sibling(gis, feat), title, desc, "Map Image Layer")
        except Exception as e:
            print(f"   !! failed updating {ent_id}: {e}")
            ledger_mod.record_error(src_id or ent_id, f"portal item update failed: {e!r}"[:300],
                                    phase="portal_update")


if __name__ == "__main__":
    main()

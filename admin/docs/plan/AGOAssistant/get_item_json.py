# -*- coding: utf-8 -*-
"""
Fetch an AGOL item's Description and Data JSON exactly the way ago-assistant does
(see how-ago-assistant-view-edit-json.md in this directory):

  Description : GET {portalUrl}sharing/rest/content/items/{id}?f=json
  Data        : GET {portalUrl}sharing/rest/content/items/{id}/data?f=json

Writes two files next to this script:
  Description_<id>.json   (the item resource / metadata)
  Data_<id>.json          (the item data resource: layers/popup/renderer, web map JSON, ...)

Run inside ArcGIS Pro (Python window) or the ArcGIS Pro conda env while signed in as a user
who can access the item. Uses the active session (GIS("pro")); requests go through the
authenticated connection so secured / stored-credential items work too.

Usage:
  python get_item_json.py                 # uses the default ITEM_ID below
  python get_item_json.py <itemId>        # any item id

Author: Julie Tripp (assisted)
Date: 2026-06-03
"""

import os
import sys
import json

from arcgis.gis import GIS

# Default to the item the ago-assistant samples were taken from.
ITEM_ID = sys.argv[1] if len(sys.argv) > 1 else "45f53ad7838c47a28a5ff17f53312ee4"

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    gis = GIS("pro")
    me = gis.users.me
    print(f"Connected to {gis.url} as {me.username if me else '?'}")

    portal = gis.url if gis.url.endswith('/') else gis.url + '/'
    desc_url = f"{portal}sharing/rest/content/items/{ITEM_ID}"
    data_url = f"{portal}sharing/rest/content/items/{ITEM_ID}/data"

    # 1) Description = the item resource itself.
    description = gis._con.get(desc_url, {'f': 'json'})
    desc_path = os.path.join(OUTPUT_DIR, f"Description_{ITEM_ID}.json")
    with open(desc_path, 'w', encoding='utf-8') as fh:
        json.dump(description, fh, indent=4, ensure_ascii=False)
    title = description.get('title') if isinstance(description, dict) else None
    print(f"Wrote Description ({title}): {desc_path}")

    # 2) Data = the item's /data resource (may be empty for some item types).
    data = gis._con.get(data_url, {'f': 'json'})
    data_path = os.path.join(OUTPUT_DIR, f"Data_{ITEM_ID}.json")
    if data in (None, '', {}):
        print(f"Item {ITEM_ID} has no data resource (empty /data response); writing empty object.")
        data = {} if data in (None, '') else data
    with open(data_path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=4, ensure_ascii=False)
    print(f"Wrote Data: {data_path}")


if __name__ == "__main__":
    main()

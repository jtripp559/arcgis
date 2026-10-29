# -*- coding: utf-8 -*-
"""
clear_categories.py -- clear bogus content categories (e.g. the ['nan'] set by an earlier publish run)
from one or more portal items, including the backing Map Image Layer sibling of a referenced Feature
Service (FeatureServer <-> MapServer URL swap).

    python clear_categories.py                       # uses DEFAULT_ITEMS below
    python clear_categories.py <itemid1> <itemid2>   # clear these item ids
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import credential_store
from arcgis.gis import GIS

PORTAL_URL = "https://maps.rrgnbs.com/arcgisportal"
DEFAULT_ITEMS = [
    "764f6940864a41adbeca491f3179b66d",   # Change in SW Supply by 2030 (Feature Service)
    "0aef1bd4ddb44b229fc155d587187d7b",   # Asparagus ... (Feature Service)
]


def clear_one(gis, iid):
    it = gis.content.get(iid)
    if it is None:
        print(f"  {iid}: NOT FOUND")
        return
    cats = it.categories
    if not cats:
        print(f"  {iid} ({it.title}) [{it.type}]: no categories -- nothing to do")
        return
    ok = it.update(item_properties={"categories": []})
    print(f"  {iid} ({it.title}) [{it.type}]: cleared {cats} -> {'OK' if ok else 'FAILED'}")


def map_sibling(gis, it):
    """Return the Map Image Layer item whose URL is the FeatureServer's MapServer sibling, or None."""
    url = (getattr(it, "url", "") or "")
    if "/FeatureServer" not in url:
        return None
    map_url = url.replace("/FeatureServer", "/MapServer")
    try:
        hits = gis.content.search(f'url:"{map_url}"', max_items=5)
        for h in hits:
            if (getattr(h, "url", "") or "").rstrip("/").lower() == map_url.rstrip("/").lower():
                return h
    except Exception as e:
        print(f"    (sibling search failed: {e})")
    return None


def main():
    ids = sys.argv[1:] or DEFAULT_ITEMS
    gis = credential_store.connect(PORTAL_URL, key="portal", default_username="rrgadmin")
    print(f"connected to {PORTAL_URL} as {gis.users.me.username if gis.users.me else '?'}")
    for iid in ids:
        clear_one(gis, iid)
        it = gis.content.get(iid)
        if it is not None:
            sib = map_sibling(gis, it)
            if sib is not None:
                clear_one(gis, sib.id)


if __name__ == "__main__":
    main()

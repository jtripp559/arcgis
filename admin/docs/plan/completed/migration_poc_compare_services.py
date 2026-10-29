# -*- coding: utf-8 -*-
"""
Name: migration_poc_compare_services.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-04

================================================================================
WHAT THIS SCRIPT DOES
================================================================================
Compare the symbology + pop-up state of two (or more) published Enterprise
feature layers, by pulling BOTH the service layer definition and the portal item
/data for each, and reporting:
  * service layer  (.../FeatureServer/<id>?f=json) -> drawingInfo / renderer, field list
  * item /data     (items/<id>/data?f=json)        -> layers[].layerDefinition.drawingInfo, popupInfo

Use it to (a) see what a symbolized service looks like vs a blank one, and
(b) re-run after programmatic editing to confirm the blank one now matches the
symbolized control.

Raw JSON for each target is saved to Migrate\Output\compare_<label>_{layer,itemdata}.json.

================================================================================
HOW TO RUN
================================================================================
    python migration_poc_compare_services.py

Connects to the Enterprise portal (Pro session if it is that portal, else
username/password). Edit TARGETS below to compare different items/services.
"""

import os
import json
import getpass

from arcgis.gis import GIS

# credential_store.py lives in the ArcGIS Admin root; this script is under docs\plan\completed -> add the root.
import sys
_ADMIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ADMIN_DIR not in sys.path:
    sys.path.insert(0, _ADMIN_DIR)
import credential_store   # Windows Credential Manager + prompt fallback

PORTAL_URL = "https://maps.rrgnbs.com/arcgisportal"
PORTAL_USERNAME = ""

OUTPUT_DIR = os.path.join(_ADMIN_DIR, "Migrate", "Output")

# Each target: label, portal item id, service layer URL.
TARGETS = [
    {
        "label": "control_with_symbol",
        "item_id": "6698de1a555d4f5d959a2642f20648a6",
        "layer_url": "https://maps.rrgnbs.com/arcgisserver/rest/services/Test/TEST_w_symbol_4d6aff488b9e48bf8a1f204c05d6f53d/FeatureServer/0",
    },
    {
        "label": "blank_target",
        "item_id": "6b887c6b9395471fb7c88dc115037ec6",
        "layer_url": "https://maps.rrgnbs.com/arcgisserver/rest/services/Test/WS_Change_in_SW_Supply_by_2030/FeatureServer/0",
    },
]


def connect_portal(portal_url):
    """Connect via the shared credential_store.connect(): stored credential FIRST (key by host: 'agol'
    for *.arcgis.com, else 'portal'), then the active Pro session, then a prompt."""
    return credential_store.connect(portal_url, default_username=PORTAL_USERNAME)


def popup_counts(popup):
    if not popup:
        return None
    top = len(popup.get("fieldInfos") or [])
    els = sum(len(el.get("fieldInfos") or []) for el in (popup.get("popupElements") or []))
    return {"title": popup.get("title"), "top_level_fieldInfos": top, "popupElements_fieldInfos": els}


def summarize(gis, tgt):
    portal = gis.url if gis.url.endswith("/") else gis.url + "/"
    # service layer def
    layer = gis._con.get(tgt["layer_url"], {"f": "json"}) or {}
    # item /data
    data = gis._con.get(f"{portal}sharing/rest/content/items/{tgt['item_id']}/data", {"f": "json"}) or {}

    # save raw for inspection
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, f"compare_{tgt['label']}_layer.json"), "w", encoding="utf-8") as fh:
        json.dump(layer, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(OUTPUT_DIR, f"compare_{tgt['label']}_itemdata.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    # service renderer
    svc_di = layer.get("drawingInfo")
    svc_rnd = (svc_di or {}).get("renderer", {}) or {}
    fields = [f["name"] for f in (layer.get("fields") or [])]

    # item /data layer 0
    item_layer = None
    for lyr in (data.get("layers") or []):
        if int(lyr.get("id", -1)) == 0:
            item_layer = lyr
            break
    item_di = ((item_layer or {}).get("layerDefinition") or {}).get("drawingInfo")
    item_rnd = (item_di or {}).get("renderer", {}) or {}
    item_popup = (item_layer or {}).get("popupInfo")

    return {
        "label": tgt["label"],
        "item_id": tgt["item_id"],
        "service_layer_name": layer.get("name"),
        "field_count": len(fields),
        "service_drawingInfo": bool(svc_di),
        "service_renderer": f"{svc_rnd.get('type')} / {svc_rnd.get('field') or svc_rnd.get('field1') or '-'}" if svc_di else "(none)",
        "item_data_has_layers": bool(data.get("layers")),
        "item_drawingInfo": bool(item_di),
        "item_renderer": f"{item_rnd.get('type')} / {item_rnd.get('field') or item_rnd.get('field1') or '-'}" if item_di else "(none)",
        "item_popup": popup_counts(item_popup),
    }


def main():
    gis = connect_portal(PORTAL_URL)
    print(f"connected as {gis.users.me.username if gis.users.me else '?'} on {gis.url}\n")

    rows = [summarize(gis, t) for t in TARGETS]

    for r in rows:
        print(f"=== {r['label']}  (item {r['item_id']}) ===")
        print(f"  service layer        : {r['service_layer_name']}  ({r['field_count']} fields)")
        print(f"  SERVICE drawingInfo  : {r['service_drawingInfo']}   renderer: {r['service_renderer']}")
        print(f"  ITEM /data layers    : {r['item_data_has_layers']}")
        print(f"  ITEM drawingInfo     : {r['item_drawingInfo']}   renderer: {r['item_renderer']}")
        print(f"  ITEM popupInfo       : {r['item_popup']}")
        print()

    print("Raw JSON saved to Migrate\\Output\\compare_<label>_layer.json and _itemdata.json for a deeper diff.")


if __name__ == "__main__":
    main()

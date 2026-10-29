# -*- coding: utf-8 -*-
"""
Copy symbology and pop-ups from a source (e.g. AGOL) feature-layer item to a target item
(e.g. a referenced feature service just published to ArcGIS Enterprise).

There are TWO distinct places this information lives, and they need different REST operations:

  1. Portal item /data  (Update Item)         -> carries BOTH symbology AND pop-ups
     POST {portal}sharing/rest/content/users/{owner}/{folder}/items/{id}/update  (text=<data json>)
     This is what ago-assistant's "Edit JSON -> Data" does. pop-ups (popupInfo) live ONLY here.

  2. Service layer definition (updateDefinition) -> carries symbology only (NO pop-ups)
     POST {service-admin}/FeatureServer/{layerId}/updateDefinition  (updateDefinition=<drawingInfo>)
     https://developers.arcgis.com/rest/services-reference/enterprise/update-definition-feature-service/
     Bakes drawingInfo/renderer into the SERVICE itself, so every client gets it. Requires
     publisher/admin rights on the federated server. pop-ups are not a service concept, so they
     cannot be set here.

So:
  --apply item     -> set the target item's /data from the source (symbology + pop-ups)   [default]
  --apply service  -> push each layer's drawingInfo to the service via updateDefinition    (symbology)
  --apply both     -> do both (service renderer + item data with pop-ups)

For the AGOL -> Enterprise migration, the usual choice is `both`: updateDefinition gives the
published service its renderer, and the item /data gives the portal item its pop-ups + style.

Layer-id remap: the source (AGOL) layer ids often differ from the target (Enterprise) service
layer ids. If both services have a single layer, the mapping is inferred automatically; otherwise
pass --layer-map "4=0,5=1" (source id = target id).

Safety: current item /data and/or current layer drawingInfo are backed up to timestamped files
before anything is written, the source JSON is validated, and you are asked to confirm unless
--yes is given.

NOTE on field names (critical for symbology): a renderer references field names
(renderer.field, unique-value / class-breaks fields) and popupInfo references fieldInfos. Those
fields must exist on the TARGET with the same names, or the renderer/pop-up will not resolve.
This script does not remap field names; see ApplySymbology.py in the migration plan for that.

Run inside ArcGIS Pro (Python window) or the ArcGIS Pro conda env, signed in to the portal that
owns the TARGET item (AGOL for an AGOL target, Enterprise for an Enterprise target).

Usage:
  python update_item_data.py <targetItemId>
  python update_item_data.py <targetItemId> --source-data Data_<sourceId>.json --apply both
  python update_item_data.py <targetItemId> --source-data src.json --apply service --layer-map 4=0
  python update_item_data.py <targetItemId> --source-data src.json --apply item --yes

Author: Julie Tripp (assisted)
Date: 2026-06-03
"""

import os
import sys
import copy
import json
import argparse
from datetime import datetime

from arcgis.gis import GIS

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_layer_map(text):
    # "4=0,5=1" -> {4: 0, 5: 1}
    mapping = {}
    if not text:
        return mapping
    for pair in text.split(','):
        pair = pair.strip()
        if not pair:
            continue
        src, dst = pair.split('=')
        mapping[int(src.strip())] = int(dst.strip())
    return mapping


def source_layers(data_obj):
    # The /data document is {"layers": [...]} (and may also have "tables"). Return the list.
    if isinstance(data_obj, dict):
        return data_obj.get('layers') or []
    return []


def main():
    ap = argparse.ArgumentParser(description="Copy symbology/pop-ups from a source item's data JSON "
                                             "to a target item (and optionally its service).")
    ap.add_argument("target_item_id", help="Target portal item id (e.g. the Enterprise referenced service item).")
    ap.add_argument("--source-data", help="Path to the source data JSON (default: Data_<targetItemId>.json).")
    ap.add_argument("--apply", choices=["item", "service", "both"], default="item",
                    help="Where to apply: item /data (symbology+pop-ups), service updateDefinition "
                         "(symbology only), or both. Default: item.")
    ap.add_argument("--layer-map", help='Source->target layer id remap, e.g. "4=0,5=1". '
                                        "If omitted and both sides are single-layer, inferred automatically.")
    ap.add_argument("--yes", action="store_true", help="Apply without the confirmation prompt.")
    args = ap.parse_args()

    target_id = args.target_item_id
    src_path = args.source_data or os.path.join(OUTPUT_DIR, f"Data_{target_id}.json")
    if not os.path.exists(src_path):
        print(f"ERROR: source data file not found: {src_path}")
        return
    with open(src_path, encoding='utf-8') as fh:
        src_data = json.load(fh)
    src_layers = source_layers(src_data)
    print(f"Source data: {src_path} ({len(src_layers)} layer(s))")

    gis = GIS("pro")
    me = gis.users.me
    print(f"Connected to {gis.url} as {me.username if me else '?'}")

    item = gis.content.get(target_id)
    if item is None:
        print(f"ERROR: target item {target_id} not found / not accessible.")
        return
    print(f"Target item: {item.title}  | type: {item.type}  | owner: {item.owner}")

    target_layers = list(getattr(item, 'layers', []) or [])
    target_ids = [int(l.properties.id) for l in target_layers]
    print(f"Target service layer ids: {target_ids}")

    # Resolve the source-id -> target-id layer mapping.
    layer_map = parse_layer_map(args.layer_map)
    if not layer_map:
        if len(src_layers) == 1 and len(target_layers) == 1:
            layer_map = {int(src_layers[0].get('id')): target_ids[0]}
            print(f"Inferred single-layer map: {layer_map}")
        elif src_layers:
            print("ERROR: could not infer a layer map (not single-layer on both sides). "
                  'Pass --layer-map "srcId=dstId,...".')
            return

    stamp = datetime.now().strftime('%Y%m%d%H%M%S')

    # Confirmation.
    if not args.yes:
        print(f"\nAbout to apply '{args.apply}' from {os.path.basename(src_path)} to item {target_id} "
              f"({item.title}) on {gis.url}.")
        if input("Type YES to proceed: ").strip() != "YES":
            print("Aborted; no changes made.")
            return

    # --- Service-level symbology via updateDefinition (drawingInfo only) ---
    if args.apply in ("service", "both"):
        by_target_id = {int(l.properties.id): l for l in target_layers}
        backup = {}
        applied = 0
        for sl in src_layers:
            sid = int(sl.get('id'))
            if sid not in layer_map:
                print(f"  [service] source layer {sid} has no target mapping; skipped.")
                continue
            tid = layer_map[sid]
            tlayer = by_target_id.get(tid)
            if tlayer is None:
                print(f"  [service] target layer id {tid} not found; skipped.")
                continue
            drawing_info = (sl.get('layerDefinition') or {}).get('drawingInfo')
            if not drawing_info:
                print(f"  [service] source layer {sid} has no drawingInfo; skipped.")
                continue
            # Back up the current drawingInfo, then push the source renderer.
            try:
                backup[str(tid)] = dict(tlayer.properties).get('drawingInfo')
            except Exception:
                backup[str(tid)] = None
            result = tlayer.manager.update_definition({"drawingInfo": drawing_info})
            ok = (isinstance(result, dict) and result.get('success')) or result is True
            print(f"  [service] layer {sid}->{tid} updateDefinition: {'OK' if ok else result}")
            applied += 1 if ok else 0
        if backup:
            bpath = os.path.join(OUTPUT_DIR, f"ServiceDrawingInfo_backup_{target_id}_{stamp}.json")
            with open(bpath, 'w', encoding='utf-8') as fh:
                json.dump(backup, fh, indent=4, ensure_ascii=False)
            print(f"  [service] backed up prior drawingInfo to {bpath}")
        print(f"  [service] updateDefinition applied to {applied} layer(s).")

    # --- Item /data via Update Item (symbology + pop-ups) ---
    if args.apply in ("item", "both"):
        # Back up the current item data first.
        portal = gis.url if gis.url.endswith('/') else gis.url + '/'
        current = gis._con.get(f"{portal}sharing/rest/content/items/{target_id}/data", {'f': 'json'})
        bpath = os.path.join(OUTPUT_DIR, f"Data_{target_id}_backup_{stamp}.json")
        with open(bpath, 'w', encoding='utf-8') as fh:
            json.dump(current if current is not None else {}, fh, indent=4, ensure_ascii=False)
        print(f"  [item] backed up current item /data to {bpath}")

        # Build the new item data: copy the source, remap each layer id to the target id.
        new_data = copy.deepcopy(src_data)
        for lyr in new_data.get('layers', []):
            sid = int(lyr.get('id'))
            if sid in layer_map:
                lyr['id'] = layer_map[sid]
        # Push via the Update Item operation (item.update handles owner/folder/token).
        ok = item.update(data=json.dumps(new_data))
        print(f"  [item] item.update(data=...): {'OK' if ok else 'FAILED'}")
        if not ok:
            print(f"  [item] previous data preserved in {bpath}")

    print("\nDone.")


if __name__ == "__main__":
    main()

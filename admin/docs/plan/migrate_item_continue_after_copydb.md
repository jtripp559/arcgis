# Continue a migration after the copy to the database (multi-layer / table items)

Date: 2026-10-20
Author: Julie Tripp (assisted)

Related: `migration-plan.md`, `migration_multilayer_plan.md` (the planned automation of all this).

---

## 1. When to use this

Use this checklist for an item whose **source has more than one layer, or any table** (this includes every
item with **relationships** -- a relationship always involves a second layer or a table). For these items the
automatic pipeline stops being reliable after the copy step (`copied_to_gdb`):

| Pipeline step | Problem for multi-layer / table items |
|---|---|
| step3 / step3c (copy) | copies one feature class per run, named `<base>`, `<base>_1`, ... -- the ledger records only the LAST one; tables can be missed |
| `PublishFromDBToFeatureService.py` | publishes ONE feature class per service |
| `migration_poc_step6_apply_symbology.py` (`symbology_ent` / `symbology_agol`) | fixed 2026-10-21: pairs every source layer with the target layer of the same name (then id) and applies each layer's own renderer + pop-up -- works once the service keeps the source layer names / ids (step 5.6) |

**Not needed** for single-layer items, with or without attachments: the normal pipeline handles them (the
export carries the `__ATTACH` table and the by-reference service serves the attachments).

How to tell: the AGOL items export (`ArcGIS_Items_AGOL_*_relevant_items.csv`, from
`GetAllArcGISServiceMetadata.py`) or `Input\ValidateDeleted.csv` has `layer count`, `table count` and
`relationship count` columns -- use this checklist when `layer count > 1`, `table count > 0` or
`relationship count > 0`.

Placeholders below: `<AGOL_ID>` = the source AGOL item id (ledger `item_id`), `<DB>` / `<SCHEMA>` = the
destination database and schema, `<BASE>` = the item's base name in SDE (its `dest_feature_class` without a
trailing `_<n>`).

Run the scripts on **nbs-app2** from `C:\Admin\Tools\ArcGIS Admin\Migrate` (the deployed copy -- copy changed
scripts there first). Keep the item OUT of the automatic publish: while it is at `copied_to_gdb` with a value in
the ledger's `error` column, `BuildPublishCSV.py` skips it -- do not clear that error until step 10.

---

## 2. Find out what is in SDE

1. Add the item to `Migrate\Input\repair_items.csv` (columns `item_id`, `title`, `dest_database`,
   `dest_schema`, `dest_feature_class`, ... -- copy them from the item's ledger row; leave `action` blank).
2. Run (read-only):
   ```
   python ValidateWhichLayerIsInSDE.py <AGOL_ID>
   ```
   Log: `Migrate\Output\ValidateWhichLayerIsInSDE_<stamp>.log`. It finds every SDE dataset that can hold the
   item's layers/tables -- named `<BASE>` / `<BASE>_<n>`, named like a source layer/table, or (if published)
   behind the service -- and pairs each with its source layer/table by comparing rows.
3. Read the result:

   | Log shows | Meaning | Do |
   |---|---|---|
   | `-> layer N <name>  n/n` | that SDE dataset holds source layer/table N, all rows match | note the pairing (step 4) |
   | `SOURCE ... NOT in SDE -- needs loading` | a layer/table was never copied | step 3 (`add-layers` / `add-tables`) |
   | `NO source layer/table matches` | an SDE dataset whose rows differ (out of date) or that belongs to another item | check it before using or deleting it |
   | `held by 2 SDE datasets` | a duplicate copy (a retried copy step) | publish only one; consider deleting the other |
   | `extent DIFFERS` on every layer by the same amount | possibly a datum shift (see 3.2) | check visually before publishing |

## 3. Fix any gaps

1. **Missing layers / tables / rows** -- `repair_item_from_export.py` (actions in `Input\repair_items.csv`;
   dry run first, then `--apply`):
   - `add-layers` / `add-tables`: loads the source's layers / tables that are not in SDE (it recognizes copies
     already there, by name or by their rows, and never loads a duplicate)
   - `append-missing`: appends rows a copy lacks (refuses if the copy has rows the source does not)
2. **Datum shift check** -- only if the source is NOT in WGS84 / Web Mercator (e.g. NAD27, wkid 3309): in Pro,
   add one source layer (`Add Data > Data From Path`: `<source FeatureServer url>/<id>`) and its SDE copy to
   one map and zoom in on an edge. Lined up = fine. ~90 m apart = the copy was projected without a datum
   transformation; reload it before publishing.

## 4. Write down the layer-id mapping

From the step 2 log, list every source layer/table with its **id**, **name** and the **SDE dataset** that holds
it. The published service must use the SAME ids, so the archived pop-ups (keyed by layer id) fit unchanged.

Example (aem_dissolve_map: 22 layers, ids 1-22, no tables):

| source id | source name | SDE dataset |
|---|---|---|
| 1 | AEM_475_500_Dissolve | `RRGCMGis.general.aem_dissolve_map` |
| 2 | AEM_425_450_Dissolve | `RRGCMGis.general.aem_dissolve_map_1` |
| ... | ... | ... |
| 22 | AEM_0_5_Dissolve | `RRGCMGis.general.aem_dissolve_map_21` |

(here `aem_dissolve_map` = id 1 and `aem_dissolve_map_<n>` = id n+1 -- the copies were made in source order;
always confirm with the log rather than assume.)

## 5. Build the map in ArcGIS Pro

1. **Project > Portals**: make `https://maps.rrgnbs.com/arcgisportal` the **active** portal (sign in as
   `rrgadmin` or the item owner) -- publishing by reference needs the federated portal active.
2. **Insert > New Map**, name it `<BASE>`. **Remove the basemap** (a basemap fails sharing: Analyzer 24078).
3. **Map Properties > Coordinate Systems**: **WGS 1984** (4326).
4. **Catalog > Databases**: add `T:\ArcGISDataset\Enterprise\Connections\<DB>_<SCHEMA>.sde` (the database
   registered with the server).
5. Add every SDE dataset from the mapping: feature classes as layers, tables as standalone tables.
6. **Ids + names** -- *View > Python*, fill in `MAPPING` from step 4, run:
   ```python
   import arcpy
   # SDE dataset name (lower case, no db.schema prefix) -> (source id, source layer/table name)
   MAPPING = {
       "aem_dissolve_map":   (1, "AEM_475_500_Dissolve"),
       "aem_dissolve_map_1": (2, "AEM_425_450_Dissolve"),
       # ... one line per layer AND table
   }
   m = arcpy.mp.ArcGISProject("CURRENT").activeMap
   cim = m.getDefinition("V3")
   cim.useServiceLayerIDs = True        # = Map Properties > General > "Allow assignment of unique numeric IDs"
   m.setDefinition(cim)
   seen = {}
   for obj in list(m.listLayers()) + list(m.listTables()):
       if not obj.supports("DATASOURCE"):
           continue
       ds = obj.dataSource.split("\\")[-1].split(".")[-1].lower()
       if ds not in MAPPING:
           print("NOT IN MAPPING (check it):", obj.name, ds)
           continue
       sid, name = MAPPING[ds]
       d = obj.getDefinition("V3")
       if hasattr(d, "serviceLayerID"):  # a layer
           d.serviceLayerID = sid
       else:                             # a standalone table
           d.serviceTableID = sid
       obj.setDefinition(d)
       obj.name = name
       seen[sid] = seen.get(sid, 0) + 1
       print(f"{ds:<28} -> id {sid:>3}  {name}")
   dupes = [i for i, n in seen.items() if n > 1]
   missing = sorted(set(v[0] for v in MAPPING.values()) - set(seen))
   print("duplicate ids:", dupes or "none", "| ids not set:", missing or "none")
   ```
   Check the printout: every id once, nothing "NOT IN MAPPING", no duplicates / missing.
   (Same result by hand: Map Properties > General > "Allow assignment of unique numeric IDs for sharing web
   layers", then each layer's / table's Properties > General > Layer ID.)
7. **Order** in Contents: lowest id at the top, as in the source service.
8. **Symbology from the source** -- if the AGOL source still exists: add each source layer (`Data From Path`:
   `<source url>/<id>`) and run **Apply Symbology From Layer** (Data Management > Layers and Table Views;
   use **Batch** for many layers): Input Layer = the SDE layer, Symbology Layer = the matching source layer.
   If the tool won't take a service layer, save it as a `.lyrx` first. If the source is gone, use the archived
   `<AGOL_ID>_layer<n>_renderer.json` as the reference and set the symbology by hand. Or run
   `Migrate\CopySymbologyInArcGisPro.py` in a Pro notebook (copies renderer, labels, transparency, scale
   range, pop-ups, field aliases from same-named source layers in another map). This is the SERVICE's
   symbology; the items get theirs from `symbology_ent` / `symbology_agol` (step 11).
9. **Relationships** (only if the source had some): note them now -- they are created after publishing (step 9).
10. Save the project.

## 6. Publish by reference (Share > Web Layer > Publish Web Layer)

1. **General**
   - Name: `<BASE>` (the service name; must not exist on the server yet)
   - Summary, tags: from the source item; add the tags `Migrated from AGOL` and `Migrated` (the pipeline's
     defaults -- `share_back` removes exactly these from the AGOL copy)
   - Data and Layer Type: **Reference registered data**; **Map Image** with **Feature** checked
   - Location: the source item's folder (portal folder and server folder); `reassign_portal` fixes owner/folder
   - Sharing: owner only (`coverage_share` adds the group)
2. **Configuration > Feature**: **Query** only (read-only).
3. **Content**: every layer and table is listed.
4. **Analyze**: no errors. Typical: duplicate / missing ids (re-run 5.6), a basemap, "data source not
   registered" (wrong `.sde`).
5. **Publish** -> a **Map Image** item + a **Feature Service** item.

## 7. Check the service

Open `https://maps.rrgnbs.com/arcgisserver/rest/services/<folder/><BASE>/FeatureServer`: the layers and
tables carry the SOURCE ids and names from step 4.

## 8. Record the publish

On nbs-app2, in `Migrate\` (use the **Feature Service** item's id):
```
python -c "import migration_status_ledger as l; l.set_state('<AGOL_ID>', 'published_to_portal', enterprise_item_id='<feature service id>', enterprise_service_url='<.../FeatureServer>')"
```
Also put the id + url in the item's row of `Input\repair_items.csv` (`enterprise_item_id`,
`enterprise_service_url`).

## 9. Relationships (only if the source had them)

1. `repair_item_from_export.py add-tables <AGOL_ID> --apply` writes the item's relationships into
   `Input\ManualRelationshipsNeeded.csv` (even when every table is already in SDE).
2. Stop the service (it holds a schema lock), then:
   ```
   python add_relationship.py --item <AGOL_ID>            # dry run: check the plan CSV
   python add_relationship.py --item <AGOL_ID> --apply
   ```
   It needs ArcGIS Server's python on nbs-app2 (licence `ArcServer`) or Pro Standard; with Pro Basic it writes
   a manual script to run there instead.
3. **Overwrite** the service from the same map, now including the relationship classes, so it exposes them.

## 10. Validate (this also clears the old error)

```
python ValidateMigratedItems.py --item <AGOL_ID> --check-db
```
With the service published it checks EVERY layer/table through the service manifest (rows, fields,
attachments, relationships). A pass clears the item's old `validate` error, which unblocks the remaining
stages. Fix any FAIL first.

## 11. Remaining pipeline stages (up to, NOT including, deprecate)

```
python run_migration_pipeline.py --run --item <AGOL_ID> --to reassign_agol --dry-run   # check the list
python run_migration_pipeline.py --run --item <AGOL_ID> --to reassign_agol
```
From `published_to_portal` this runs `symbology_ent`, `thumb_copy_portal`, `source_update`, `coverage_share`,
`reassign_portal`, `share_back`, `symbology_agol`, `thumb_copy_agol`, `reassign_agol` (`qa` / `validate` are
manual and skipped). `--to reassign_agol` matters: without it the run continues into `deprecate`.

`symbology_ent` / `symbology_agol` (step 6) give EVERY layer its own renderer + visibility range + pop-up
from the Step-1 captures (`Migrate\Output\<AGOL_ID>_layer<n>_renderer.json` / `_service.json`) and the
DataDump `/data`, pairing source and target layers by name, then id. The log shows one
`other layer : <src id> '<name>' -> <target id> '<name>'` line per layer -- check none is missing. If the
primary source layer has no matching target layer the stage stops without changing anything (fix the
names / ids, or pass `--target-layer <id>` when running the step-6 script by hand).

## 12. Deprecate the source (irreversible)

Only after checking the AGOL by-reference item (layers, attachments, relationships, symbology, pop-ups):
```
python run_migration_pipeline.py --run --item <AGOL_ID> --only deprecate
```
`symbology_agol` set `agol_updated`, which the deprecate gate requires.

---

## Notes

- Once this is automated (multi-layer copy, publish, per-layer symbology -- `migration_multilayer_plan.md`
  Part 2), this checklist is no longer needed.
- The stage names above are from `run_migration_pipeline.build_stages`; an unknown name is reported by the
  script.
- Each later run of `ValidateWhichLayerIsInSDE.py` / `ValidateMigratedItems.py` writes its own log in
  `Migrate\Output\`.

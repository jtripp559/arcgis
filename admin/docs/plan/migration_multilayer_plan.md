# Multi-Layer / Table / Relationship Support Plan

Date: 2026-10-19
Author: Julie Tripp (assisted)

Related: `migration-plan.md` (pipeline + stage map), `migration_error_remediation_plan.md`.

---

## 1. Problem

The migration pipeline assumes **one feature class per item**. A source service with several
layers, any standalone tables, or relationships comes through **incomplete**, and the gap is only
caught afterwards by `ValidateMigratedItems.py` (the one stage that already handles multiple layers).

| Stage | Script | Single-layer assumption today |
|-------|--------|-------------------------------|
| step3 (stage) | `docs/plan/completed/migration_poc_step3_stage_local.py` | `_find_export_fc` keeps ONE feature class from the export |
| step3c (load) | `docs/plan/completed/migration_poc_step3c_load_sde.py` | loads that one staged feature class |
| Ledger | `Migrate/migration_status_ledger.py` | one `dest_feature_class` column; publish joins on it |
| Publish CSV | `Migrate/BuildPublishCSV.py` | one `feature_name` row per service |
| Publish | `PublishFromDBToFeatureService.py` | `MakeFeatureLayer` of ONE dataset into the temp map |
| Symbology | `docs/plan/completed/migration_poc_step6_apply_symbology.py` | `target_layer_id=0`; one renderer + pop-up per item |
| Relationships | `CreateRelationshipsInGDB.py` (pipeline stage) | NOT BUILT; fixed by hand after publish with `Migrate/add_relationship.py` (then republish) |

Why relationships drop: exporting a SINGLE feature class (ExportFeatures / Project) carries its
attachment class (`__ATTACHREL`) but NOT relationship classes to other datasets, because the other
end is never copied.

### Items already hit by this (fixed or being fixed by hand)

| item_id | title | Symptom | Manual fix |
|---------|-------|---------|------------|
| 2836b79ed2b644f2800232c60ab7176a | CA_WaterRights | relationship missing (layer -> table) | `add_relationship.py`, then republish |
| 27e5aa16a4544db0a69c3a2d941ec93b | RRG_HoldingsAssets | relationships missing | `add_relationship.py` (done) |
| 39c68d5eb6394baaa57ac9c85f5526e2 | HoldingContracts_republish | 2 tables never migrated | `repair_item_from_export.py add-tables`, republish, `add_relationship.py`, republish |
| fc3b10f86c1b4bd38caeb189c3641e02 | aem_dissolve_map | only 1 of N layers migrated (validator paired it to the wrong source layer) | `repair_item_from_export.py add-layers --skip-layer ...`, publish by hand |

Stop-gap tooling (built 2026-10-19, `Migrate/`):
- `repair_item_from_export.py` -- `reload` / `add-tables` / `add-layers` from a fresh full export.
- `add_relationship.py` -- recreate relationship classes from `Input/ManualRelationshipsNeeded.csv`.

---

## 2. Part 1 -- Guard (do now, small)

Stop multi-layer / table items from being published half-migrated.

- [ ] `Migrate/BuildPublishCSV.py`: skip any item whose SOURCE has more than one layer or any
      table, and record a ledger error (phase `publish_csv`):
      `multi-layer/table item: not supported by the pipeline yet (<n> layers, <m> tables)`.
      Layer/table counts come from the AGOL items export it already reads
      (`ArcGIS_Items_AGOL_*_relevant_items.json`, from `GetAllArcGISServiceMetadata.py`), or the live
      service if the item is missing there.
- [ ] (Optional) the same check in step1 (`migration_poc_step1_inspect.py`), so the item stops before
      any copy work.
- [ ] Note the rule in `migration-plan.md` (stage table + run instructions).

Result: such items stop at `copied_to_gdb` (or earlier) with a clear reason, instead of publishing
with missing layers / tables / relationships and failing validation later. They can be finished by
hand with the stop-gap tooling until Part 2 lands.

---

## 3. Sizing (do before Part 2)

- [ ] Count the items in scope (~6500 eventually) with `layer_count > 1`, `table_count > 0`, or
      `relationship_count > 0`, from the latest AGOL items export.
- Decision: a handful -> the guard + stop-gap tooling may be enough. Hundreds -> build Part 2.

---

## 4. Part 2 -- Full multi-layer path (larger)

In pipeline order. Each step is testable on its own against a multi-layer test item (suggest
`aem_dissolve_map` once repaired, or a copy of `HoldingContracts_republish`) into the test SDE
(`NBS_testSQL_sde.sde`) before touching RRGOrg / RRGCMGis.

### 4.1 Copy: stage and load EVERY dataset (step3 / step3c)
- [ ] step3: keep the whole export (every feature class + table + companion `__ATTACH` tables);
      project each feature class to 4326 with `preserveGlobalIds=True`. Replace `_find_export_fc`
      with a dataset list (source layer id -> staged dataset).
- [ ] step3c: load every staged dataset (ExportFeatures / ExportTable, `preserveGlobalIds=True`),
      naming each per the dest-FC naming rule (item `name` -> service URL segment -> `_1`, `_2`, ...),
      and verify per-dataset row counts against the live source.
- [ ] Reuse the `add-layers` / `add-tables` logic in `repair_item_from_export.py` (project-or-export,
      exists check, count verification).

### 4.2 Ledger: record every dataset
- [ ] New column `dest_datasets`: JSON list of `{source_id, kind (layer|table), source_name, dataset}`.
- [ ] Keep `dest_feature_class` as the PRIMARY dataset (the publish / ledger join key), so existing
      rows and scripts keep working.

### 4.3 Relationships stage (BEFORE publish)
- [ ] Build `CreateRelationshipsInGDB.py` (the unbuilt pipeline stage), per item:
      read the source relationships (live service; same pairing as
      `GetAllArcGISServiceMetadata.summarize_service_layers`), resolve both ends through
      `dest_datasets` (exact, no service manifest needed), then `CreateRelationshipClass`.
- [ ] Reuse `add_relationship.py`'s checks: key fields exist with the same type, not branch-versioned,
      already-exists / different-keys detection, unique RC name, read-back VERIFY.
- [ ] License: creating relationship classes in an enterprise gdb needs Pro Standard/Advanced or
      ArcGIS Server's Python (`ArcServer`) on nbs-app2. Run the stage there, or fall back to
      `add_relationship.py`'s manual-script output (status MANUAL).
- [ ] Mark the stage `built=True` in `run_migration_pipeline.build_stages`.
- Running it before publish means ONE publish exposes everything -- no republish.

### 4.4 Publish: every layer + table in one service
- [ ] `PublishFromDBToFeatureService.py`: when the ledger row has `dest_datasets`, add every
      feature class (`addDataFromPath` / `MakeFeatureLayer`) and table (`addTable`) to the temp map,
      in SOURCE order, plus the relationship classes they participate in.
- [ ] Set each layer's service layer id to the SOURCE layer id (`useServiceLayerIDs=True` +
      CIM `serviceLayerID`), so ids stay stable for symbology, relationships, and web maps.
- [ ] `BuildPublishCSV.py`: still one row per ITEM (the primary dataset as `feature_name`); remove
      the Part 1 guard once this lands.

### 4.5 Symbology: per layer
- [ ] step6: loop over the source layer ids (renderer + pop-up + visibility range per layer, plus
      table pop-ups) instead of only `target_layer_id=0`, for both the Enterprise and the AGOL
      by-reference items.

### 4.6 Validate
- [ ] No change needed: `ValidateMigratedItems.py --check-db` already pairs every layer/table via the
      service manifest (counts, fields, attachments, relationships, values).
- [ ] Re-validate the hand-fixed items in section 1 to confirm they now pass.

---

## 5. Deploy

The migration toolset runs from the deployed copy at `C:\Admin\Tools` on nbs-app2, not from the repo.
After each step lands, copy the changed scripts there (`run_migration_pipeline.py`,
`run_migration_batch.py`, the step scripts, `PublishFromDBToFeatureService.py`, `BuildPublishCSV.py`,
`ValidateMigratedItems.py`, `repair_item_from_export.py`, `add_relationship.py`).

---

## 6. Open questions

- Should a multi-layer item publish to ONE service (matches the source) -- assumed yes.
- Layer id preservation: confirm a referenced MapServer honors CIM `serviceLayerID` for tables too.
- Hosted VIEW sources: export carries the PARENT schema (hidden fields come along); the validator now
  treats those as WARNINGs. Decide whether the copy should drop view-hidden fields instead.

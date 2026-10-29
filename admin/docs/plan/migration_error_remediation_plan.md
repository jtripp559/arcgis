# Migration Error Remediation Plan (Phase 1 batch)

Date: 2026-06-12
Author: Julie Tripp (assisted)

Source ledger analyzed:
`\\nbs-app2\C$\Admin\Tools\ArcGIS Admin\Migrate\Output\migration_status_ledger.csv`
Driven by: `run_migration_batch.py` over `Input\ItemsToMigratePhase1.csv` (nbs-app2).

---

## 1. Summary of what the `error` column shows

49 ledger rows. 21 carry a recorded error. They fall into exactly THREE classes.
All three are repeating: the same items re-error on every batch sweep (every ~30 min
over 2026-06-11/06-12), because an errored row is intentionally skipped on resume,
so a bad row never clears itself - it just keeps re-recording.

| Class | Rows | State | Error signature (repeated) |
|-------|------|-------|----------------------------|
| A | 14 | (blank) | `[step3] batch gate: copy stage 'step3' exited 0 but ledger state 'copied_local' did not appear within 120s` |
| B | 6 | `copied_local` | `[publish] feature dataset T:\...\<db>_<schema>.sde\<DB>.<schema>.<FC> does not exist. Skipping...` (logged ~11x each) |
| C | 1 | (blank) | `[copy_local] staging copy AGOL->FGDB failed for 2022_Statewide_Crop_Mapping_Provisional (no output FC)` |

The other 28 rows are healthy: 14 at `source_deprecated` (fully done) and 14 at
`copied_to_gdb` (mid-pipeline, no error - the sweeps will carry them forward).

---

## 2. Class A - "batch gate ... copied_local did not appear" (14 items)

### Affected items
| item_id | title |
|---------|-------|
| 8b7d4523c63a4899ab37f4db484ad654 | Lemon Lime Western Varieties Wind Risk Free 2030 (v.5) |
| 787eff1a35eb45ada7f6c5bc83eafa7d | Lemon Lime Western Varieties 2030 (v.5) |
| b76c69d1679443e1969bee912e1d1ba5 | Fuentes hidricas intermitentes |
| 90f70e34610b4c45955e6f7fc520d43d | Coffee Arabica 2030 (v.2) |
| e21bb3bccfab459d8f044c858179d9b0 | Sour Cherry Historic (v.4) |
| 5da4d63c2d7f4a77b844113ebf207e90 | Coffee arabica Historical (v.2) |
| 2250907c7bd842ba907948193d417389 | Asparagus Cold Dormancy Historic (v.2) |
| 5f7fa02b68144e78af3bf51f44e50a65 | Coffee arabica Current (v.2) |
| 9ec8be71f7484817aa268a3733c7b446 | Sweet Cherry Historic (v.4) |
| e844055723d1470cb1bbe241798029b7 | Cacao 2030 (v.2) |
| c5954f1e4d254083b3f2153342512643 | WorldGeologicMap |
| b56c9a9666214070b2a183d6cffc1da6 | Cacao Historic (v.2) |
| 53c88c1fd6254387bd63a19171184a87 | Asparagus Cold Dormancy 2030 (v.2) |
| a66f9261fa7045a2bd7152964fdcb431 | Guayule Historic (v.1) |

### Root cause (confirmed in code)
These are all sources that are ALREADY WGS84 (EPSG:4326). The pipeline is designed to
skip local staging for 4326 sources and copy AGOL -> SDE directly in step3c:

- `docs\plan\completed\migration_poc_step3_stage_local.py:244-254` - when
  `live_wkid == TARGET_WKID and not FORCE_LOCAL_STAGING`, step3 logs the "direct path"
  message and `return`s. It writes NO ledger state (no `copied_local`) and records NO error.
  The process exits 0.
- `migration_poc_step3c_load_sde.py:18-19,187` - step3c handles this: with no staged FC it
  does the direct paged AGOL -> SDE copy and sets `copied_to_gdb`.

But the batch driver gates BETWEEN step3 and step3c on `copied_local`:

- `run_migration_batch.py:272-289` (`copy_one_item` -> `wait_for_stage_state`) blocks up to
  `STATE_WAIT_SECONDS` (120s) for step3's milestone `copied_local`. For a 4326 source that
  milestone never arrives, so the gate TIMES OUT, records the false `batch gate:` error
  (`run_migration_batch.py:282`), and stops the item's chain BEFORE step3c ever runs.
- On the next batch run, `build_copy_worklist` (`run_migration_batch.py:174-177`) sees the
  recorded error and skips the item ("clear it to retry"). So it is stuck forever.

Net: every already-4326 item is structurally unable to pass the batch driver's copy chain.

### Fix

Code fix (prevents recurrence) - pick ONE:

- Preferred: make step3 record `copied_local` on the direct-path return too, so the gate is
  satisfied and step3c then runs in direct mode. In `migration_poc_step3_stage_local.py`,
  before the `return` at line 254 add a `ledger_mod.set_state(ITEM_ID, "copied_local", ...,
  source_service_url=service_url, dest_feature_class=dest_name)`. Semantics stay correct:
  `copied_local` = "step3 finished"; step3c still self-selects direct vs load mode by whether
  a staged FGDB exists.
- Alternative: in the batch driver, do not require `copied_local` after step3 for direct-path
  items (e.g. treat step3 as gated by exit code alone, like step1). More invasive; the step3
  change above is the smaller, clearer fix.

Immediate unblock (these 14 items, no code change required): run step3c directly per item -
it does the direct AGOL -> SDE copy for 4326 sources and bypasses the batch gate entirely.
First clear the false gate error so the row is eligible again, then load:

```powershell
$py  = "C:\Users\JulieTripp\AppData\Local\ESRI\conda\envs\arcgispro3_5-clone\python.exe"
$dir = "C:\Admin\Tools\ArcGIS Admin\docs\plan\completed"
$ids = @(
  "8b7d4523c63a4899ab37f4db484ad654","787eff1a35eb45ada7f6c5bc83eafa7d",
  "b76c69d1679443e1969bee912e1d1ba5","90f70e34610b4c45955e6f7fc520d43d",
  "e21bb3bccfab459d8f044c858179d9b0","5da4d63c2d7f4a77b844113ebf207e90",
  "2250907c7bd842ba907948193d417389","5f7fa02b68144e78af3bf51f44e50a65",
  "9ec8be71f7484817aa268a3733c7b446","e844055723d1470cb1bbe241798029b7",
  "c5954f1e4d254083b3f2153342512643","b56c9a9666214070b2a183d6cffc1da6",
  "53c88c1fd6254387bd63a19171184a87","a66f9261fa7045a2bd7152964fdcb431")
foreach ($id in $ids) {
  & $py "C:\Admin\Tools\ArcGIS Admin\Migrate\clear_error.py" $id   # see note below
  & $py "$dir\migration_poc_step3c_load_sde.py" $id
}
```

Note on clearing errors: there is no standalone CLI to clear a single row's error. Either
add a tiny one (calls `migration_status_ledger.clear_errors(id)`), or edit the `error` cell
to empty in the CSV for these rows before re-running. Once step3c sets `copied_to_gdb`, the
once-stage sweeps publish them onward.

---

## 3. Class B - "[publish] feature dataset ... does not exist. Skipping..." (6 items)

### Affected items (all stuck at `copied_local`)
| item_id | dest FC | db.schema |
|---------|---------|-----------|
| f921b738e68b4cf092b16b55ad296888 | Apples_2030_v1 | RRGOrg.crop |
| 0aa778954e3649ba84c261689d985249 | Elevation_Contours_10m_Rancho_del_Cielo | NBS_Client.general |
| e9970bf084df4585bc1a0a6a76755eb2 | Apple_Washington_Varieties_and_Practices_2050_V1 | NBS_MaxEnt.general |
| 80c798011211461db6d5b92cb6edf49b | Mandarin_USA_..._Change_from_Current_to_2010_V7 | NBS_MaxEnt.general |
| 6b491258367644a8b95397179a1296a6 | World_Provinces_MaizeSoyRapeseed | NBS_WS.clim |
| f3d57b7336df40b28411b6410406153b | Avocados_Hass_..._Change_from_Current_to_2010 | RRGOrg.crop |

### Root cause (confirmed in code)
These items staged to local FGDB (`copied_local`) but were NEVER loaded into the SDE
(step3c did not reach `copied_to_gdb`). Meanwhile the publish sweep tried to publish them:

- `BuildPublishCSV.py:286` - `generate(..., include_state="copied_local")`. The default
  minimum rank is `copied_local`, so the auto-generated publish CSV INCLUDES items that are
  only staged locally and not yet in the SDE. (`run_migration_batch.py:426` calls `generate`
  without overriding `include_state`, so it uses this default.)
- `PublishFromDBToFeatureService.py:2308-2310` - the publish step checks
  `arcpy.Exists(<sde>\<DB>.<schema>.<FC>)`; the FC is not in the SDE yet, so it logs
  `feature dataset ... does not exist. Skipping...` and records the error to the ledger.
- That recorded publish error then blocks the copy resume from ever running step3c
  (`run_migration_batch.py:174-177` skips errored rows) - the same deadlock as Class A.

The repetition (~11 entries per row) is one error per periodic sweep across the run window.

### Fix

Code fix (prevents recurrence): change the publish-CSV minimum state to `copied_to_gdb`
so only items actually loaded into the SDE are eligible to publish:

- In `BuildPublishCSV.py:286`, default `include_state="copied_to_gdb"` (the FC must exist in
  the SDE before publish can reference it). The CLI already documents `--include-state
  copied_to_gdb`; this just makes it the default the batch driver inherits.
- Optionally also have `run_migration_batch.py` pass `include_state="copied_to_gdb"` explicitly
  at the `bpcsv.generate(...)` call (`run_migration_batch.py:426`) as belt-and-suspenders.

Immediate unblock (these 6 items): clear the `[publish]` error, run step3c (LOAD mode - the
staged FGDB still exists for `copied_local` rows), then regenerate the publish CSV and sweep:

```powershell
$py  = "C:\Users\JulieTripp\AppData\Local\ESRI\conda\envs\arcgispro3_5-clone\python.exe"
$c   = "C:\Admin\Tools\ArcGIS Admin\docs\plan\completed"
$ids = @("f921b738e68b4cf092b16b55ad296888","0aa778954e3649ba84c261689d985249",
         "e9970bf084df4585bc1a0a6a76755eb2","80c798011211461db6d5b92cb6edf49b",
         "6b491258367644a8b95397179a1296a6","f3d57b7336df40b28411b6410406153b")
foreach ($id in $ids) {
  # clear the [publish] error for $id (see Class A note), then:
  & $py "$c\migration_poc_step3c_load_sde.py" $id
}
# after all reach copied_to_gdb, rebuild the publish CSV and let the batch sweeps publish:
& $py "C:\Admin\Tools\ArcGIS Admin\Migrate\run_migration_batch.py" --ledger-only --regen-publish-csv
```

If a per-item staging GDB was already cleaned up (so step3c has no FGDB to LOAD) and the
source is not 4326, re-run step3 first (or step3 with `FORCE_LOCAL_STAGING=True`) to re-stage,
then step3c.

---

## 4. Class C - "staging copy AGOL->FGDB failed (no output FC)" (1 item)

### Affected item
| item_id | title | size |
|---------|-------|------|
| 5798cb579f354ab385d8ea5917d9f7ae | 2022 Statewide Crop Mapping Provisional | ~468 MB |

### Root cause
This is a GENUINE copy failure, not a state-machine artifact. In
`migration_poc_step3_stage_local.py:274-278`, the AGOL -> FGDB paged copy
(`copyData`/CopyFeaturesFromService) produced no output feature class, so step3 recorded the
error and stopped. Most likely a large/complex layer hitting a paging, timeout, or geometry
issue during the download (it is the second-largest crop layer in the batch).

### Fix / investigation
1. Read the CopyFeaturesFromService log referenced by step3's run
   (`...\Migrate\Output\` or the CopyFeaturesFromService log dir) to see the real failure
   (timeout vs transfer limit vs geometry/field error).
2. Clear the `[copy_local]` error for this id, then re-run step3 once:
   `python migration_poc_step3_stage_local.py 5798cb579f354ab385d8ea5917d9f7ae`
3. If it fails again on size/paging: lower the page size or set `FORCE_LOCAL_STAGING=True`
   and retry; confirm `maxRecordCount` on the source and that the token/credentials are valid
   for the full extent. A transient AGOL timeout often succeeds on a clean retry.
4. Once it reaches `copied_local`, run step3c to load it, then let the sweeps publish.

---

## 5. Cross-cutting issue: errored rows never self-heal

All three classes share an amplifier: once a row has ANY recorded error,
`build_copy_worklist` (`run_migration_batch.py:174-177`), `BuildPublishCSV.build_rows`
(`BuildPublishCSV.py:237-244`), and the publish gate all skip it until the error is cleared
by hand. That is the intended safety design, but there is currently NO convenient way to
clear a single row's error.

Recommended: add a small `clear_error.py <item_id> [--phase X]` CLI in `Migrate\` that calls
`migration_status_ledger.clear_errors(item_id, phase=...)`. This is needed for the immediate
unblock steps above and for routine operation. (`clear_errors` already exists in
`migration_status_ledger.py:550`; it just lacks a CLI wrapper.)

---

## 6. Recommended order of execution

1. Add `clear_error.py` CLI (Section 5) - prerequisite for the unblock steps.
2. Apply the two code fixes:
   - step3 writes `copied_local` on the 4326 direct-path return (Class A).
   - `BuildPublishCSV` default `include_state="copied_to_gdb"` (Class B).
   - Redeploy the edited scripts to `C:\Admin\Tools\...` (the toolset runs from the deployed
     copy, not the repo).
3. Investigate + retry Class C (1 item) - it is independent and may need a real fix.
4. Unblock Class A (14) and Class B (6): clear errors, run step3c per item.
5. Re-run `run_migration_batch.py --ledger-only --regen-publish-csv` to publish everything now
   at `copied_to_gdb`, then let it run to `source_deprecated`.

## 7. Verification

- After step3c on the A/B items: confirm each row's `state` advanced to `copied_to_gdb` and
  its `error` is empty.
- After the sweep: confirm they progress through `published_to_portal` ... `source_deprecated`
  with no new errors.
- Re-run the analysis: no rows should remain with a blank `state`+error, and the
  `feature dataset ... does not exist` and `batch gate ... did not appear` signatures should
  not reappear on subsequent sweeps (the code fixes prevent regeneration).

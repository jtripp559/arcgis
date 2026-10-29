# Attachments Copy Plan (AGOL -> RRGOrg migration + reusable tool)

Status: **RESOLVED / PROVEN END TO END (2026-06-12).** Date: 2026-06-12. Owner: Julie Tripp.

Companion to `docs/plan/migration-plan.md`. Scope: preserve feature ATTACHMENTS (and,
by the same mechanism, relationship classes + GlobalIDs) through the AGOL -> RRGOrg
migration.

POC test item: `196d4eb4de7043e7af3b75e76278da12` (one layer, no tables, no
relationships, HAS attachments).

---

## 0. OUTCOME (2026-06-12) -- attachments travel WITH the data via "route (b)"

The original premise of this doc -- copy attachments in a SEPARATE pass and match
source->dest on GlobalID -- was driven by the limits of the `copyData` REST/query copy
engine, which **drops attachments AND the GlobalID entirely** (empirically confirmed:
the staged FC had no GlobalID field at all). Investigation found a better path:

**Route (b): export the source item to a File Geodatabase (Esri "Export to FGDB").** A
server-side extract job brings the feature class **plus** its `__ATTACH` table, its
`__ATTACHREL` relationship class, **and the ORIGINAL managed GlobalIDs** in one operation
(also tables + all layers; not bounded by `maxRecordCount`). The migration now stages
attachment/relationship-bearing items this way, so **attachments are no longer a separate
copy pass** -- they ride along with the feature class, already linked.

Proven end to end on the POC item (all isolated: local ledger + a test SDE):
1. **Export -> FGDB**: managed GlobalIDs preserved 13/13; `__ATTACH` (13 rows) +
   `__ATTACHREL` present; attachment binaries byte-identical (1,167,062 B).
2. **Reproject in the FGDB** with `arcpy.env.preserveGlobalIds=True`: bundle + binaries
   survive (Project for non-4326; ExportFeatures for already-4326).
3. **FGDB -> SQL Server SDE** via `ExportFeatures` with `preserveGlobalIds=True`: full
   fidelity -- count, original GlobalIDs, `__ATTACHREL`, and `__ATTACH` (byte-identical)
   all land. (`arcpy.management.Copy` FGDB->SDE FAILED -- not a viable load.)
4. **Publish BY REFERENCE** (MAP_IMAGE + Feature Access) and the referenced FeatureServer
   serves attachments: `queryAttachments?objectIds=...` and the per-feature
   `/{oid}/attachments` endpoint both return all 13, and a blob downloaded (HTTP 200,
   81188 B, image/jpeg). (Quirk: `queryAttachments?where=1=1` returns 0 on this build --
   use objectIds/globalIds or the per-feature endpoint, which is what pop-ups/web maps use.)

**Tooling built:** `Migrate/export_item_to_fgdb.py` (export + download + verify row counts
and GlobalID preservation; temporarily enables/restores the source `Extract` capability).
**Pipeline wiring:** `migration_poc_step3_stage_local.py` (`EXPORT_MODE="always"`,
export-first with a copyData fallback, reproject with `preserveGlobalIds=True`) and
`migration_poc_step3c_load_sde.py` (`preserveGlobalIds=True` load + `__ATTACH` count check).

`copy_attachments.py` (Sections 3+ below) is therefore **NO LONGER the primary mechanism**
for the SDE migration. It is retained as a reusable standalone tool (service->service
attachment copy, or a fallback when an item cannot be exported). The GlobalID-matching
analysis below stands as the rationale for why route (b) -- which sidesteps matching by
keeping attachments physically attached -- was chosen.

---

## 1. Goal

Preserve attachments through the migration so a migrated item's features keep their
attached files (photos, PDFs, etc.), and provide a standalone, reusable tool that can
move attachments between any two layers (AGOL -> SDE, SDE -> AGOL by-reference, etc.).

Capability order decided 2026-06-12: **attachments first** (most isolated; the test
item touches no publish/manifest/symbology changes), then tables + multiple layers,
**relationships last**. Attachments also forces solving GlobalID preservation, which
relationships need too -- so doing it first de-risks the hardest capability.

---

## 2. Why a separate step was required (for the copyData path only)

> Superseded by route (b) -- see Section 0. This section explains the `copyData`
> limitation that motivated a separate attachment pass; route (b) (export-to-FGDB)
> avoids it by keeping attachments physically attached to the feature class.

The migration copy engine (`copyFeaturesFromService.copyData`) copies features via the
REST `/query` endpoint -> `arcpy.FeatureSet` -> `FeatureClassToFeatureClass`. A `/query`
response carries **geometry + attributes only**, never the attachment binaries, so
attachments are **silently dropped** by the copy. (`arcpy.env.maintainAttachments=True`
is set in `copyData` but is a no-op when the source is a REST FeatureSet rather than a
real geodatabase dataset.) Attachments must therefore be copied in a separate pass,
after the features have landed.

### The matching problem (central design constraint)

OBJECTIDs are reassigned when features are copied, so the source OBJECTID does NOT
identify the same row on the destination. Attachments must be matched on a field that
survives the copy with the SAME value on both sides:

- **GlobalID (preferred IF preserved).** Works only if the destination kept the source
  GlobalIDs. A plain `FeatureClassToFeatureClass` / `ExportFeatures` **regenerates**
  GlobalIDs, so GlobalID matching then finds ZERO overlap. Preserving them requires
  `arcpy.env.preserveGlobalIds=True` with an Append-style load (a change to the copy
  step -- see open questions).
- **A natural key.** Any attribute field unique + identical on both sides. Use this when
  GlobalIDs were not preserved.

The tool validates the join (present on both sides, unique, non-empty, overlapping) and
**fails loudly** with the specific reason rather than silently dropping attachments.

---

## 3. What is built: `Migrate/copy_attachments.py`

Standalone + reusable (does NOT advance a migration pipeline state; records errors to the
ledger only when `--item-id`/`--from-step1` is given, under phase `attachments`).

Flow:
1. Connect to the source (credential_store, `agol` key first; Pro/prompt fallback).
2. Enumerate source attachments (`FeatureLayer.attachments.search`); read OBJECTID ->
   join-key maps on both sides.
3. Validate the join; stop with guidance if it cannot match.
4. Download each attachment to a collision-proof temp subfolder, renamed to its original
   name.
5. Add to the destination:
   - **arcpy FC dest** (the migration / SDE case): `AddGlobalIDs` only if none exist,
     `EnableAttachments`, then `AddAttachments` via an in-memory match table.
   - **service dest**: `FeatureLayer.attachments.add` per feature.
6. Verify counts; log a summary; clean up the temp folder.

Key flags: `--from-step1 <id>` (auto-fills source service + dest SDE FC from the Step-1
report), `--source-item`/`--source-url`/`--source-layer`, `--dest-fc`/`--dest-url`/
`--dest-layer`, `--join-field` (default `GlobalID`, GUID-normalized), `--dest-join-field`,
`--dry-run`, `--keep-downloads`.

---

## 4. Two storage models -- the key design fork

The source items use **geodatabase attachments** (the Esri feature-attachment system:
binaries in a `<fc>__ATTACH` table related to the feature class by GlobalID, served
through the feature service's attachment REST endpoints). There are two ways to land them
on the destination:

### Option A -- Geodatabase attachments (what the tool does today)
Load the binaries into the SDE FC's `__ATTACH` table. The referenced feature service then
serves them via `.../FeatureServer/<layer>/queryAttachments` and
`.../FeatureServer/<layer>/<oid>/attachments/<id>`.
- **Security: token comes for free.** Because the attachments are served by the (secured)
  feature service, every attachment request already requires the service's token. No extra
  infrastructure.
- Fidelity: an exact round-trip of the source model; pop-ups / attachment widgets work
  unchanged.
- Cost: binaries live in the RRGOrg SQL database (BLOBs) -- DB growth at scale (~6500
  items eventually).

### Option B -- Files in the ArcGIS Server `webdocs` directory, referenced by URL
Store the files in `T:\ArcGISDataset\ArcGISWebDocs\attachments\` and serve them from the
registered Site Directory at
`https://maps.rrgnbs.com/arcgisserver/rest/directories/webdocs/attachments/`
(verified working: `...\webdocs\attachments\test.txt` ->
`.../rest/directories/webdocs/attachments/test.txt`). The feature layer would then
reference each file by URL (in an attribute field and/or pop-up content) rather than
storing the bytes in the geodatabase.
- Motivation: keep large binaries OUT of the SQL database; serve them as plain static
  files.
- **This is NOT the geodatabase attachment model.** Feature-service attachments are blobs
  in the `__ATTACH` table; they do not reference external URLs. Option B is a different
  data model (URL-in-a-field) and would not appear through the standard attachment
  endpoints / attachment widgets unless separately wired into `popupInfo`.
- **Security is the open problem** -- see Section 5.

**DECISION (2026-06-12): Option A (geodatabase attachments).** Chosen for native token
security (the secured feature service enforces it -- see Section 5) and exact round-trip
fidelity. Option B is shelved (revisit only if SQL DB growth from BLOBs becomes a problem).
Downloaded binaries are staged at
`T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\Migrate\Attachments`
(beside the per-item staging gdbs), in a per-source subfolder
(`<dir>\<item_id>\att_<oid>_<id>\<name>`). They are **KEPT by default** (not deleted) so
other workflows can reuse the originals; pass `--cleanup-downloads` to remove a source's
subfolder after a successful load. Override the base with `--download-dir`.

---

## 5. Securing the `webdocs` directory with a token (Option B)

Requirement: accessing `https://maps.rrgnbs.com/arcgisserver/rest/directories/webdocs/attachments/`
must require a valid token.

Findings (needs confirmation against our 11.x version + a live test):

- ArcGIS Server has a Security Configuration flag **`virtualDirsSecurityEnabled`**. When
  `true`, "accessing the content of secured services in the **arcgisoutput, arcgisjobs,
  and arcgisinput** directories over HTTP will require user authentication."
- That setting is scoped to **those three service directories and to content of SECURED
  SERVICES**. A custom registered Site Directory served at `/rest/directories/webdocs/`
  is **not** one of those three, and static files placed there are **not associated with a
  secured service** -- so it is doubtful that `virtualDirsSecurityEnabled` will token-gate
  `webdocs`. THIS IS THE CENTRAL OPEN QUESTION for Option B (test it before committing).
- If `virtualDirsSecurityEnabled` does not cover `webdocs`, token-securing arbitrary
  static files would need a different tier:
  - **Web Adaptor / IIS authentication or URL authorization** on the `webdocs` path --
    this is web-tier auth (Windows/Basic/IWA), NOT an ArcGIS token, so it would not satisfy
    "valid token" literally and could break clients that pass `?token=`.
  - **A custom reverse proxy / handler** that validates an ArcGIS token before serving the
    file -- effective but custom code to build and maintain.
  - **Don't use a static directory at all** -> Option A, where the feature service enforces
    the token natively.
- Net: **if token security is a hard requirement, Option A satisfies it with no extra work;
  Option B has no clean, supported token-security path today.** This is the strongest
  argument for Option A.

---

## 6. Open questions & concerns

1. **GlobalID preservation. RESOLVED 2026-06-12 -> route (b).** `copyData` does not just
   regenerate GlobalIDs, it **drops the field entirely** (confirmed). Rather than retrofit
   `preserveGlobalIds` onto the REST copy (which cannot carry a managed GlobalID from a
   FeatureSet anyway), the migration switched to **export-to-FGDB**, which preserves the
   ORIGINAL managed GlobalIDs natively, and loads them into SDE with
   `arcpy.env.preserveGlobalIds=True` (proven: original GlobalIDs preserved 13/13 end to end).
   This also satisfies relationships, which need the same preserved keys. GlobalID *matching*
   (the `--join-field` problem) is moot for route (b) because attachments stay attached.
2. **Do attachments survive the by-reference publish? RESOLVED 2026-06-12 -> YES.** Published
   the test SDE FC as MAP_IMAGE + Feature Access by reference; the referenced FeatureServer
   reports `hasAttachments=True` + `supportsQueryAttachments=True`, the per-feature
   `/{oid}/attachments` endpoint and `queryAttachments?objectIds=...` both return all 13, and
   a blob downloaded (HTTP 200, 81188 B, image/jpeg). Quirk: `queryAttachments?where=1=1`
   returns 0 on this build -- use objectIds/globalIds or the per-feature endpoint (what
   pop-ups/web maps use). (Consumer-through-by-ref-item with stored credentials: the by-ref
   AGOL item points at this same FeatureServer URL, so it inherits the same attachment access.)
3. **Attachments enabled / GlobalIDs on the SDE FC. RESOLVED 2026-06-12.** With route (b) the
   `__ATTACH` table + `__ATTACHREL` relationship class arrive WITH the feature class on the
   `ExportFeatures` load (no separate EnableAttachments needed); the schema-owner / sde
   connection created them fine, and the by-reference publish picked up the attachment
   capability without any extra step.
4. **Option A vs Option B decision. RESOLVED 2026-06-12 -> Option A (geodatabase
   attachments).** Native token security + exact fidelity. Watch SQL DB growth from BLOBs
   across ~6500 items; if it becomes a problem, revisit Option B (a rough size estimate =
   attachment count x average size would inform that).
5. **Where should the binaries physically stage? RESOLVED 2026-06-12.** Download base is
   `T:\...\AGOL\Migrate\Attachments` (`ATTACHMENTS_STAGING_DIR`; `--download-dir` overrides),
   in a per-source subfolder (`<item_id>\att_<oid>_<id>\<name>`). KEPT by default for reuse
   by other workflows; `--cleanup-downloads` deletes a source's subfolder after a successful
   load. (Re-running a source refreshes its folder; if a source's attachments change between
   runs, stale files could linger -- acceptable for the migration, note it if that matters.)
6. **Symbology / pop-up step interaction (Option B only).** If we go with URL references, the
   Phase 4 symbology/pop-up apply must inject the attachment URLs into `popupInfo` -- extra
   work in `ApplySymbology` / the Step 6 apply. Not needed for Option A.
7. **Non-unique / missing join keys.** Some layers may have no unique natural key and no
   preserved GlobalID. Define the fallback (per-item manual key, or mandate GlobalID
   preservation globally).
8. **Pipeline integration.** Should `copy_attachments.py` become a stage in
   `run_migration_pipeline.build_stages` (per-item, after `step3c`, no-op when the source has
   no attachments), or stay standalone for the POC? Currently standalone.
9. **Idempotency / re-runs. RESOLVED 2026-06-12 (dedup guard built).** Neither `AddAttachments`
   nor the service add de-dupes, so a re-run would DUPLICATE. The tool now reads the destination's
   existing attachments first and SKIPS any source attachment that matches an existing
   (feature, name, size) -- so re-runs only add the delta. Caveat: two distinct files with the
   SAME name + SAME size on the same feature would be treated as already-present (a corrupted/
   edited file of identical size is the realistic miss). Acceptable for the migration; revisit
   with a content hash only if it bites. If reading the existing set fails, the guard is skipped
   with a warning (a re-run could then duplicate).
10. **Large attachments / throughput.** Per-attachment download+add over REST at ~6500 items
    could be slow and hit AGOL rate limits (429). Consider batching / backoff, mirroring the
    copy phase's paging concerns.

---

## 7. POC test plan (item `196d4eb4...`) -- DONE 2026-06-12 (route b)

No `copy_attachments.py` step is needed -- attachments ride along with the feature class
via route (b). The proven flow (run isolated: local ledger + a test SDE):

```
# from the Migrate folder, ArcGIS Pro conda env:
python migration_poc_step3_stage_local.py 196d4eb4... --migrate-dir <local scratch>
#   -> detects hasAttachments -> EXPORT path -> staged FC + __ATTACH(13) + __ATTACHREL,
#      original GlobalIDs preserved, reprojected to 4326 with preserveGlobalIds=True.
python migration_poc_step3c_load_sde.py   196d4eb4... --migrate-dir <local scratch>
#   -> ExportFeatures with preserveGlobalIds=True loads the bundle into SDE:
#      count 13, GlobalIDs 13/13, __ATTACHREL created, __ATTACH 13 rows byte-identical.

# publish BY REFERENCE (server folder, tag), then verify attachments serve:
python PublishFromDBToFeatureService.py <publish.csv> --server-folder Test ...
#   FeatureServer/0/queryAttachments?objectIds=...   -> all 13
#   FeatureServer/0/<oid>/attachments/<id>           -> blob (HTTP 200, bytes match)
```

Success criteria (ALL MET): source attachment count == dest `__ATTACH` count (13);
original GlobalIDs preserved (13/13); `__ATTACHREL` present; binaries byte-identical
(1,167,062 B); attachments reachable through the published referenced FeatureServer
(and therefore the AGOL by-reference item, which points at the same URL).

> Standalone-tool dry-run validation for `copy_attachments.py` (the service->service /
> fallback path) is still useful if/when that tool is used, but it is NOT on the SDE
> migration path anymore.

---

## 8. References

- [Server directories - ArcGIS Enterprise](https://enterprise.arcgis.com/en/server/latest/administer/linux/about-server-directories.htm)
- [Security Configuration (virtualDirsSecurityEnabled) - ArcGIS REST APIs](https://developers.arcgis.com/rest/enterprise-administration/server/securityconfig/)
- [Access ArcGIS token-secured web services - ArcGIS Server](https://enterprise.arcgis.com/en/server/latest/administer/linux/accessing-arcgis-token-secured-web-services.htm)
- [Securing AGS output, cache, and jobs folders - Esri Community](https://community.esri.com/t5/arcgis-rest-apis-and-services-questions/securing-ags-output-cache-and-jobs-folders/td-p/518751)
- Companion: `docs/plan/migration-plan.md` (Phase 2 copy, Phase 3 relationships/attachments, decision #9 by-reference publish).

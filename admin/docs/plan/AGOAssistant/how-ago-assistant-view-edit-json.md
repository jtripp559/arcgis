# How ago-assistant Views and Edits an Item's JSON

Reverse-engineered from the Esri/ago-assistant source (`master` branch):
`src/js/portal/content/{itemDescription,itemData,updateDescription,updateData}.js`
and `src/js/portal/request.js`. ago-assistant is a thin client over the ArcGIS REST
"Sharing" API - every "View JSON" / "Edit JSON" action is one or two REST calls.

---

## 1. "View an Item's JSON" - getting Description and Data

ago-assistant shows two separate editable documents. They come from two **distinct** REST
resources, each fetched with a plain `GET` and `?token=...&f=json`.

### Description
`src/js/portal/content/itemDescription.js`
```
GET {portalUrl}sharing/rest/content/items/{id}?token=...&f=json
```
This is the **item resource** itself - the item's properties / metadata: `title`, `type`,
`tags`, `extent`, `snippet`, `typeKeywords`, `url`, `owner`, `access`, etc. This is the panel
ago-assistant labels **"Description."**

Maps to: `AGOAssistantSample_Description_45f53ad7838c47a28a5ff17f53312ee4.json`

### Data
`src/js/portal/content/itemData.js`
```
GET {portalUrl}sharing/rest/content/items/{id}/data?token=...&f=json
```
This is the item's **data resource** - a separate document from the description. For a
feature-layer item it is the visualization / config JSON: the `layers` array with
`layerDefinition` (renderer / drawingInfo), `popupInfo`, `blendMode`, etc. For a Web Map it
is the map's operational layers / basemap JSON. Items with no data resource return an empty
body, which the client resolves to `null`.

Maps to: `AGOAssistantSample_Data_45f53ad7838c47a28a5ff17f53312ee4.json`

So "View JSON" = `GET .../items/{id}` (Description) **plus** `GET .../items/{id}/data` (Data).
Two distinct resources - which is why the tool shows two boxes.

---

## 2. "Edit JSON" - how Save works

Both save paths **POST** to the same **Update Item** operation. The path is under
`users/{username}`, so the caller must be the item **owner** (or an org admin):

```
POST {portalUrl}sharing/rest/content/users/{username}/{folder}/items/{id}/update
content-type: application/x-www-form-urlencoded
```
`{folder}` is the owner's folder id (empty for root-folder items).

They differ only in **what they post**:

### Saving Data
`src/js/portal/content/updateData.js` - posts a single field `text`:
```
text=<edited data JSON as a string>, token=..., f=json
```
The `text` parameter is how the Update operation replaces an item's `/data`. (The file's
comment says "Web Map," but it is generic and works for any item's data resource, including a
feature-layer's layer/popup config.)

### Saving Description
`src/js/portal/content/updateDescription.js` - parses the edited JSON and **flattens each
property into its own form field**, because the Update op expects scalars, not arrays/objects:
```js
null    ->  ""                   // cleared fields
Array   ->  value.toString()     // e.g. tags, extent  ->  comma-separated string
Object  ->  JSON.stringify(...)  // e.g. properties     ->  stringified JSON
```
...then it appends `token` + `f=json` and POSTs every property as a separate form field
(`title=...&tags=a,b,c&extent=...&typeKeywords=...`). Each description property maps directly to an
Update-Item parameter.

### Transport
`src/js/portal/request.js` uses plain `XMLHttpRequest`:
- `GET` serializes parameters into the query string.
- `POST` url-encodes the body as `application/x-www-form-urlencoded`.
- The token is passed as a **parameter**, not a Bearer header.

---

## 3. How this maps to our repo

- `GetAllArcGISServiceMetadata.py` -> `save_item_json()` performs the **read** half of section 1
  - it pulls the same two documents (`/items/{id}` description and `/items/{id}/data`).
- The `..._FeatureServer_sources_...json` dump (`{"currentVersion":12,"services":[]}`) is
  **unrelated** to ago-assistant. It is the `{serviceUrl}/sources` admin probe from the old
  stored-credentials check - not the item description or data.
- To replicate the **save** in Python (arcgis API): `item.update(item_properties={...})` for
  the description and `item.update(data=...)` for the data both hit the same
  `/users/{owner}/items/{id}/update` endpoint under the hood, and both require ownership/admin.

## 4. Item `/data` (Update Item) vs Service `updateDefinition`

These two operations are often confused. They write to **different places** and carry
**different information** - this matters for migrating symbology + pop-ups.

| | Item `/data` (Update Item) | Service `updateDefinition` |
|---|---|---|
| Endpoint | `.../content/users/{owner}/{folder}/items/{id}/update` (param `text=`) | `{service-admin}/FeatureServer/{layerId}/updateDefinition` (param `updateDefinition=`) |
| Scope | The **portal item** (web layer / web map item) | The **published service** itself (the FeatureServer layer) |
| Carries **symbology** (`drawingInfo`/renderer) | Yes - `layers[].layerDefinition.drawingInfo` | Yes - `drawingInfo` on the layer |
| Carries **pop-ups** (`popupInfo`) | **Yes - pop-ups live ONLY here** | **No** - pop-ups are not a service concept |
| Auth needed | Item owner / org admin | Publisher / server admin on the federated server |
| Doc | this file | <https://developers.arcgis.com/rest/services-reference/enterprise/update-definition-feature-service/> |

Key takeaways:
- **Pop-ups can only be set through the item `/data`** (Update Item / `item.update(data=...)`).
  `updateDefinition` cannot store `popupInfo`.
- **Symbology can be set in either place** - in the item `/data` (so the portal item / web map
  shows it) and/or in the service via `updateDefinition` (so the service itself carries the
  renderer for every client). For a **referenced** feature service published to Enterprise you
  usually want both: `updateDefinition` for the service renderer, item `/data` for the pop-ups
  (and the item-level style).
- A renderer references **field names** (`renderer.field`, unique-value / class-breaks fields)
  and `popupInfo` references `fieldInfos`. Those fields must exist on the target with the same
  names or the renderer / pop-up will not resolve.

`update_item_data.py` in this directory implements all three modes:
`--apply item` (symbology + pop-ups via item `/data`), `--apply service` (symbology via
`updateDefinition`), and `--apply both`. It also remaps source->target layer ids (AGOL layer ids
rarely match the new Enterprise service's ids).

## 5. Quick reference

| Action | Method | Endpoint | Key params |
|---|---|---|---|
| View Description | GET | `.../content/items/{id}` | `token`, `f=json` |
| View Data | GET | `.../content/items/{id}/data` | `token`, `f=json` |
| Save Description | POST | `.../content/users/{username}/{folder}/items/{id}/update` | each property as a field |
| Save Data (symbology + pop-ups) | POST | `.../content/users/{username}/{folder}/items/{id}/update` | `text=<data json>` |
| Set service renderer | POST | `{service-admin}/FeatureServer/{layerId}/updateDefinition` | `updateDefinition=<drawingInfo>` |

Scripts in this directory:
- `get_item_json.py` - reproduces the two GET requests; writes Description + Data JSON identical
  to the ago-assistant samples.
- `update_item_data.py` - copies symbology and pop-ups from a source data JSON to a target item
  and/or its service (`--apply item|service|both`), with source->target layer-id remap.

## Plan: V3 Split With Metadata Pairing

DRAFT — Split the current V2 UI code into two standalone scripts while preserving Flet UI layouts, reuse the existing chunking logic, and implement content-only MD outputs with paired metadata JSON files. Standardize uploads on the management API multipart flow with `fields` metadata, validating MD–metadata pairs and reporting progress. Update top-level docs only, and add a lightweight validation layer to maintain backward compatibility with current JSON input and config files.

**Steps**
1. Inventory and map the current UI generation/upload flows in CollectionUploaderV2UI.py (generate_md_files, process_sentenca, chunk_text, create_metadata_header, upload_to_collection, and config UI sections).
2. Create MD_GenerationV3.py by copying the relevant UI sections (file/dir pickers and actions row) from CollectionUploaderV2UI.py and wiring the “Gerar Arquivos MD” action to new logic:
   - Add a checkbox next to the button that toggles chunking.
   - Generate content-only MD files from conteudo and write paired metadata JSON files with all other keys.
   - Preserve existing chunking behavior (2048/256 sentence-aware).
3. Create CollectionUploaderV3.py by copying the relevant UI sections and wiring the upload action to:
   - Discover MD–metadata pairs by naming convention and validate pair integrity before upload.
   - Build multipart payloads with file + fields JSON (metadata) using the current management API approach.
   - Add progress indicators and success/failure notifications in the UI.
4. Introduce a small, explicit validation layer in both V3 scripts to ensure:
   - Required JSON keys exist (conteudo plus metadata fields).
   - MD and metadata naming conventions match and are one-to-one.
   - Backward compatibility for configs (reuse existing keys and defaults).
5. Update top-level docs only:
   - Add new usage sections for MD_GenerationV3.py and CollectionUploaderV3.py in README.md, USAGE_GUIDE.md, and TESTING_GUIDE.md.
   - Document the checkbox effect and the MD/metadata pairing behavior with examples.
   - Update API references to the management API multipart fields metadata flow.
6. Add a brief “Architecture Options” note that evaluates:
   - Plugin-based generator/uploader modules.
   - Config-driven presets for generation/upload settings.
   - Queue-based batch processing for large datasets.
   - Validation layer benefits and constraints.

**Verification**
- Manual UI run-throughs for both scripts: generate MD+metadata with checkbox on/off; validate output naming and content; upload a small batch and confirm success notifications.
- Spot-check that metadata JSON payload matches the expected fields structure used by the management API.

**Decisions**
- Use management API multipart upload with fields JSON for metadata.
- Content-only MDs with separate metadata JSON files; no YAML front matter.
- Copy UI sections into each V3 script; no shared UI module for now.
- Update only top-level documentation files in this pass.

---

## Plan: Add Collection Creation + Metadata Validation (V3)

DRAFT — Extend the V3 UI flow to optionally create a new collection from the Configurações panel, pre-populating the required metadata fields shown in your image. When a user selects an existing collection, validate that its metadata schema matches the expected keys (including `palavras-chave`) and block upload if there is a mismatch, with actionable error messages. This keeps the V3 separation intact while enforcing schema consistency for hybrid search.

**Steps**
1. Locate the Configurações UI in the V3 scripts (copied from CollectionUploaderV2UI.py) and add:
   - A checkbox “Criar nova collection”.
   - A name input visible/enabled only when the checkbox is set.
2. Define a single canonical metadata schema for V3 based on your preference: categoria, reclamada, numero_processo, data_publicacao, tipo_acao, palavras-chave. Keep this list in one shared helper inside each V3 script.
3. Implement “create collection” flow in CollectionUploaderV3:
   - When the checkbox is set, call the management API create-collection endpoint with the fields list above (including types and flags like inject/unique as required by the API).
   - After creation, refresh collections list and select the new collection.
4. Implement “metadata validation” flow in CollectionUploaderV3:
   - On existing collection selection, fetch its schema and compare keys to the required list.
   - If missing/extra keys, block upload and show a detailed error with the expected list and guidance to recreate or adjust the collection.
5. Integrate validation into the upload path so it runs before any batch upload begins and before pairing MD + metadata files.
6. Update docs (top-level only) to mention:
   - The new “Criar nova collection” checkbox and required metadata keys.
   - The blocking behavior when schema doesn’t match.

**Verification**
- Manual: create a new collection from Configurações and confirm fields match the image.
- Manual: select a mismatched collection and confirm upload is blocked with a clear error.
- Manual: select a valid collection and upload to confirm normal flow.

**Decisions**
- Apply only to V3 scripts.
- Use palavras-chave as the canonical metadata field name.
- Use a checkbox + name input for create flow.
- Block upload if schema mismatches.

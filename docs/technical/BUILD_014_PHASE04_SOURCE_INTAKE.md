# Build 014 — controlled Knowledge Pack source intake

## Intake contract

`POST /brands/current/drafts/{draft_id}/sources/upload` is Brand Owner-only and accepts PDF/DOCX multipart uploads. It applies:

- extension and content-signature checks through the existing extraction utility;
- configured byte limit (`MAX_UPLOAD_BYTES`);
- private object key namespace `brand-source-documents/{tenant}/{brand}/{draft}/{source}/...`;
- original SHA-256 binding;
- ClamAV TCP `INSTREAM` scan;
- extraction only when the scan result is `CLEAN`;
- a private extraction manifest with logical text regions, parser status/confidence and bounded warnings.

The API stores new records as `draft`; the response explicitly returns `authoritative: false`. Owner approval and whole-pack publication are still required before the record can become authoritative.

## Malware result state machine

| Scanner result | Stored source state | Extraction | Download / inspect / approve |
|---|---|---|---|
| `CLEAN` | `scan_status=CLEAN` | Runs | Extraction and download available; approval still requires complete text |
| `INFECTED` | `scan_status=INFECTED` | Not run | Blocked |
| `UNAVAILABLE` | `scan_status=UNAVAILABLE` | Not run | Blocked; owner can retry after service recovery |
| `ERROR` / malformed response | `scan_status=ERROR` | Not run | Blocked; owner can retry |

The scanner adapter never maps timeout, refused connection, invalid reply, missing daemon or any other error to `CLEAN`. Source download and extraction routes re-check tenant+brand+draft namespace and original hash. Draft uploaded assets use the same scan states and cannot be previewed or approved unless CLEAN.

## Data handling and bounds

- Original uploaded files are stored privately under opaque application-controlled keys. Browser responses do not include object-storage keys.
- `file_sha256` binds the original bytes. `sha256` binds the retained extracted text when one exists.
- Extracted text retained in the Knowledge Pack is limited to the first 20,000 characters; the manifest records that truncation.
- Extraction manifests expose at most 500 logical regions. Region text is individually bounded; unneeded raw word-level payload is omitted.
- A document with no extractable text or partial parser status cannot be approved as a source of factual evidence.
- The upload route does not fetch external source URIs.
- A live ClamAV daemon and its signature database must be deployed. The Compose service is for development only; scanner protocol tests use a fake socket.

## Version diff contract

`GET /brands/current/versions/compare?from_version_id=...&to_version_id=...` compares only versions belonging to the caller's current tenant and brand. It returns record additions, removals and changed fields with bounded values. Private object-store key fields are redacted, nested keys are redacted and long source excerpts are truncated.

## Provenance mutation guard

The generic section editor cannot set approval metadata or inject storage/scan/extraction provenance. Uploaded-source original hash, storage key, extraction key, parser output and scan result are immutable through the generic JSON editor. An edit to an approved record automatically downgrades that record to `draft`; it must be explicitly re-approved. The dedicated rescan use case can modify only scan/extraction-owned fields.

## Known boundaries

- These controls cover Brand Knowledge source documents and Brand Control Center raster assets. The normal user submission intake path is part of Phase 05 and is not claimed to have malware scanning in Build 014.
- The local SQLite tests do not prove PostgreSQL RLS or lock semantics. The live non-superuser PostgreSQL CI gate remains open.
- The ClamAV protocol adapter has unit coverage, but a live daemon/signature-update integration run remains pending.
- Quarantine retention and automated object cleanup are not yet implemented; private quarantined objects must be handled under the workspace retention policy.
- Owner-defined usage rules (allowed channels, minimum dimensions, clear space, palette constraints and validity windows) remain Phase 04 work.

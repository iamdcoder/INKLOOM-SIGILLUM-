# Apply Build 007 — Brand Control Center and Knowledge Pack lifecycle

Apply this patch to the existing Build 006 `sigillum` project root. It is an additive patch; do not replace your `.env`, `data/`, `.venv/`, `apps/web/node_modules/` or `apps/web/package-lock.json`.

## Apply on Windows PowerShell

From the existing `sigillum` root directory:

```powershell
Expand-Archive `
  "$HOME\Downloads\INKLOOM_SIGILLUM_BUILD_007_PATCH.zip" `
  -DestinationPath . `
  -Force
```

## Backend verification

```powershell
.\.venv\Scripts\Activate.ps1
python -m compileall -q backend\sigillum apps tests scripts
python -m pytest tests -q
```

Expected current result: **40 passed**.

## Frontend verification

```powershell
cd apps\web
npm run lint
npm run typecheck
npm run build
```

This patch updates the Brand Control Center page and global styles. Run all three checks locally before using the new page.

## Start the product

Terminal 1, from repository root:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2, from `apps\web`:

```powershell
npm run dev
```

Sign in with the seeded Brand Owner account configured in `.env` and open Brand Control Center.

## Exercise the lifecycle

1. Select **Create draft**.
2. Choose a Knowledge Pack section.
3. Edit the JSON and select **Save section**.
4. Select **Validate draft** and inspect any validation errors.
5. Select **Publish version** and confirm the publication.
6. Verify the new active version and fingerprint appear in version history.
7. Upload a new submission and inspect its review's Knowledge Pack version/hash.
8. Open an older review and verify its snapshot/hash remains unchanged.

Only the Brand Owner can create, edit, validate or publish. Reviewers and Administrators can inspect published versions without changing them. Creators cannot access management endpoints.

## Important implementation boundary

Build 007 stores tenant-specific pack snapshots in local `data/brand_packs/` directories. It uses immutable version directories, an atomic active pointer and stale-draft checks for this single-host build. It is not a PostgreSQL/object-store distributed adapter. Binary brand asset upload/scanning, guided forms and automated impact re-review are not implemented yet.

# Build 007 — local verification

From the `sigillum` repository root, with the virtual environment active:

```powershell
python -m pytest tests -q
```

Expected current backend result after Build 007: **40 passed** (plus any later tests added in subsequent builds).

Start the API:

```powershell
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

Start the web app in a second terminal:

```powershell
cd apps\web
npm run lint
npm run typecheck
npm run build
npm run dev
```

Sign in as the seeded Brand Owner to access the editor:

- Email: `owner@orbita.demo`
- Password: use the configured local demo password (`SIGILLUM_DEMO_PASSWORD` / `.env`)

Open **Brand Control Center**. Create a draft, select a section, edit its JSON, save the section, validate the draft, inspect validation feedback and explicitly publish. A successful publication increments the pack version. Existing reviews retain their previous fingerprint; new submissions use the newly active pack.

Use a Reviewer or Administrator account to confirm version history is read-only. Use a Creator account to confirm Knowledge Pack management endpoints are denied.

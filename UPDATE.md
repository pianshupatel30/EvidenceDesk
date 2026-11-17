# Open the redesigned EvidenceDesk on Windows

Use a fresh folder so the older bundled sample documents do not remain in the new collection.

1. Click the terminal running your old EvidenceDesk and press **Ctrl+C**. If asked `Terminate batch job (Y/N)?`, type `Y` and press Enter.
2. Download the updated `EvidenceDesk_Project.zip`.
3. In File Explorer, right-click the ZIP and choose **Extract All**. Choose a fresh folder such as `E:\EvidenceDesk_V2`.
4. Open the extracted folders until you see `setup_and_run.bat`, `README.md`, and `documents` together.
5. Double-click **setup_and_run.bat** (Windows may hide the `.bat` extension). Keep the terminal open while it installs packages.
6. Wait for `Uvicorn running on http://127.0.0.1:8000`.
7. Open **http://127.0.0.1:8000** in Chrome or Edge. Press **Ctrl+F5** if the previous design is still visible.
8. Ask `How do I book a workshop?`, then click its source reference.

Future launches: double-click `run.bat` in this new folder.

## What changed

- Charcoal navigation, warm ivory workspace, burnt-orange actions, and lime accents.
- Instrument Serif headings and DM Sans text, bundled locally with their licenses.
- Searchable document library, indexed-passage previews, and drag-and-drop upload.
- Source references open previews; answers have a copy button.
- Separate Evaluation and Activity views with review filtering and measured request data.
- Twelve neutral, fictional arts-centre documents, sixty updated evaluation questions, and a regenerated baseline.

## Keep your own files

Keep your old folder as a backup. Upload any personal documents you want to use through the new app. Do not copy the whole old `documents` or `data` directory into the new folder: doing that brings back older samples and reports. If you previously configured a model, you can copy your private `.env` locally into the new project folder; never upload that file to GitHub.

## Checks

See `reports/BASELINE.md` for the exact automated checks, retrieval measurements, and unverified parts. Visual browser review could not be completed in the build environment.

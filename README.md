# HLB Flow

A local competition prototype for explainable checkout financing. Includes a fictional Nova storefront, Chrome side-panel extension, live Python decision API, bank workspace, a Colab-trained LightGBM model, human review, and simulated payments.

**All people, identity checks, external financial connections, lending decisions, authentication challenges, and payments are synthetic demonstrations. No actual money moves. This is not production banking software.**

## Quick start

Prerequisites: Python 3.11+ with pip/venv, internet for the first dependency installation, and desktop Chrome for the extension. No Node installation or frontend build is required.

Run the appropriate app-only setup script from this directory:

| OS | Command |
|---|---|
| Linux | `bash setup_linux.sh` |
| macOS | `bash setup_macos.sh` |
| Windows PowerShell | `powershell -File .\setup_windows.ps1` |

If your Windows execution policy blocks scripts, run the script in a PowerShell session allowed by your organisation, or use the manual commands below. The script does not weaken the machine's execution policy.

The setup scripts install dependencies, validate the existing `model/` bundle, prepare the extension files, and start the server. **They never train or retrain a model.** They stop if the bundle is absent or its checksum is wrong.

The terminal prints a generated local demo access code. Enter it in the storefront and bank workspace. It is also stored in `runtime/access_code.txt` (excluded from source control). A shared code intentionally allows the customer/officer/presenter demo roles on this loopback-only synthetic environment; this is not a production identity system.

- Storefront: <http://127.0.0.1:8000/>
- Bank workspace: <http://127.0.0.1:8000/bank>
- API reference: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/api/health>

Keep the terminal open. Press Ctrl+C to stop. The launcher refuses to kill another process if port 8000 is occupied.

## Install the extension

1. Run setup and leave the server running.
2. In desktop Chrome, open `chrome://extensions`.
3. Enable **Developer mode**, choose **Load unpacked**, and select this project's `extension/` folder.
4. Pin HLB Flow from the Extensions toolbar menu.
5. On the Nova storefront, choose **Explore financing**, enter the local access code, and select a synthetic customer. This creates a real server-side mock order.
6. Return to the merchant tab and click the HLB Flow extension icon. It reads only the order reference from the supported page.
7. Sign in to the extension with the same code and persona. Consent, choose terms, and request financing.

Chrome requires the user to load an unpacked extension. Setup prepares all files but does not silently change browser security settings or install extensions. Only `http://127.0.0.1:8000/` is a supported merchant origin. `localhost` may serve the app but use **127.0.0.1** for the complete extension demonstration.

The storefront also opens a web financing window for browsers that cannot load extensions. It uses the exact same decision and payment backend; identify it as the web fallback, not an extension test.

## Demonstrate the main flow

1. Open Bank workspace and sign in as **Presenter**. Demo controls → Normal operation.
2. In the storefront, create a VND6 million phone order using Minh (gig worker).
3. In the extension/web fallback, grant scoped data consent, choose six months, submit.
4. In the bank workspace → Applications, select the application. Inspect actual evidence, LightGBM estimate/contributions, affordability, and policy reasons.
5. In the financing panel, review total cost and the full reducing-balance schedule. Accept the offer.
6. Request the demo authentication challenge; type the displayed six-digit code. It is deliberately a synthetic on-screen challenge, not SMS or real multi-factor authentication.
7. Complete simulated payment. The order becomes confirmed and exactly one simulated loan activates.
8. Check the audit trail and metrics. No real payment details are used.

## Demonstrate risk and recovery

Use the Presenter role for fault injection; use Credit officer for review resolution. Switch roles with the workspace button. All historical events remain in the database.

- **Missing transaction evidence:** new request → referral; no model score. Restore Normal operation, switch to Credit officer, add an evidence note and confirm fresh synthetic evidence, then re-evaluate.
- **Identity mismatch:** blocked before scoring. Officer cannot bypass it while the fault remains active.
- **Income-source/model outage:** pending/review, no fabricated score or approval.
- **Affordability stress:** reduced supplemental net income, actual affordability failure, no offer.
- **Payment failure:** no loan activation. Restore Normal operation and retry through a fresh acceptance/challenge.
- **Lost payment response:** unknown status with original reference. Use Check original transaction; do not start another payment.
- **Price change after offer:** Presenter selects an application and changes order price. Existing offer becomes invalid and cannot be accepted/captured. Create a fresh checkout/request.
- **Full refund:** Officer/Presenter can simulate refund on a captured application; payment and loan states reverse and audit history remains.
- **New run:** archives previous applications in history and invalidates pending offers. It never deletes payments or audit records.

## Model and training provenance

`model/` contains:

- `lightgbm.txt`: exported LightGBM booster; loaded as text, no untrusted pickle.
- `manifest.json`: model/feature schema, calibration coefficients, thresholds, source/model checksums, temporal partitions and versions.
- `colab_provenance.json`: actual Colab execution environment, time and notebook link.
- `personas.json`: synthetic demonstration identities linked to selected source records. Each new order is genuinely rescored; no persona-to-decision lookup is used.

Training is an independent workflow in `training/`, not part of setup:

1. Open `training/HLB_Flow_LightGBM_Training.ipynb` in Google Colab.
2. Install notebook dependencies and upload the supplied dataset.
3. Run chronological training, calibration and evaluation.
4. Export `hlb_flow_colab_model.zip`.
5. Import with `.venv/bin/python import_colab_model.py /path/to/hlb_flow_colab_model.zip` (Windows: `.venv\Scripts\python.exe`).

The completed training run used the CSV copy uploaded into Colab, converted to XLSX for the ingestion pipeline. Every one of its 10,000 × 26 values was independently compared with the original workbook; `reports/source_equivalence.json` records this. `data/source.xlsx` and its original `data definition` tab are preserved, with authoritative definitions in `reports/schema.json`. CSV hashes and the generated Colab source-snapshot hash are distinct and labelled in provenance.

Primary model features exclude IDs, date, customer segment, opaque unified credit score, assigned interest rate, approved amount, default target, manual/STP outcomes, abandonment and supplied processing metrics. Transaction visibility gates the model path. Training: April; tuning: May 1–15; calibration: May 16–31; final test: June.

The target is **90+ days past due during loan tenure**, not default within a 90-day horizon. Synthetic labels, label selection (all positive labels occur among declined applications), missing maturity timestamps, and unavailable person linkage prevent real-world credit-risk validation. See the model card in the workspace and `reports/model_report.json`.

Demo assumptions: VND1.6–15m principal, 3/6/9/12-month terms, 20% nominal annual rate, zero fees, 20% stress haircut, 40% stressed debt-ratio ceiling, VND1m residual floor, ten-minute offers. These are illustrative, not bank-approved policy. Disposable income, existing debt, and living expenses are explicitly supplemental synthetic fixtures, not fabricated workbook columns.

## Tests

```bash
.venv/bin/python -m pytest -q
```

Windows: `.venv\Scripts\python.exe -m pytest -q`.

Tests use a disposable database and the imported Colab model; they do not retrain. Coverage includes model feature leakage, explanation reconstruction, schedule rounding, identity/evidence/model failures, affordability, consent, idempotency, concurrent duplicate payments, unknown-status reconciliation, role/ownership enforcement, stale offers, review, refunds, and audit state.

## Manual setup / later starts

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python prepare.py
.venv/bin/python launch.py
```

For later starts, run only `.venv/bin/python launch.py` after dependencies are installed. `FLOW_NO_BROWSER=1` disables automatic browser opening. `FLOW_ACCESS_CODE` optionally supplies a local demo access code; never use a real bank password. `FLOW_RUNTIME` points to a different synthetic database directory.

macOS may require `libomp`; setup installs it using Homebrew when available. Linux may require `libgomp1` (Debian/Ubuntu) or `libgomp` (Fedora). Python itself is a prerequisite; these scripts do not silently install an OS package manager or require system-wide Python changes.

## Repository map

| Folder/file | Purpose |
|---|---|
| `backend/` | FastAPI, SQLite transaction state, LightGBM inference, policy and amortisation |
| `web/` | Storefront, customer financing and bank dashboard; bundled assets, no CDN |
| `extension/` | Manifest V3 side panel; generated UI assets copied from web customer flow |
| `model/` | Already trained Colab model and metadata |
| `training/` | Training source and notebooks; separate from setup |
| `reports/` | Actual data/model evaluation and verification evidence |
| `tests/` | Automated API/model/transaction tests |
| `docs/PRD.md` | Original detailed implementation specification |
| `docs/demo-runbook.md` | Presentation sequence and test boundaries |
| `runtime/` | Generated local database and demo access code, ignored by Git |

## Boundaries

This build uses plain ES modules and CSS instead of React so no JavaScript dependency install/build is required on the presentation machine. It includes no real bank account access, licensed payment rails, actual identity biometrics, real SMS, credit bureau integration, legally binding signing, mobile extension, autonomous model retraining, reusable revolving credit facility, or partial refunds. End-to-end payment integration and all loan ledgers are simulated and labelled. Recorded video/deck creation is separate from this source implementation.

Only loopback binding is supported. Do not expose this demo to the public internet or enter actual customer information. A production pilot requires independently validated models, mature repayment labels, regulated lender/payment integrations, real authentication, bank-approved policy and security review.

## Brand styling

The interface uses HLB blue `#002d62`, red `#ed1c24`, and white, verified against [Hong Leong Bank Vietnam’s official website styles](https://www.hlbank.com.vn/etc/clientlibs/hlb/hlb-header.min.css). Approval and warning colours remain semantic. Decorative slashes were removed from product copy; URLs, paths, and code retain required syntax. The Flow wordmark is a competition concept, not an approved bank identity.

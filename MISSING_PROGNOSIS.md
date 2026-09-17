# Missing-Prognosis Analysis

Why some patients in `stance-dashboard.structured-user-reports` don't have a corresponding doc in the `prognosis` collection — and what (if anything) needs to happen for them to get one.

> Last refreshed: 2026-05-13 ~15:56 UTC, mid-backfill.
> Re-run the diagnostic script (below) for current numbers.

## Snapshot

| Metric | Value |
|---|---:|
| Total patients in `structured-user-reports` | 2,771 |
| Have a prognosis doc | 2,443  (88.2%) |
| Missing prognosis | 329  (11.9%) |

(The "missing" number is dropping in real time — there's a backfill running inside the container at ~35 sec/patient.)

## Why the missing patients are missing

| Count | Bucket | What it means | Fixable by backfill? |
|---:|---|---|---|
| **312** | `first_assessment_ok` | Patient has a `isFirstAssessment: true` record with a populated `diagnosis` field. The pipeline simply never ran for them — most likely because the change-stream listener wasn't running between Mar 24 and May 13. | ✅ **Yes** — clean, full-quality prognosis |
| **17** | `empty_diagnosis` | Patient has a first-assessment record, but the `diagnosis` field is empty or whitespace. The agent can still run, but the prognosis will be generic / low-confidence because its main input is missing. | 🟡 **Partial** — saves a placeholder-quality doc; real fix is to populate `diagnosis` in the source data |
| **0** | `no_first_assessment` | Patient has clinical records but none flagged `isFirstAssessment: true`. The change-stream listener and the batch script both filter on this flag and silently skip. | ❌ Blocked by data shape |
| **0** | `no_clinical_data` | Patient ID exists in the view but `MongoReportsLoader.get_patient_reports()` returns nothing. | ❌ Blocked by data shape |
| **0** | `load_error` | Exception during data load (Mongo error, code bug, etc.). | ❌ Investigate per-case |

## Why this is mostly good news

- **Zero patients are in the bottom three (blocked) buckets.** Every missing patient has at least *some* data and is reachable by the pipeline.
- **95% of the 329 missing will be fully fixed** automatically by the running backfill.
- **5% (the 17 `empty_diagnosis` cases) are a source-data quality issue, not a pipeline issue.** These will still get a doc, but the doc's value depends on someone (clinician?) backfilling the `diagnosis` field in the underlying `reports` collection.

## Example `empty_diagnosis` patients

These got flagged because their first-assessment record exists but has no diagnosis text:

| patient_id | patient_name |
|---|---|
| `69c3c23a3b1ef75a4c750af5` | Minu Margaret |
| `69c9ff3ed39bffb0f5d4697f` | Aadhya p |
| `69cb3083edf88d812cffea59` | Jishnu Somashekar |
| `69ccc2c1d39bffb0f5d8e6c8` | Kruthik Krishna |
| `69d3700603c6d4c932664c8c` | MAVERICK Cricket Academy ← looks like an org, not a person; probable data-entry error |

For the full list, run the script with `--csv`.

## What caused the gap in the first place

Brief root-cause summary (so this analysis isn't read in isolation):

1. The prognosis pipeline relies on a **MongoDB change-stream listener** that fires when records change in the `reports` collection.
2. The listener was off between **2026-03-24** (last successful run) and **2026-05-13** (today's fix). Triggers:
   - Service was restarted on **Apr 23**, but `AUTO_START_CHANGE_STREAM=true` wasn't set in the env, so the listener didn't auto-start.
   - The `.env` file was missing from the EC2 entirely, so even the manual start endpoint would have failed (Mongo was hitting the localhost fallback).
3. Today's fix: env restored on the box, listener wired to auto-start, app containerized so the env is durable. The 329 missing are the population that *would have been* processed during that window had the system been healthy.

## Diagnostic script

Permanent location: `backend/scripts/categorize_missing_prognosis.py`

It compares patient IDs from `structured-user-reports` against `prognosis.patient_id` and classifies each missing patient by what's actually wrong with their source data.

### Run it (anytime, any frequency — read-only against Mongo)

```bash
ssh -i deploy/prognosis_classifier.pem \
  ubuntu@ec2-3-110-133-84.ap-south-1.compute.amazonaws.com

# Human-readable summary
docker exec prognosis-api python3 /app/backend/scripts/categorize_missing_prognosis.py

# Or with per-patient CSV detail
docker exec prognosis-api python3 /app/backend/scripts/categorize_missing_prognosis.py --csv > missing.csv
```

### What the summary looks like

```
Patient prognosis coverage  (stance-dashboard)

  Total patients in structured-user-reports : 2771
  Have prognosis doc                         : 2443  (88.2%)
  Missing prognosis                          : 329  (11.9%)

Why missing patients have no prognosis:

  [OK   ]  312  Ready — backfill will fix                     ****************************************
  [WARN ]   17  Has first-assessment but diagnosis empty      *****************
  [BLOCK]    0  No isFirstAssessment=true record
  [BLOCK]    0  No clinical data at all
  [ERROR]    0  Exception during data load
           329  total
```

## When you'd want to re-run this

- After the current backfill completes (~3 hours from 15:43 UTC, so ~18:45 UTC), to confirm only the `empty_diagnosis` group remains.
- Weekly, as a sanity check that the change-stream listener is keeping up with new patients.
- After clinical data cleanup (filling in missing `diagnosis` fields), to confirm those patients can now be processed cleanly — and to get a worklist to feed back into the backfill.

## How to clear out the remaining `empty_diagnosis` cases

Two options, depending on policy:

1. **Source-data fix (preferred):** populate `diagnosis` in the underlying `reports` collection for the 17 patients, then trigger:
   ```bash
   docker exec prognosis-api python3 LLM/prognosis/push_prognosis_to_mongo.py --patient <id>
   ```
   for each, to produce a normal-quality prognosis.

2. **Accept placeholder docs:** let the backfill run them anyway — they'll get a generic Tier 3 / "needs more data" prognosis. Useful only if downstream consumers tolerate low-confidence entries.

## Useful related commands

```bash
# How many prognosis docs exist right now?
docker exec prognosis-api python3 -c "
import os; from pymongo import MongoClient
db = MongoClient(os.getenv('MONGO_URI'), tlsAllowInvalidCertificates=True, tlsAllowInvalidHostnames=True)[os.getenv('MONGO_DB')]
print(db.prognosis.count_documents({}))
"

# Live tail of the backfill
docker exec prognosis-api tail -f /tmp/backfill.log

# Confirm the change-stream listener is up (so new patients get auto-processed)
curl -s http://localhost:8013/api/change-stream/status
```

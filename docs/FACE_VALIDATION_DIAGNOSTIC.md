# Enrollment photo diagnostic

Run from the repository root with the project virtual environment. Enrollment
and Vision must be ready at their configured HTTPS URLs. Use one real person for all images.

```powershell
& .\venv\Scripts\python.exe scripts\diagnose_enrollment_faces.py --capture --output-dir logs\face-validation --person-label person-1
```

The existing `test.py` webcam preview prompts for front, small left/right turns
with both eyes visible, and slight up/down poses. SPACE captures; ESC cancels.
Photos, a replayable manifest, errors, timing, and a report are temporary by default.
Add `--retain-artifacts` to keep them in the ignored directory. Reports omit vectors and credentials.

To rerun a retained dataset, pass its manifest to `--manifest` instead of
`--capture`. CSV columns are `angle,path`; paths may be relative to the manifest.
Supply 5-10 distinct real images covering front, left, right, up, and down.

With Enrollment also running, exercise the actual background validation and
combined numbered retake flow:

```powershell
& .\venv\Scripts\python.exe scripts\diagnose_enrollment_faces.py --parallel-capture --output-dir logs\face-validation --person-label person-1
```

Add `--bad-photo-number 2` to request a turned-away initial photo at that number.
The retake uses ordinary capture guidance. Every attempt and its REST result is
retained only with `--retain-artifacts`, including failed frames. Ordinary diagnostics do not enroll users.

`--reproduce-enrollment-error` also records five real microphone clips (interactive
terminal required) and submits a confirmed rejected five-photo manifest through
test.py's actual enrollment REST upload. Use an isolated Enrollment store for
this mode. It retains the response and voice clips. The bad photo should prevent
voice embedding or persistence; unexpected success requires inspection and API cleanup.

Both the diagnostic and production prevalidation call `/enrollment/validate-photo`.
Enrollment owns `PhotoValidation`, which delegates to its existing Vision REST client.
Final enrollment uses that same server-side check; only safe metadata is returned to clients.
The short-lived, bounded server cache keys successful checks by exact image
content, so final enrollment can reuse the vector without trusting client vectors.
Expired/evicted results are rechecked by the same path. Enrollment completion or
failure clears its validation cache. Configure cache retention through
`PHOTO_VALIDATION_CACHE_TTL_SECONDS` and `PHOTO_VALIDATION_CACHE_MAX_ITEMS`.

For a full console enrollment with retained evidence:

```powershell
& .\venv\Scripts\python.exe test.py --enrollment-evidence-dir logs\face-validation
```

Evidence is private biometric material: do not commit it. Retain the reference
photos/reports needed for reruns; remove obsolete diagnostic runs deliberately.
A few images from one person demonstrate that case only, not population-level
pose accuracy. Vision's existing inference concurrency limit is unchanged;
background requests overlap user capture, but inference may still be serialized.

`--manifest <passing-five-photo-manifest> --benchmark-background` replays those
real frames using their original capture timestamps and the actual background
REST flow. It records sequential versus background timing and detects unexpected
retakes. This is a pacing replay, not a second live-camera measurement. Sequential
REST checks populate Enrollment's cache: subsequent replay may reuse them, so its
numbers must not be presented as an uncached speedup benchmark.
# Hardening contract

Diagnostics now call authenticated HTTPS `POST /enrollment/validate-photo`, exactly
like capture orchestration. They do not import Enrollment/Vision internals.
Success metadata is `valid, face_detected, confidence, embedding_generated, reason`.
Failures retain the existing HTTP error envelope, with the same metadata under
`error.validation`. Reasons distinguish no face, invalid image, model readiness,
inference failure and request failure. Internal exception details stay server-side.

Retention is **off by default**. Add `--retain-artifacts` explicitly to keep the
run; otherwise its temporary directory is deleted on exit. `--output-dir` and
`test.py --enrollment-evidence-dir` accept only descendants of the ignored
`logs/face-validation` directory. Retained contents include real private photos,
redacted REST reports, timings and (only in the explicit error-reproduction mode)
microphone clips. Remove a specifically inspected run directory with PowerShell
`Remove-Item -LiteralPath <absolute-run-directory> -Recurse` when no longer needed.
Do not remove the whole evidence tree while retained evidence is still needed.

The success cache retains only the exact embedding and face metadata, not raw
images. Its key is `(PHOTO_VALIDATION_VERSION, SHA256(image bytes))`; TTL and maximum
entries are `PHOTO_VALIDATION_CACHE_TTL_SECONDS` and `PHOTO_VALIDATION_CACHE_MAX_ITEMS`.
Deployment must bump `PHOTO_VALIDATION_VERSION` when detector, model, preprocessing
or validity policy changes (default `opencv-facenet-validation-v1`). Restart also
clears this in-memory cache. Worker concurrency is `PHOTO_VALIDATION_CONCURRENCY`
(default two). Each round drains every future before a retake begins: old attempts
cannot replace newer photos, and accepted slot order never changes.

Use small turns, mostly frontal, both eyes visible. Strong side profiles remain
a known OpenCV frontal-detector limitation, not a threshold-tuning target.

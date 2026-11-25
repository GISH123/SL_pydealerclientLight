# SL pydealerclientLight

Public sanitized handoff repository for the current `video2026 / pydealerclientLight` source.

This repository is a cleaned GitHub handoff copy. Local runtime configuration, certificates, binaries, and build outputs should not be committed.

---

## Current Status

This version is based on the current `video2026 / pydealerclientLight` source and replaces the older archived GitHub version.

Main runtime direction:

- The client no longer performs local card model inference.
- Card recognition is delegated to an external model HTTP API.
- The client handles video capture, ROI cropping/preprocessing, round state, dispatch logic, result caching, CSV/image output, and HTTP/socket control flow.
- BAC and BALL3-related workflows are included.
- HTTP/HTTPS control endpoints are available for mock dealer / integration testing.

---

## Verified Build Environment

Verified on 2026-07-04 with a fresh conda environment:

```powershell
conda create -n pydealerlight_py31113 python=3.11.13 -y
conda activate pydealerlight_py31113

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Confirmed:

```text
Python 3.11.13
basic imports OK: cv2, numpy, requests, twisted
python -m compileall -q . passed
```

Do not use Python 3.14 for this project. The pinned dependency set is intended for Python 3.11.x.

---

## Requirements Notes

`cryptography` is required by `generate_https_cert.py`.

The PyInstaller spec calls `generate_https_cert.py` during build to generate HTTPS certificate/key files for the packaged release.

Expected local generated files:

```text
server.crt
server.key
build/
dist/
```

These files are local build/runtime artifacts and should not be committed.

---

## Build EXE

From the repository root:

```powershell
conda activate pydealerlight_py31113
python -m PyInstaller --clean --noconfirm .\pydealerLight_httpapi.spec
```

Verified build result on 2026-07-04:

```text
PyInstaller successfully generated:
dist\pydealerLight_httpapi_v1_0_46\pydealerLight_httpapi_v1_0_46.exe
```

The build also copied `version.txt` to the dist root.

---

## Runtime Configuration

The following files are local runtime files and are intentionally not committed:

```text
config.xml
models/videolist.xml
```

Use these sanitized examples as templates:

```text
config.example.xml
models/videolist.example.xml
```

Before running the EXE, place local runtime copies beside the EXE:

```text
dist\pydealerLight_httpapi_vX_Y_Z\
鈹溾攢 pydealerLight_httpapi_vX_Y_Z.exe
鈹溾攢 config.xml
鈹斺攢 models\
   鈹溾攢 videolist.xml
   鈹斺攢 position XML files
```

The runtime `config.xml` selects the active `vid`. The runtime `models/videolist.xml` maps that `vid` to:

- game type
- stream/video source
- position XML
- expected video width/height
- model engine API URL
- skip/frequency settings

---

## Smoke Test Result

A packaging smoke test was performed on 2026-07-04.

The first EXE run started successfully and initialized:

```text
read config.xml
read models/videolist.xml
read position XML
started BALL3 HTTP service
started HTTP server on 127.0.0.1:1234
started HTTPS server on 127.0.0.1:1235
loaded bundled server.crt/server.key
```

It exited because the local computer could not reach the internal RTMP stream configured in the runtime `models/videolist.xml`. OpenCV reported stream width as `0.0`, causing the expected width/height mismatch check to stop the program.

A second smoke test replaced the dist runtime stream with a local dummy `3840x2160` video. Result:

```text
PASS: EXE is still running after 20 seconds.
```

Conclusion:

```text
Build OK.
EXE startup OK.
HTTP/HTTPS service startup OK.
Runtime does not immediately crash when given a reachable video source.
Prediction/model output was not tested in this smoke test.
```

---

## HTTP / HTTPS Control API

The application exposes HTTP/HTTPS control endpoints used by mock dealer and integration testing.

Typical endpoints:

```text
/start_predict
/dispatch_index
/save_result
/stop_predict
```

Default verified startup ports from the smoke test:

```text
HTTP  : http://127.0.0.1:1234
HTTPS : https://127.0.0.1:1235
```

The actual ports are controlled by local `config.xml`.

---

## BAC Runtime Notes

BAC-related changes in the current source include:

- BAC 1 through 6 index dispatch support.
- Independent active index list handling in `DataManager`.
- Result is sent only after an index reaches `detecttimes`.
- `/start_predict`, `/dispatch_index`, `/save_result`, and `/stop_predict` control flow.
- Runtime config logging at startup.
- BAC ROI preprocessing via `<bacPreprocess ... />`.
- Optional ROI resize before sending to the external model API.
- Accepted prediction image saving.
- Original ROI crop saving under `predict_images/<YYYY-MM-DD>/original_crop/`.
- Final result row caching and save-result flow.
- STOP fallback save when pending final rows exist.
- Live stream stall timeout and reopen cooldown config.
- `sys.excepthook` / `threading.excepthook` logging for uncaught exceptions.

---

## BALL3 Runtime Notes

BALL3-related source is included for the current video2026 flow.

Included tools/files include:

```text
ball3_http_service.py
ball3_http_integration_test.py
```

The BALL3 HTTP service is started in threaded mode during runtime.

---

## J20 BAC UAT

- [J20 BAC UAT Deployment Operator Guide](doc/J20_UAT/J20_BAC_Deployment_Operator_Guide.md)
- [J20 BAC UAT Deployment Checklist](doc/J20_UAT/J20_BAC_Deployment_Checklist.md)

---

## Repository Hygiene

Do not commit local config, secrets, certificates, binaries, or build outputs.

Intentionally ignored / removed from Git:

```text
config.xml
models/videolist.xml
doc/model_B04/videolist.xml
server.crt
server.key
*.key
*.crt
*.pem
*.p12
*.pfx
*.exe
*.dll
*.pyd
*.so
*.zip
*.7z
*.bundle
build/
dist/
logs/
log/
csv/
predict_images/
audit_images/
temp_folder_for_big_pic/
__pycache__/
```

Previously tracked binary/runtime artifacts removed during this handoff cleanup:

```text
ftp/ImageUploader.exe
doc/model_B04/videolist.xml
config.xml
models/videolist.xml
```

---

## Final Git Safety Checks Before Commit

Run these before pushing to GitHub:

```powershell
git status --short

git ls-files | Select-String -Pattern '(^|/)(server\.key|server\.crt|\.env|config\.env|config\.xml|videolist\.xml)$|\.zip$|\.7z$|\.exe$|\.dll$|\.pyd$|\.bundle$'

Run a staged sensitive-value scan before commit. Do not commit internal IPs, credentials, certs, binaries, or local runtime configs.
```

Expected:

```text
git ls-files check: no output
git grep check: no real credentials/internal IPs
```

A placeholder line like this is acceptable:

```xml
<ftp host="FTP_HOST" port="21" password="FTP_PASSWORD" user="FTP_USER" />
```

---

## Legacy Notes

This repository originated from older `pydealerclientLight` / `PyDealerClient` work.

Older functionality included:

- live video sampling
- socket communication with dealer
- local image recognition model flow
- snapshot image saving and optional FTP upload
- CSV/log outputs
- Baccarat and related game variants

The current handoff version focuses on the newer video2026 HTTP/API-based flow.


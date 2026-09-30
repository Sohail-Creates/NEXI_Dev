# Vision Service Architecture — observed 2026-09-30

This is a source-and-live-state audit, not a target design. Runtime calls were made against the stack already listening on ports 8000–8006; no service code, configuration, or harness code was changed. The checked-in `docs/openapi/vision.json` and live `GET /openapi.json` had the same 11 paths and methods. The live OpenAPI title/version also matched the checked-in document. Responses below are abbreviated only where a large embedding or HTML/MJPEG body would add no useful information; field names, shapes, status codes, and the measured values are retained.

## 1. Overview

Vision is the HTTPS service on port **8001** (`https://localhost:8001`) for camera-backed face detection/FaceNet embeddings and YOLO object detection. Camera ownership is external: Vision obtains camera leases from Central’s resource authority, and Vision does not own or persist the camera device. TLS launch commands are in [COMMANDS.txt](COMMANDS.txt); the repository does not currently contain `run.txt` or a root `ARCHITECTURE.md` with separate certificate-setup instructions.

Live identity: `GET /` returned service `Vision Service`, version `4.0.0`, status `operational`; `GET /health` returned HTTP 200 with camera `available`, face model `loaded`, OpenCV `4.8.0`, and emotion detection `disabled`. The listener was PID 9272, whose executable path was the system Python 3.11 installation rather than `02_vision_service/venv`; the live process’s full command line was not readable in this environment. The service-local venv has the versions listed in section 2, but it cannot be assumed that this listener used those exact installed packages.

## 2. Models actually in use

### Face embedding model

- **Name/runtime:** DeepFace `Facenet` (FaceNet-128d); `deepface==0.0.98`, `tensorflow==2.20.0`, `tf-keras==2.20.1`, `keras==3.15.1` are pinned in Vision’s requirements. The service venv reports those exact package versions.
- **Weights:** `_MODEL_CACHE_ROOT` defaults to `02_vision_service/models`; `DEEPFACE_HOME` is set there unless already set. The present file is `02_vision_service/models/.deepface/weights/facenet_weights.h5`, **92,190,816 bytes**. It is downloaded by DeepFace if absent; the file was already present for this pass.
- **Input/preprocessing:** camera frames are OpenCV BGR arrays; uploaded images are decoded with `cv2.imdecode(..., IMREAD_COLOR)`, also BGR. DeepFace’s OpenCV detector extracts/aligned face crops; DeepFace converts the crop to RGB for extraction and the representation path converts it back to BGR, resizes to **160×160**, and applies DeepFace’s `base` normalization. No route-level resize is done before face detection. These details are in `services/face_detector.py`, the route code, and the installed DeepFace `modules/representation.py`.
- **Output:** the model is 128-dimensional. On the HTTP wire the schema is `embedding: number[]`; Python/Pydantic expose ordinary floats, not a typed-array/dtype contract. The endpoint does not promise a decimal precision. The live response had 128 serialized values and `embedding_model: "Facenet"`.
- **Loading/failure:** `app.py` calls `load_model_with_retry` during lifespan startup. The live health route reported it loaded. A separate startup attempt during this pass measured 9.707 seconds between the FaceNet “Loading” and “Successfully loaded” log timestamps; that attempt later failed to bind because port 8001 was occupied, so this is a measured cold model-load attempt, not a clean service-start duration. If loading returns false, startup continues with `face_model_loaded=false`; detailed health degrades. Missing DeepFace during a face request maps to 503, but other inference failures can be hidden as an empty face list or a zero embedding (section 10).
- **Execution:** CPU. The launch log reported TensorFlow’s CPU feature guard and no GPU/device selection is configured in Vision’s model call. No claim is made that a GPU path was tested.

### Face detector backend

- **Name/version:** default `opencv`, using the DeepFace OpenCV Haar cascade backend with `opencv-python==4.8.0.76` (live `/health` reported OpenCV `4.8.0`). This is distinct from the FaceNet embedding model.
- **Files:** the installed frontal cascade is `02_vision_service/venv/Lib/site-packages/cv2/data/haarcascade_frontalface_default.xml`, **930,127 bytes**; OpenCV’s eye cascade is also loaded for eye-based alignment. No separate cascade download occurs in the Vision route.
- **Input/output:** BGR image; DeepFace uses `detectMultiScale3`, then emits integer `x`, `y`, `w`, `h` and a confidence derived from OpenCV reject levels. DeepFace rounds that confidence to two decimals. The code does not clamp it to a documented `[0,1]` range. When no face is found and `enforce_detection=False`, DeepFace deliberately returns a whole-image region with confidence `0`; Vision currently treats that as a detected face and embeds it.
- **Loading/failure:** the DeepFace OpenCV backend is constructed lazily by DeepFace on detection. DeepFace’s installed OpenCV adapter catches its own `detectMultiScale3` exception with a bare `except: pass`; Vision’s `detect_faces_deepface` also catches all exceptions and returns `[]`.
- **Execution:** CPU/OpenCV; no GPU path.

### Object detector

- **Name/version:** `yolov8n` via `ultralytics==8.0.196`; the local checkpoint `02_vision_service/yolov8n.pt` is **6,549,796 bytes**. Its checkpoint metadata identifies the model as YOLOv8n and records the training/export package version as `8.0.0.dev0`; runtime package version is `8.0.196`.
- **Loading path:** during startup, `app.py` checks object-detector availability if enabled; this triggers lazy construction/loading. `ResourcePool` first looks for `02_vision_service/models/yolov8n.pt`. That file is absent in this checkout. It then passes no explicit model path, and `ObjectDetector` calls `YOLO("yolov8n.pt")`, which resolves relative to the process working directory or causes Ultralytics to attempt a download. The actual local weight is at the Vision service root, so the normal `Set-Location "$repo\02_vision_service"` launch makes it discoverable by that fallback. A launch from the repository root during this pass tried to download and failed because the environment was offline. This is a real working-directory fragility; the normal COMMANDS.txt launch uses the service directory.
- **Input/preprocessing/output:** OpenCV BGR `numpy.ndarray`; Ultralytics performs its own model preprocessing (the Vision wrapper does not resize or specify `imgsz`). The wrapper reads xyxy boxes, truncates coordinates to integers, maps them to `{x,y,width,height}`, emits class ID/name and confidence, and drops confidence below `0.5`. Output confidence is the model’s scalar score; there is no object embedding output.
- **Loading/failure:** if detector loading fails, the pool returns `None` and complete analysis silently substitutes an empty detection list. If `detect()` itself fails, it returns `None`; the route then calls `.get()` on `None` and returns a generic 500. The live service produced a complete-analysis response with one object on one call, which proves that its object path was active on that call, but another call returned HTTP 500 (section 4/10).
- **Execution:** CPU in this setup; the wrapper does not select a device. No GPU use was observed.

## 3. Embedding storage and wire formats

Vision contains no user database, enrollment store, or persistence call for face images/embeddings. It returns face embeddings to the caller in the HTTP JSON response; any durable storage is owned by another service. Vision does persist/cache **model weights**, which is not user image/embedding storage. Camera frames are processed in memory by route code. Multipart upload handling uses FastAPI/Starlette `UploadFile`; its parser may spool an upload to a temporary file according to framework behavior, but Vision has no explicit image-save or retention code.

Face response JSON uses `status`, `timestamp`, `frame_width`, `frame_height`, `faces_detected`, and `faces[]`; each face has `face_id`, `bounding_box:{x,y,width,height}`, `confidence`, `embedding:number[]`, and `embedding_model`. Real live camera response excerpt:

```json
{
  "status": "success",
  "frame_width": 640,
  "frame_height": 480,
  "faces_detected": 1,
  "faces": [{
    "face_id": 0,
    "bounding_box": {"x": 0, "y": 0, "width": 639, "height": 479},
    "confidence": 0.0,
    "embedding": "<128 real JSON numbers; omitted here>",
    "embedding_model": "Facenet"
  }]
}
```

That response is **not evidence of a face**: it is a whole-frame, zero-confidence fallback candidate. It was returned by the actual camera route during this pass.

No object/visual embedding is generated or returned by the current mounted routes. The `feature_extractor.py` module computes handcrafted color/size/shape/texture descriptors and `instance_tracker.py` can compare them, but neither is called by a route or by the mounted YOLO path. The real object result format is metadata only: `class_id`, `class_name`, `confidence`, and `bounding_box`.

Real uploaded-image request used this pass: `POST /api/v1/detect/faces/upload`, multipart `file=neutral-fixture.png` (an in-memory 320×240 gray PNG), with `X-NEXI-Service-Token`. The HTTP 200 body had `status:"success"`, `frame_width:320`, `frame_height:240`, `faces_detected:1`, and one full-image box with confidence `0.0`, `embedding_model:"Facenet"`, and 128 embedding numbers. This is also a concrete example of the zero-confidence fallback, not a valid face test.

## 4. Complete endpoint inventory

Auth means the `X-NEXI-Service-Token` internal credential enforced by `InternalRouteAuthMiddleware`. `/` and `/health` are not in its protected prefixes. OpenAPI request/response schemas are from the current live `/openapi.json`, cross-checked against the checked-in `docs/openapi/vision.json`. Protected routes were called with the internal credential. “Not exercised” is explicit: this was a read-only documentation task, so the mutating pause/resume calls were not made; the unbounded stream was sampled then closed.

| Method | Path | Request shape | Auth | Response / live proof | Current status |
|---|---|---|---|---|---|
| GET | `/` | No body/params | No | HTTP 200 JSON: `{service,version,status,features,timestamp}`; actual values included `Vision Service`, `4.0.0`, `operational`. | **WORKING** — real call HTTP 200. |
| GET | `/health` | No body/params | No | HTTP 200 JSON: `{status,camera,face_model,opencv_version,emotion_detection,timestamp}`; actual: `healthy`, `available`, `loaded`, `4.8.0`, `disabled`. | **WORKING** — real call HTTP 200. Note: performs an actual camera availability check, not a passive probe. |
| GET | `/api/face-data` | No body/params | Yes | HTTP 200 JSON: `{face_count:0,primary_emotion:null,confidence:null,timestamp:...}`. | **DEGRADED** — live route is a hard-coded empty placeholder, not current real-time state. |
| POST | `/api/v1/detect/faces` | Optional query: `detector_backend` (default `opencv`), `model_name` (default `Facenet`); no body | Yes | HTTP 200 JSON `FaceDetectionResponse`; live camera returned 640×480 and one full-frame face candidate at confidence 0.0. | **DEGRADED** — request works, but current no-face fallback is counted and embedded as a face. |
| POST | `/api/v1/detect/faces/upload` | Multipart required `file`; same optional query params | Yes | Real in-memory PNG upload HTTP 200; JSON shape same as face detection; it produced a full-image zero-confidence candidate. | **DEGRADED** — same false-candidate/fallback behavior. |
| POST | `/api/v1/analyze/complete` | Optional query: `detector_backend`, `model_name`; no body | Yes | `CompleteAnalysisResponse`: `{status,timestamp,frame_width,frame_height,faces_detected,faces,objects_detected,objects}`. A live call returned HTTP 200 with one object; another returned HTTP 500 envelope `INTERNAL_SERVER_ERROR: Complete analysis failed`. | **DEGRADED** — inconsistent real results; cause is not exposed by the response. |
| GET | `/api/v1/frame` | Required query `lease_id` | Yes | Real call with an invalid lease returned HTTP 409: `Delegated VIDEO_CALL camera lease is not active`. It did not open the camera. | **WORKING** — invalid-lease rejection confirmed; valid lease capture was not tested because it requires an active call lease. |
| POST | `/camera/pause` | No body/params | Yes | Source/OpenAPI shape: `{status:"paused",message:"Camera paused"}`. **Not called** because it changes process state. | **NOT LIVE-VERIFIED** — read-only constraint prevented exercising it. |
| POST | `/camera/resume` | No body/params | Yes | Source/OpenAPI shape: `{status:"active",message:"Camera resumed"}`. **Not called** because it changes process state. | **NOT LIVE-VERIFIED** — read-only constraint prevented exercising it. |
| GET | `/live` | No body/params | Yes | Without credential it returned 401; with internal credential it returned HTTP 200 `text/html; charset=utf-8`. | **WORKING** — auth behavior and successful HTML response confirmed. |
| GET | `/stream` | No body/params | Yes | HTTP 200 `multipart/x-mixed-replace; boundary=frame`; a client sampled ten frames and closed the stream. | **WORKING** — real stream confirmed, not claimed as a sustained benchmark. |

Live OpenAPI and checked-in OpenAPI both expose exactly the 11 method/path combinations above. No unlisted object-upload or object-embedding endpoint exists in the current Vision OpenAPI.

## 5. Camera and resource lifecycle

For a normal camera operation, `ResourcePool.get_camera()` serializes local access with `_camera_lock`, asks `CameraResourceClient` to POST Central `/resources/request` for `resource_type=camera`, `service_name=vision_service`, and `priority=BACKGROUND`, then POSTs `/resources/acknowledge/{lease_id}`. Only after the acknowledged grant does it resolve/open the physical device. In `finally`, it closes the device and releases the Central lease. The client supplies its PID, start time, and configured port so Central can verify process identity when possible.

The camera watchdog checks lease activity every 250 ms. When a lease is no longer active, it closes the camera and acknowledges release; a forced-close timer retries only within Vision’s own process. A denial/unreachable authority fails the camera request. Camera lock timeout, failed open, and failed close are surfaced as exceptions to callers.

Vision holds **no camera lease while idle**. During this pass Central’s resource-status endpoint showed camera `{is_available:true, holder:null, queue:[]}` before and after a short stream. `/health` itself temporarily opens/releases the camera as its availability check.

Shutdown releases the local camera object and clears model references. `ResourcePool.shutdown()` does **not** explicitly release `_camera_client.lease_id`; normal route cleanup releases it, but an abnormal shutdown while a lease is active relies on Central’s lease timeout/liveness handling. This is a cleanup fragility, not proof that a stale lease occurred in the live check.

Forced preemption is cooperative polling, not an application resume protocol: Central marks the lease revoking; Vision notices via its status polling, closes/releases the camera, and the current request/activity is interrupted. No paused request state is saved or restarted. Video-call routes reserve camera only; Vision’s resource client has no microphone lease.

The `/camera/pause` flag is separate from Central leases. It is checked only by the MJPEG generator; it does not close/release the camera, and `generate_frames()` loops with `continue` while paused (no sleep), so a paused stream can busy-spin while still holding the lease.

## 6. Request-handling flow

For `POST /api/v1/detect/faces/upload`, the route validates the requested backend/model, requires DeepFace, reads the multipart upload, decodes it to OpenCV BGR using `cv2.imdecode`, then calls `detect_faces_deepface(img, detector_backend)`. That calls `DeepFace.extract_faces(..., enforce_detection=False, align=True)`. Each face object goes to `process_face`, which reads the detected area/confidence and calls `DeepFace.represent` on the cropped face. The returned values are validated/coerced into Pydantic `FaceData`, then serialized as JSON. There is no explicit dimension cap or resize before detector invocation.

The live request body was the in-memory 320×240 gray PNG described in section 3. Its response was HTTP 200 with a full-image box, confidence 0.0, and 128 values. This follows DeepFace’s `enforce_detection=False` dummy-region behavior and shows that the route’s `status:"success"` does not mean a face was confidently detected.

For camera detection the same face pipeline is fed a frame from `_resource_pool.get_camera()`. For complete analysis, after that face path the route gets the YOLO detector and runs it on the original BGR frame. It is a combined endpoint; there is no separately callable object-only or object-upload endpoint.

## 7. Code structure

| File | Actual responsibility |
|---|---|
| `02_vision_service/main.py` | Adds repository root to import path and runs Uvicorn with configured TLS. |
| `02_vision_service/requirements.txt` | Pinned service dependencies (inventory in section 12). |
| `02_vision_service/yolov8n.pt` | Local YOLOv8n checkpoint; the loader’s preferred `models/yolov8n.pt` path does not point here. |
| `02_vision_service/tests/test_vision.py` | Older integration script; it targets plaintext HTTP and expects emotion fields that current routes do not produce. |
| `vision_service/__init__.py` | Package metadata and app re-export; its `__version__="1.0.0"` disagrees with FastAPI/root endpoint `4.0.0`. |
| `vision_service/app.py` | Middleware/router installation, model startup, ResourcePool initialization and shutdown. |
| `vision_service/config.py` | Environment-backed model, camera, host, and URL values; creates DeepFace cache directory at import. |
| `vision_service/models.py` | Pydantic request/response model declarations; several declarations are not used by mounted routes. |
| `vision_service/routes/__init__.py` | Imports the four route modules. |
| `vision_service/routes/health.py` | Root, detailed health, and currently stubbed face-data endpoint. |
| `vision_service/routes/detection.py` | Camera/upload face detection, combined analysis, delegated call-frame capture. |
| `vision_service/routes/streaming.py` | MJPEG generator and embedded HTML live page; it has a separate inline DeepFace call. |
| `vision_service/routes/camera.py` | Toggles the streaming pause boolean; does not itself acquire/release the camera. |
| `vision_service/services/__init__.py` | Re-exports face helper functions and ResourcePool. |
| `vision_service/services/camera_client.py` | Central resource request/acknowledge/status/release HTTP client. |
| `vision_service/services/camera_devices.py` | Camera enumeration, platform backend choice, selection, and OpenCV open helper. |
| `vision_service/services/face_detector.py` | DeepFace load/retry, detector/model validation, face extraction and embedding conversion. |
| `vision_service/services/object_detector.py` | YOLO loading, one-image inference and result mapping; has an unused sequential batch wrapper. |
| `vision_service/services/resource_pool.py` | Camera locking, lease lifecycle/watchdog, lazy YOLO object. |
| `vision_service/services/feature_extractor.py` | Handcrafted image descriptors; no in-service callers were found. |
| `vision_service/services/instance_tracker.py` | In-memory visual-instance matching; no in-service callers were found. |
| `vision_service/services/__pycache__` / `utils/__init__.py` | Bytecode/runtime package artifacts and empty utility namespace; no Vision route logic. |

## 8. Performance characteristics (measured 2026-09-30)

**Environment:** Windows 10.0.19045, Intel Core i5-7200U CPU @ 2.50 GHz. The live listener PID 9272 reported **453,464,064 bytes working set** (about 432.5 MiB) and **1,165,225,984 bytes private memory** when sampled after models were warm. This is a process measurement, not an isolated model allocation. The live process was already running; its original startup duration could not be recovered.

| Operation | Samples from this pass | What the number means |
|---|---|---|
| Face detection `POST /api/v1/detect/faces` | 1.696 s, 2.234 s, 2.290 s; mean **2.073 s** | Full HTTP request wall time, including lease/device open/read/release and inference; not pure neural-network time. Frame size 640×480. Responses repeatedly had a zero-confidence whole-frame face candidate. |
| Combined `POST /api/v1/analyze/complete` | 2.948 s, 3.365 s, 3.320 s; mean **3.211 s** on successful calls | Full combined face+object request wall time. A later call returned 500 and is not included in the successful mean. The API provides no object-only latency, so a separate object-inference number cannot be measured honestly through the current public endpoint. |
| MJPEG `/stream` | Ten frames in 3.897 s = **2.57 observed frames/s** | Short sample including connection/startup overhead; not a sustained FPS benchmark. Stream was closed and camera was idle afterward. |
| FaceNet cold load | **9.707 s** from startup logs | Direct model load duration in a second local app initialization attempt; it successfully loaded FaceNet, but the server then failed to bind because the existing Vision process owned port 8001. Not a clean end-to-end startup time. |
| YOLO cold load | **Not measured** | The second initialization attempt ran from repository-root working directory, failed to resolve the local checkpoint through the intended service-directory fallback, and could not download while offline. The existing live route did return a detection once, proving the live object path was active then, but its startup timing is unavailable. |

No camera or embedding payload was written by these measurements. An object-only latency or representative image benchmark would require a new endpoint, instrumentation, or direct internal invocation; none was added for this read-only pass.

## 9. Scalability assessment

Camera operations are serialized in one Vision process by `_camera_lock`; Central also coordinates leases across services/processes. Two camera-based requests therefore cannot use the physical camera concurrently. Upload-based face requests do not acquire the camera lock, but their route functions are `async` while performing synchronous image decode and TensorFlow/DeepFace inference without `await` or thread offload. That blocks the event loop in a single worker and limits concurrent HTTP handling. YOLO initialization is locked, but inference itself has no Vision-side inference lock.

Measured bottlenecks on this machine are CPU-bound inference plus camera open/read/release overhead; warm end-to-end face calls averaged about 2.07 s, combined calls about 3.21 s, and the short stream sample was 2.57 FPS. The one physical camera is an additional serialized resource. Memory is substantial (about 432.5 MiB process working set after warm-up, private bytes about 1.08 GiB). These values are specific to this host and short workload, not capacity guarantees.

## 10. Known issues and bugs

1. **No-face is serialized as a face.** `detect_faces_deepface` uses `enforce_detection=False`; DeepFace’s documented fallback makes a full-image region/confidence 0 when no detection is found. `process_face` still embeds it and routes increment `faces_detected`. Confirmed live on both upload and camera calls. Files: `services/face_detector.py` and `routes/detection.py`.
2. **Embedding failure can look like a valid embedding.** `process_face` substitutes 128 zeros on represent failure, regardless of selected model. For `Facenet512` this has the wrong dimension; for all models it is indistinguishable by schema from a real numeric list unless consumers inspect content.
3. **Detector errors can look like no face.** `detect_faces_deepface` catches every exception and returns `[]`; the route can return HTTP 200 `status:"success"` after a detector failure. The installed DeepFace OpenCV backend also has a bare `except: pass` around `detectMultiScale3`.
4. **Complete analysis was intermittent live.** It returned 200 with one object on a real call, then HTTP 500 `{error:{status_code:500,code:"INTERNAL_SERVER_ERROR",message:"Complete analysis failed",request_id:...}}`. The route catches broad exceptions and replaces the cause with a generic message; listener logs were not available, so the specific cause is unknown.
5. **Health is incomplete as a model-health signal.** Detailed health reports `healthy` when camera is available and face model loaded; it does not include object-detector availability. A successful root `/` claims only face detection/embeddings/video streaming and omits object detection, while complete analysis has an object route.
6. **Face-data endpoint is a placeholder.** `/api/face-data` always returns zero/null values and is not updated from `streaming.latest_face_data`.
7. **Pause does not release or truly pause the device.** It toggles a stream-only global flag. While paused, generator busy-spins, keeps the camera context/lease, and does not capture frames. This does not pause camera users outside the stream.
8. **Live streaming detection diverges from the ordinary route.** Every fifth frame it calls `DeepFace.extract_faces` inline and only draws boxes; it does not use `detect_faces_deepface`/`process_face` or return embeddings. Exceptions are caught and rendered as “Detection Error”; streaming continues.
9. **Upload error mapping is broad.** The upload endpoint catches broad exceptions and returns HTTP 400, including unexpected processing errors; it reads the entire upload without a route-level size limit.
10. **YOLO lookup depends on current working directory.** Local weights are at the service root while the explicit search checks `models/`; fallback `YOLO("yolov8n.pt")` depends on process CWD. An offline launch from repo root failed to find them, while the normal service-directory launch makes the local file discoverable.
11. **Shutdown relies on request cleanup for lease release.** `ResourcePool.shutdown()` closes `_camera` but does not explicitly release the Central lease client; abnormal shutdown can leave authority cleanup to lease timeout/liveness handling.
12. **Emotion-related types/tests are stale.** `HealthCheckResponse.emotion_detection` is always disabled; `FaceData` has no emotion fields, but route constructors pass extra emotion keys (ignored by Pydantic defaults). `tests/test_vision.py` expects seven emotion scores and uses `http://localhost:8001`, while the service is HTTPS and middleware now protects detection/camera/stream routes. These tests do not describe current route behavior.
13. **Version metadata disagrees.** `vision_service.__version__` is `1.0.0`, while FastAPI and root health report `4.0.0`.
14. **Configuration validation is empty.** `Config.validate()` is a `pass`; invalid values such as nonpositive camera timeouts are not rejected there.

## 11. Redundancy and unnecessary code

Search method: `rg` over all `02_vision_service/vision_service/**/*.py` for each class/function symbol, then source import/call inspection. Results:

- `VisualFeatureExtractor` appears only at its class definition; no route/service instantiates it. It is currently disconnected from the live service. Its documented RGB/BGR support is also suspect: the conversion expression at the top of `extract_features()` chooses the original image for every 3-channel input, so BGR is not converted despite the comment.
- `InstanceTracker` has no caller in Vision code; its sample references occur in its own docstring. It is a standalone, unmounted in-memory subsystem. Several scoring helpers use bare `except:` and silently return defaults.
- `ObjectDetector.detect_batch()` has no caller in Vision code and simply loops over `detect()`; it is unused in the mounted app.
- Face detection has two distinct implementations: normal endpoints call the shared `face_detector` helpers; streaming imports DeepFace and calls `extract_faces` inline. The different result handling is real, not just a duplicate import.
- Confirmed unused imports in route/service files include `io`, `PIL.Image`, `Optional`, and `ObjectDetectionResponse` in `routes/detection.py`; `datetime` and `Config` in `routes/camera.py`; `List`, `Tuple`, and `HTTPException` in `routes/streaming.py`; `sys` in `services/resource_pool.py`; and `datetime`, `cv2`, and `Tuple` in `services/face_detector.py` (the exact set is based on in-file symbol search). `models.py` also imports `Field` and `Dict` without use.
- `Config.MODEL_LOAD_MAX_RETRIES`, `Config.MODEL_LOAD_BACKOFF_SECONDS`, `CAMERA_TIMEOUT`, cache root, camera selector, service URL, and detector/model toggles are read by startup/routes. `Config.validate()` is not functional. `VALID_BACKENDS`/`VALID_EMBEDDING_MODELS` constrain route query values.
- `requirements.txt` includes direct-looking packages with no direct Vision import (`pydantic-settings`, `httpx`, `scikit-image`); some may be transitive. Conversely, `camera_client.py` directly imports `requests` and `psutil`, but neither is explicitly listed in this service’s requirements. The installed environment currently supplies them, but the service’s dependency declaration is incomplete for those direct imports.

## 12. Dependencies

Groups below are based on Vision’s source imports and the active route/model path, not on a claim that every transitive dependency was exhaustively resolved.

| Requirement | Pin | Group / evidence |
|---|---:|---|
| `fastapi` | 0.129.0 | Required by mounted routes/app. |
| `uvicorn[standard]` | 0.24.0 | Required ASGI server in `main.py`/commands. |
| `pydantic` | 2.12.5 | Required by response models and FastAPI schemas. |
| `pydantic-settings` | 2.13.0 | No direct Vision import found; unclear/transitive or leftover. |
| `cryptography` | 46.0.5 | Used through shared security stack; not imported by a Vision route directly. |
| `python-dotenv` | 1.2.3 | Used by Uvicorn `--env-file` launch command. |
| `python-multipart` | 0.0.22 | Required by multipart `UploadFile` route. |
| `httpx` | 0.25.0 | No direct Vision import found; unclear/transitive or leftover. |
| `anyio` | 4.15.1 | ASGI/FastAPI/Starlette runtime dependency. |
| `opencv-python` | 4.8.0.76 | Required for camera, image decode/encode, cascade detector. |
| `cv2-enumerate-cameras` | 1.3.3 | Optional native camera enumeration; code falls back to OpenCV probing on import/runtime failure. |
| `Pillow` | 10.0.1 | Imported as `PIL.Image` in detection route but unused there; may also be model-stack transitively. |
| `torch` | 2.0.1 | Required by Ultralytics YOLO runtime. |
| `torchvision` | 0.15.2 | Model/runtime companion used by Ultralytics stack. |
| `tensorflow` | 2.20.0 | FaceNet model execution. |
| `tf-keras` | 2.20.1 | DeepFace/TensorFlow Keras compatibility path. |
| `keras` | 3.15.1 | TensorFlow/DeepFace model stack. |
| `deepface` | 0.0.98 | Face detector/embedding API and FaceNet implementation. |
| `ultralytics` | 8.0.196 | YOLOv8 object detector. |
| `scikit-image` | 0.21.0 | No direct Vision import found; unclear/transitive or leftover. |
| `numpy` | 1.26.4 | Image arrays and model result conversion. |
| `scipy` | 1.11.2 | Imported only by the currently unreferenced visual-feature extractor (and possibly transitively elsewhere). |

Direct imports of `requests` and `psutil` in `camera_client.py` are not pinned in this requirements file; they are present in the observed environment through other installed packages, but that is not a reliable declaration.

## 13. Security posture specific to Vision

Protected route prefixes include `/api/v1/detect`, `/api/v1/analyze`, `/api/v1/frame`, `/api/face-data`, `/camera`, `/stream`, and `/live`; these require the internal-service credential. The root `/` and `/health` are public. The live `/live` call returned 401 without the internal credential and 200 with it. The protected detector returns biometric embeddings in JSON, so callers must treat the response as sensitive even though Vision itself does not persist it.

Camera-frame source code does not write frame/image files or log pixel contents. Camera images are passed into in-memory inference and returned as metadata/embeddings; `/api/v1/frame` and `/stream` send JPEG bytes to their HTTP clients. Upload code reads the uploaded bytes and decodes them in memory; framework multipart parsing can spool to temporary storage, but Vision contains no explicit permanent upload storage. No Vision route sends frames to another service; Central is called for leases, not for image processing. The YOLO/DeepFace model weights are stored locally and are not user images.

## 14. Summary of major findings

| Tag | Finding |
|---|---|
| STRENGTH | Camera acquisition uses a Central lease, acknowledges before opening, serializes local physical access, closes before release acknowledgement, and confirmed idle after the sampled stream ended. |
| STRENGTH | FaceNet and YOLO paths both ran in the current live stack; upload, camera detection, health, root, and MJPEG routes returned real responses. |
| WEAKNESS | No-face input is reported as one zero-confidence full-frame “face” and still gets a 128-value embedding. |
| WEAKNESS | Combined analysis was inconsistent live (200 with object output, then generic 500); no isolated object-only endpoint or timing exists. |
| WEAKNESS | `/api/face-data` is permanently empty; emotion-oriented model/test artifacts are stale relative to the current API. |
| WEAKNESS | Stream pause keeps the lease and busy-spins; preemption revokes hardware but does not restart the interrupted request/activity. |
| WEAKNESS | YOLO weight discovery depends on working directory, and the declared dependency list omits direct `requests`/`psutil` imports. |
| NEUTRAL | Vision does not persist user images or embeddings; embeddings are returned to the caller, while model weights are cached locally. |
| NEUTRAL | The short stream sample measured 2.57 FPS on one Windows/i5-7200U host; it is not a general throughput guarantee. |


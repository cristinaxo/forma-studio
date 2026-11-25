"""Forma local-only audio studio. Start with start.command."""
from pathlib import Path
import asyncio, concurrent.futures, importlib.util, json, os, re, shutil, subprocess, sys, threading, time, uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import soundfile as sf
import imageio_ffmpeg
from process_audio import DEFAULT_VOICE_DEVICE as VOICE_DEVICE

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("FORMA_DATA_DIR", str(ROOT / "data")))
DATA.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 50 * 1024 * 1024
LOCK = threading.RLock()
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
PROCESSES = {}
ALLOWED_TOOLS = {"master", "stems", "voice"}
# Only this computer. Tests widen this through monkeypatch; production does not
# recognise a test client's host name.
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
ALLOWED_STEPS = {6, 10, 20, 30, 40, 50}
DEFAULT_SEED = 1234
MAX_SEED = 2 ** 31 - 1
MAX_ACTIVE_JOBS = 3
# Queue slots held while an upload is still being decoded. Counting projects on
# disk alone would let two concurrent uploads both pass the limit check.
RESERVATIONS = set()

def folder(ident):
    if not re.fullmatch(r"[0-9a-f]{32}", ident):
        raise HTTPException(404, "Project not found")
    p = DATA / ident
    if not (p / "project.json").is_file():
        raise HTTPException(404, "Project not found")
    return p

def read(p):
    return json.loads((p / "project.json").read_text())

def save(p, item):
    temp = p / "project.tmp"
    temp.write_text(json.dumps(item, indent=2))
    temp.replace(p / "project.json")

def update(p, **values):
    with LOCK:
        item = read(p)
        item.update(values)
        save(p, item)

@asynccontextmanager
async def lifespan(app):
    for p in DATA.iterdir():
        if (p / "project.json").exists():
            with LOCK:
                item = read(p)
                if item["status"] in {"queued", "running"}:
                    update(p, status="error", message="The studio stopped before this job finished. Run it again.")
    yield
    for process in list(PROCESSES.values()):
        process.terminate()
    EXECUTOR.shutdown(wait=False, cancel_futures=True)

app = FastAPI(title="Forma local studio", lifespan=lifespan)

@app.middleware("http")
async def local_boundary(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":")[0]
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "This studio is available only on this computer."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host"):
        return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"detail": "Cross-site requests are not allowed."}, status_code=403)
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse({"detail": "Content-Length must be a number."}, status_code=400)
    if declared > MAX_BYTES * 2 + 1024 * 1024:
        return JSONResponse({"detail": "Upload is too large. Maximum 50 MB per file."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response

def job(p, tool, options):
    try:
        with LOCK:
            if read(p)["status"] == "cancelled":
                return
            update(p, status="running", started=time.time(), message="Processing on your computer")
        output = p / "output"
        output.mkdir(exist_ok=True)
        command = [sys.executable, "-u", str(ROOT / "process_audio.py"), tool,
                   "--source", str(p / "source.wav"), "--output", str(output)]
        if tool == "master":
            command += ["--preset", options["preset"], "--target", str(options["target"])]
        elif tool == "voice":
            command += ["--reference", str(p / "reference.wav"), "--steps", str(options["steps"]),
                        "--pitch", str(options["pitch"]), "--mode", options["mode"],
                        "--seed", str(options.get("seed", DEFAULT_SEED))]
        with (p / "process.log").open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
            with LOCK:
                PROCESSES[p.name] = process
                if read(p)["status"] == "cancelled":
                    process.terminate()
            try:
                code = process.wait(timeout=3600)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
                raise RuntimeError("Processing exceeded one hour. Try a shorter clip.")
        with LOCK:
            PROCESSES.pop(p.name, None)
            if read(p)["status"] == "cancelled":
                return
        if code != 0:
            lines = (p / "process.log").read_text(errors="replace").splitlines()
            detail = next((x for x in reversed(lines) if x.strip()), "Unknown engine error")
            raise RuntimeError(detail[-350:])
        outputs = []
        for f in sorted(output.glob("*.wav")):
            info = sf.info(f)
            outputs.append({"name": f.stem.replace("-", " ").title(), "file": f.name,
                            "url": f"/api/projects/{p.name}/audio/{f.name}",
                            "duration": info.duration, "bytes": f.stat().st_size})
        if not outputs:
            raise RuntimeError("Processing finished without producing audio.")
        stats = json.loads((output / "analysis.json").read_text()) if (output / "analysis.json").exists() else None
        update(p, status="success", completed=time.time(), outputs=outputs, analysis=stats, message="Ready to listen")
    except Exception as e:
        with LOCK:
            if read(p)["status"] != "cancelled":
                update(p, status="error", message=str(e))
    finally:
        PROCESSES.pop(p.name, None)

async def decode(upload, dest, max_seconds):
    incoming = dest.with_suffix(".upload")
    total = 0
    try:
        with incoming.open("wb") as f:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(413, "Each audio file must be under 50 MB.")
                f.write(chunk)
        if not total:
            raise HTTPException(422, "Choose a non-empty audio file.")
        # A fixed output format keeps codecs and user filenames out of all jobs.
        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-y", "-i", str(incoming),
                   "-t", str(max_seconds + 1), "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(dest)]
        result = await asyncio.to_thread(subprocess.run, command, capture_output=True, timeout=120)
        if result.returncode:
            raise HTTPException(422, "This file could not be decoded. Try WAV, MP3, FLAC, M4A or WebM.")
        info = sf.info(dest)
        if info.duration > max_seconds:
            raise HTTPException(422, f"Use a clip no longer than {max_seconds} seconds for this tool.")
        if info.duration < .5:
            raise HTTPException(422, "Audio must be at least half a second long.")
        return {"duration": info.duration, "sample_rate": info.samplerate, "channels": info.channels}
    finally:
        incoming.unlink(missing_ok=True)
        await upload.close()

@app.get("/api/status")
def status():
    installed = importlib.util.find_spec("demucs") is not None
    seed = (ROOT / "vendor/seed-vc/inference.py").exists()
    return {"mode": "local", "stems": installed, "voice": seed,
            "master": True, "device": (os.environ.get("FORMA_VOICE_DEVICE") or VOICE_DEVICE).upper(),
            "max_seconds": 180, "voice_seconds": 30,
            "data_directory": str(DATA), "version": "0.1.0"}

@app.get("/api/projects")
def projects():
    with LOCK:
        items = [read(p) for p in DATA.iterdir() if (p / "project.json").exists()]
    return sorted(items, key=lambda x: x["created"], reverse=True)

@app.get("/api/projects/{ident}")
def project(ident: str):
    with LOCK:
        return read(folder(ident))

@app.post("/api/projects")
async def create(source: UploadFile = File(...), reference: UploadFile | None = File(None),
                 tool: str = Form(...), title: str = Form(""), preset: str = Form("balanced"),
                 target: float = Form(-14), steps: int = Form(10), pitch: int = Form(0),
                 mode: str = Form("speech"), seed: int = Form(DEFAULT_SEED)):
    if tool not in ALLOWED_TOOLS or preset not in {"balanced", "warm", "bright", "punch"}:
        raise HTTPException(422, "Choose a valid tool and preset.")
    if not (-20 <= target <= -9 and steps in ALLOWED_STEPS and -12 <= pitch <= 12
            and mode in {"speech", "singing"} and 0 <= seed <= MAX_SEED):
        raise HTTPException(422, "Invalid processing settings.")
    if tool == "voice" and reference is None:
        raise HTTPException(422, "Add a reference voice recording.")
    p = DATA / uuid.uuid4().hex
    with LOCK:
        active = sum(read(q)["status"] in {"running", "queued"} for q in DATA.iterdir() if (q / "project.json").exists())
        if active + len(RESERVATIONS) >= MAX_ACTIVE_JOBS:
            raise HTTPException(429, f"{MAX_ACTIVE_JOBS} jobs are already queued. Wait for one to finish.")
        p.mkdir()
        RESERVATIONS.add(p.name)
    try:
        info = await decode(source, p / "source.wav", 30 if tool == "voice" else 180)
        if reference:
            ref = await decode(reference, p / "reference.wav", 30)
            if ref["duration"] < 3:
                raise HTTPException(422, "Use at least 3 seconds of clean reference voice.")
        item = {"id": p.name, "title": (title.strip() or Path(source.filename or "Untitled recording").stem)[:100],
                "created": time.time(), "status": "queued", "tool": tool, "message": "Waiting for the local engine",
                "source_url": f"/api/projects/{p.name}/audio/source.wav", "outputs": [], "analysis": None,
                "settings": {"preset": preset, "target": target, "steps": steps, "pitch": pitch,
                             "mode": mode, "seed": seed,
                             "device": os.environ.get("FORMA_VOICE_DEVICE") or VOICE_DEVICE}, **info}
        with LOCK:
            save(p, item)
            RESERVATIONS.discard(p.name)
        EXECUTOR.submit(job, p, tool, item["settings"])
        return item
    except BaseException:
        with LOCK:
            RESERVATIONS.discard(p.name)
        shutil.rmtree(p, ignore_errors=True)
        raise

@app.post("/api/projects/{ident}/cancel")
def cancel(ident: str):
    p = folder(ident)
    with LOCK:
        if read(p)["status"] not in {"queued", "running"}:
            raise HTTPException(409, "This job has already finished.")
        update(p, status="cancelled", message="Stopped by you")
        process = PROCESSES.get(ident)
        if process:
            process.terminate()
    return {"ok": True}

@app.delete("/api/projects/{ident}")
def delete(ident: str):
    with LOCK:
        p = folder(ident)
        if read(p)["status"] in {"queued", "running"} or ident in PROCESSES:
            raise HTTPException(409, "Wait for this job to stop before deleting it.")
        shutil.rmtree(p)
    return {"ok": True}

@app.get("/api/projects/{ident}/audio/{filename}")
def audio(ident: str, filename: str):
    p = folder(ident)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+\.wav", filename):
        raise HTTPException(404)
    f = p / "source.wav" if filename == "source.wav" else p / "output" / filename
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type="audio/wav", filename=filename, content_disposition_type="inline")

@app.get("/")
def home():
    return FileResponse(ROOT / "static/index.html")

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

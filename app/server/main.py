import io
import os
import secrets
import shutil
import signal
import subprocess
import sys
from argparse import Namespace
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from fastapi import FastAPI, Request, HTTPException, Header, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from PIL import Image

from manga_translator import Config
from server.instance import ExecutorInstance, executor_instances
from server.myqueue import task_queue
from server.request_extraction import get_ctx, while_streaming, TranslateRequest, BatchTranslateRequest, get_batch_ctx
from server.to_json import to_translation, TranslationResponse
from server.edit import RerenderRequest

app = FastAPI()
nonce = None

# 所有 spawn 出來的 worker 子進程清單；signal handler 會一次 terminate 全部。
# 之前 per-worker 的 signal.signal 會覆寫，N>1 時只殺最後一個 → 其他 leak。
_SPAWNED_WORKER_PROCS: list = []

BASE_DIR = Path(__file__).resolve().parent
RESULT_ROOT = (BASE_DIR.parent / "result").resolve()
RESULT_ROOT.mkdir(parents=True, exist_ok=True)

FONTS_ROOT = (BASE_DIR.parent / "fonts").resolve()
USER_FONTS_ROOT = (FONTS_ROOT / "user").resolve()
# 內建可選字型：value = render.font_path 送出的值（相對 fonts/）
_BUNDLED_FONTS = [
    {"value": "", "label": "自動（依語言）"},
    {"value": "NotoSansMonoCJK-TC.otf", "label": "Noto Sans CJK 繁中"},
    {"value": "NotoSansMonoCJK-SC.otf", "label": "Noto Sans CJK 简中"},
    {"value": "TaipeiSansTCBeta-Regular.ttf", "label": "台北黑體"},
    {"value": "anime_ace.ttf", "label": "Anime Ace（英）"},
    {"value": "comic shanns 2.ttf", "label": "Comic Shanns（英）"},
]
_FONT_EXTS = {".ttf", ".otf", ".ttc", ".otc"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加result文件夹静态文件服务
if RESULT_ROOT.exists():
    app.mount("/result", StaticFiles(directory=str(RESULT_ROOT)), name="result")

@app.post("/register", response_description="no response", tags=["internal-api"])
async def register_instance(instance: ExecutorInstance, req: Request, req_nonce: str = Header(alias="X-Nonce")):
    if req_nonce != nonce:
        raise HTTPException(401, detail="Invalid nonce")
    instance.ip = req.client.host
    executor_instances.register(instance)

def _detect_image_format(image_bytes: bytes) -> str:
    """從 image bytes 的 magic header 判斷格式。回傳 'JPEG'/'PNG'/'WEBP'/'GIF'/'BMP'，未知回 'JPEG'。"""
    if not image_bytes or len(image_bytes) < 12:
        return "JPEG"
    if image_bytes[:3] == b'\xff\xd8\xff':
        return "JPEG"
    if image_bytes[:8].startswith(b'\x89PNG'):
        return "PNG"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "WEBP"
    if image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return "GIF"
    if image_bytes[:2] == b'BM':
        return "BMP"
    return "JPEG"


def _save_result(result, fmt: str) -> bytes:
    """依 fmt 把 PIL Image 編成 bytes。RGBA→RGB 轉換只在 JPEG/BMP（不支援 alpha）時做。"""
    img_byte_arr = io.BytesIO()
    fmt = (fmt or "JPEG").upper()
    if fmt == "JPG":
        fmt = "JPEG"
    if fmt in ("JPEG", "BMP") and result.mode in ("RGBA", "LA", "P"):
        result = result.convert("RGB")
    if fmt == "JPEG":
        result.save(img_byte_arr, format="JPEG", quality=90, optimize=True)
    elif fmt == "PNG":
        result.save(img_byte_arr, format="PNG", optimize=True)
    elif fmt == "WEBP":
        result.save(img_byte_arr, format="WEBP", quality=90)
    elif fmt == "GIF":
        result.save(img_byte_arr, format="GIF")
    elif fmt == "BMP":
        result.save(img_byte_arr, format="BMP")
    else:
        # fallback JPEG
        if result.mode in ("RGBA", "LA", "P"):
            result = result.convert("RGB")
        result.save(img_byte_arr, format="JPEG", quality=90, optimize=True)
    return img_byte_arr.getvalue()


def transform_to_image(ctx):
    """預設 transform：JPEG q=90（給沒帶格式資訊的 endpoint 用）。"""
    if hasattr(ctx, 'use_placeholder') and ctx.use_placeholder:
        return _save_result(ctx.result, "PNG")
    return _save_result(ctx.result, "JPEG")


def make_transform_to_image(input_fmt: str):
    """工廠：用 input_fmt 包出對應的 transform，輸入是什麼格式輸出就是什麼。"""
    fmt = (input_fmt or "JPEG").upper()

    def _transform(ctx):
        if hasattr(ctx, 'use_placeholder') and ctx.use_placeholder:
            return _save_result(ctx.result, "PNG")
        return _save_result(ctx.result, fmt)

    return _transform

def transform_to_json(ctx):
    return to_translation(ctx).model_dump_json().encode("utf-8")

def transform_to_bytes(ctx):
    return to_translation(ctx).to_bytes()

@app.post("/translate/json", response_model=TranslationResponse, tags=["api", "json"],response_description="json strucure inspired by the ichigo translator extension")
async def json(req: Request, data: TranslateRequest):
    ctx = await get_ctx(req, data.config, data.image)
    return to_translation(ctx)

@app.post("/translate/bytes", response_class=StreamingResponse, tags=["api", "json"],response_description="custom byte structure for decoding look at examples in 'examples/response.*'")
async def bytes(req: Request, data: TranslateRequest):
    ctx = await get_ctx(req, data.config, data.image)
    return StreamingResponse(content=to_translation(ctx).to_bytes())

@app.post("/translate/image", response_description="the result image", tags=["api", "json"],response_class=StreamingResponse)
async def image(req: Request, data: TranslateRequest) -> StreamingResponse:
    ctx = await get_ctx(req, data.config, data.image)
    img_byte_arr = io.BytesIO()
    ctx.result.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)

    return StreamingResponse(img_byte_arr, media_type="image/png")

@app.post("/translate/json/stream", response_class=StreamingResponse,tags=["api", "json"], response_description="A stream over elements with strucure(1byte status, 4 byte size, n byte data) status code are 0,1,2,3,4 0 is result data, 1 is progress report, 2 is error, 3 is waiting queue position, 4 is waiting for translator instance")
async def stream_json(req: Request, data: TranslateRequest) -> StreamingResponse:
    return await while_streaming(req, transform_to_json, data.config, data.image)

@app.post("/translate/bytes/stream", response_class=StreamingResponse, tags=["api", "json"],response_description="A stream over elements with strucure(1byte status, 4 byte size, n byte data) status code are 0,1,2,3,4 0 is result data, 1 is progress report, 2 is error, 3 is waiting queue position, 4 is waiting for translator instance")
async def stream_bytes(req: Request, data: TranslateRequest)-> StreamingResponse:
    return await while_streaming(req, transform_to_bytes,data.config, data.image)

@app.post("/translate/image/stream", response_class=StreamingResponse, tags=["api", "json"], response_description="A stream over elements with strucure(1byte status, 4 byte size, n byte data) status code are 0,1,2,3,4 0 is result data, 1 is progress report, 2 is error, 3 is waiting queue position, 4 is waiting for translator instance")
async def stream_image(req: Request, data: TranslateRequest) -> StreamingResponse:
    return await while_streaming(req, transform_to_image, data.config, data.image)

@app.post("/translate/with-form/json", response_model=TranslationResponse, tags=["api", "form"],response_description="json strucure inspired by the ichigo translator extension")
async def json_form(req: Request, image: UploadFile = File(...), config: str = Form("{}")):
    img = await image.read()
    conf = Config.parse_raw(config)
    ctx = await get_ctx(req, conf, img)
    return to_translation(ctx)

@app.post("/translate/with-form/bytes", response_class=StreamingResponse, tags=["api", "form"],response_description="custom byte structure for decoding look at examples in 'examples/response.*'")
async def bytes_form(req: Request, image: UploadFile = File(...), config: str = Form("{}")):
    img = await image.read()
    conf = Config.parse_raw(config)
    ctx = await get_ctx(req, conf, img)
    return StreamingResponse(content=to_translation(ctx).to_bytes())

@app.post("/translate/with-form/image", response_description="the result image", tags=["api", "form"],response_class=StreamingResponse)
async def image_form(req: Request, image: UploadFile = File(...), config: str = Form("{}")) -> StreamingResponse:
    img = await image.read()
    conf = Config.parse_raw(config)
    ctx = await get_ctx(req, conf, img)
    img_byte_arr = io.BytesIO()
    ctx.result.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)

    return StreamingResponse(img_byte_arr, media_type="image/png")

@app.post("/translate/with-form/json/stream", response_class=StreamingResponse, tags=["api", "form"],response_description="A stream over elements with strucure(1byte status, 4 byte size, n byte data) status code are 0,1,2,3,4 0 is result data, 1 is progress report, 2 is error, 3 is waiting queue position, 4 is waiting for translator instance")
async def stream_json_form(req: Request, image: UploadFile = File(...), config: str = Form("{}")) -> StreamingResponse:
    img = await image.read()
    conf = Config.parse_raw(config)
    # 标记这是Web前端调用，用于占位符优化
    conf._is_web_frontend = True
    return await while_streaming(req, transform_to_json, conf, img)



@app.post("/translate/with-form/bytes/stream", response_class=StreamingResponse,tags=["api", "form"], response_description="A stream over elements with strucure(1byte status, 4 byte size, n byte data) status code are 0,1,2,3,4 0 is result data, 1 is progress report, 2 is error, 3 is waiting queue position, 4 is waiting for translator instance")
async def stream_bytes_form(req: Request, image: UploadFile = File(...), config: str = Form("{}"))-> StreamingResponse:
    img = await image.read()
    conf = Config.parse_raw(config)
    return await while_streaming(req, transform_to_bytes, conf, img)

@app.post("/translate/with-form/image/stream", response_class=StreamingResponse, tags=["api", "form"], response_description="Standard streaming endpoint - returns complete image data. Suitable for API calls and scripts.")
async def stream_image_form(req: Request, image: UploadFile = File(...), config: str = Form("{}")) -> StreamingResponse:
    """通用流式端点：返回完整图片数据，适用于API调用和comicread脚本。輸出格式 = 輸入格式。"""
    img = await image.read()
    conf = Config.parse_raw(config)
    # 标记为通用模式，不使用占位符优化
    conf._web_frontend_optimized = False
    fmt = _detect_image_format(img)
    return await while_streaming(req, make_transform_to_image(fmt), conf, img)

@app.post("/translate/with-form/image/stream/web", response_class=StreamingResponse, tags=["api", "form"], response_description="Web frontend optimized streaming endpoint - uses placeholder optimization for faster response.")
async def stream_image_form_web(req: Request, image: UploadFile = File(...), config: str = Form("{}"), advanced: str = Form("0")) -> StreamingResponse:
    """Web前端专用端点：使用占位符优化，提供极速体验。輸出格式 = 輸入格式。"""
    img = await image.read()
    conf = Config.parse_raw(config)
    # 标记为Web前端优化模式，使用占位符优化
    conf._web_frontend_optimized = True
    # 進階編輯模式才存編輯狀態（pkl 較大，避免一般使用者浪費磁碟）
    conf._save_edit = advanced == "1"
    fmt = _detect_image_format(img)
    return await while_streaming(req, make_transform_to_image(fmt), conf, img)

@app.post("/queue-size", response_model=int, tags=["api", "json"])
async def queue_size() -> int:
    return len(task_queue.queue)




@app.api_route("/result/{folder_name}/final.png", methods=["GET", "HEAD"], tags=["api", "file"])
async def get_result_by_folder(folder_name: str):
    """根据文件夹名称获取翻译结果图片"""
    result_dir = RESULT_ROOT
    if not result_dir.exists():
        raise HTTPException(404, detail="Result directory not found")

    folder_path = result_dir / folder_name
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(404, detail=f"Folder {folder_name} not found")

    final_png_path = folder_path / "final.png"
    if not final_png_path.exists():
        raise HTTPException(404, detail="final.png not found in folder")

    async def file_iterator():
        with open(final_png_path, "rb") as f:
            yield f.read()

    return StreamingResponse(
        file_iterator(),
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=final.png"}
    )

@app.post("/translate/batch/json", response_model=list[TranslationResponse], tags=["api", "json", "batch"])
async def batch_json(req: Request, data: BatchTranslateRequest):
    """Batch translate images and return JSON format results"""
    results = await get_batch_ctx(req, data.config, data.images, data.batch_size)
    return [to_translation(ctx) for ctx in results]

@app.post("/translate/batch/images", response_description="Zip file containing translated images", tags=["api", "batch"])
async def batch_images(req: Request, data: BatchTranslateRequest):
    """Batch translate images and return zip archive containing translated images"""
    import zipfile
    import tempfile
    
    results = await get_batch_ctx(req, data.config, data.images, data.batch_size)
    
    # Create temporary ZIP file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
        with zipfile.ZipFile(tmp_file, 'w') as zip_file:
            for i, ctx in enumerate(results):
                if ctx.result:
                    img_byte_arr = io.BytesIO()
                    ctx.result.save(img_byte_arr, format="PNG")
                    zip_file.writestr(f"translated_{i+1}.png", img_byte_arr.getvalue())
        
        # Return ZIP file
        with open(tmp_file.name, 'rb') as f:
            zip_data = f.read()
        
        # Clean up temporary file
        os.unlink(tmp_file.name)
        
        return StreamingResponse(
            io.BytesIO(zip_data),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=translated_images.zip"}
        )

@app.get("/", response_class=HTMLResponse,tags=["ui"])
async def index() -> HTMLResponse:
    script_directory = Path(__file__).parent
    html_file = script_directory / "index.html"
    html_content = html_file.read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)

@app.get("/manual", response_class=HTMLResponse, tags=["ui"])
async def manual():
    script_directory = Path(__file__).parent
    html_file = script_directory / "manual.html"
    html_content = html_file.read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)

def generate_nonce():
    return secrets.token_hex(16)

def start_translator_client_proc(host: str, port: int, nonce: str, params: Namespace):
    cmds = [
        sys.executable,
        '-m', 'manga_translator',
        'shared',
        '--host', host,
        '--port', str(port),
        '--nonce', nonce,
    ]
    if params.use_gpu:
        cmds.append('--use-gpu')
    if params.use_gpu_limited:
        cmds.append('--use-gpu-limited')
    if params.ignore_errors:
        cmds.append('--ignore-errors')
    if params.verbose:
        cmds.append('--verbose')
    if params.models_ttl:
        cmds.append('--models-ttl=%s' % params.models_ttl)
    if getattr(params, 'pre_dict', None):
        cmds.extend(['--pre-dict', params.pre_dict])
    if getattr(params, 'post_dict', None):
        cmds.extend(['--post-dict', params.post_dict])       
    base_path = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(base_path)
    proc = subprocess.Popen(cmds, cwd=parent)
    # 同一個 worker 進程註冊 K 次（每次獨立 ExecutorInstance，各有自己 busy flag），
    # 讓 orchestrator 的 find_executor() / free_executors() 看到 K 個邏輯 slot，
    # 全部指到同 ip:port → worker 端用 _PriorityGpuLock 自己處理並發。
    # K 從 env 讀，預設 5（對應 bot side MANGA_TRANSLATOR_CONCURRENCY=5）。
    _slots = int(os.getenv('MT_WORKER_CONCURRENCY', '5'))
    for _ in range(max(1, _slots)):
        executor_instances.register(ExecutorInstance(ip=host, port=port))

    # 累積到 module-level list，signal handler 一次殺所有 worker proc。
    # 之前用 closure 只記住自己的 proc，每呼叫一次 start_translator_client_proc
    # 就 signal.signal() 覆寫，導致 N=2 worker 時只有最後一個會被 terminate，
    # 8002 會 leak（下次啟動撞 10048 port-in-use）。
    _SPAWNED_WORKER_PROCS.append(proc)

    def handle_exit_signals(signal_num, frame):
        for p in _SPAWNED_WORKER_PROCS:
            try:
                p.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit_signals)
    signal.signal(signal.SIGTERM, handle_exit_signals)

    return proc

def prepare(args):
    global nonce
    if args.nonce is None:
        nonce = os.getenv('MT_WEB_NONCE', generate_nonce())
    else:
        nonce = args.nonce
    if args.start_instance:
        # Multi-worker：spawn N 個獨立 worker 進程在 args.port+1, +2, ..., +N。
        # 每個 worker 自己載一份模型到 VRAM，獨立 event loop 跟 _PriorityGpuLock。
        # MT_WORKER_CONCURRENCY 控每個 worker 內部 slot 數（會在 start_translator_client_proc 註冊到 orchestrator）。
        num_workers = max(1, int(os.getenv('MT_NUM_WORKERS', '1')))
        procs = []
        for i in range(num_workers):
            procs.append(start_translator_client_proc(args.host, args.port + 1 + i, nonce, args))
        # 回傳第一個 proc 給上層 signal handler；其他 proc 由各自的 signal handler 管
        return procs[0] if procs else None
    folder_name= "upload-cache"
    if os.path.exists(folder_name):
        shutil.rmtree(folder_name)
    os.makedirs(folder_name)

@app.post("/simple_execute/translate_batch", tags=["internal-api"])
async def simple_execute_batch(req: Request, data: BatchTranslateRequest):
    """Internal batch translation execution endpoint"""
    # Implementation for batch translation logic
    # Currently returns empty results, actual implementation needs to call batch translator
    from manga_translator import MangaTranslator
    translator = MangaTranslator({'batch_size': data.batch_size})
    
    # Prepare image-config pairs
    images_with_configs = [(img, data.config) for img in data.images]
    
    # Execute batch translation
    results = await translator.translate_batch(images_with_configs, data.batch_size)
    
    return results

@app.post("/execute/translate_batch", tags=["internal-api"])
async def execute_batch_stream(req: Request, data: BatchTranslateRequest):
    """Internal batch translation streaming execution endpoint"""
    # Streaming batch translation implementation
    from manga_translator import MangaTranslator
    translator = MangaTranslator({'batch_size': data.batch_size})
    
    # Prepare image-config pairs
    images_with_configs = [(img, data.config) for img in data.images]
    
    # Execute batch translation (streaming version requires more complex implementation)
    results = await translator.translate_batch(images_with_configs, data.batch_size)
    
    return results

@app.get("/results/list", tags=["api"])
async def list_results():
    """List all result directories"""
    result_dir = RESULT_ROOT
    if not result_dir.exists():
        return {"directories": []}
    
    try:
        directories = []
        for item_path in result_dir.iterdir():
            if item_path.is_dir():
                # Check if final.png exists in this directory
                final_png_path = item_path / "final.png"
                if final_png_path.exists():
                    directories.append(item_path.name)
        return {"directories": directories}
    except Exception as e:
        raise HTTPException(500, detail=f"Error listing results: {str(e)}")

@app.get("/update/check", tags=["api"])
async def update_check():
    """檢查 GitHub 是否有新版，回傳更新內容清單。"""
    from server.update import check_update
    try:
        return await check_update()
    except Exception as e:
        raise HTTPException(500, detail=f"Update check failed: {e}")

@app.post("/update/apply", tags=["api"])
async def update_apply():
    """下載並套用最新版，然後排程重啟。"""
    from server.update import apply_update, schedule_restart
    try:
        result = await apply_update()
    except Exception as e:
        raise HTTPException(500, detail=f"Update failed: {e}")
    try:
        schedule_restart()
        result["restart_scheduled"] = True
    except Exception as e:
        result["restart_scheduled"] = False
        result["restart_error"] = str(e)
    return result

@app.get("/edit/state/{folder_name}", tags=["api"])
async def edit_state(folder_name: str):
    """進階編輯：回該翻譯結果的可編輯文字框資料 + 背景尺寸。"""
    from server.edit import state_to_json
    data = state_to_json(RESULT_ROOT, folder_name)
    if data is None:
        raise HTTPException(404, detail="Edit state not found. Translate with advanced mode on.")
    return data

@app.post("/edit/rerender", tags=["api"])
async def edit_rerender(req: RerenderRequest):
    """進階編輯：套用編輯、只重跑 render，回 PNG，並把成品存回 final.png（圖庫顯示編輯後版本）。"""
    from server.edit import rerender
    try:
        img = await rerender(RESULT_ROOT, req.folder, req.edits)
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=f"Rerender failed: {e}")
    rgb = img.convert("RGB")
    # 覆蓋 final.png：之後圖庫 / 點圖看到的就是編輯後的版本（「還原出廠」會用原始 edits 重渲染還原）
    try:
        safe = os.path.basename(req.folder)
        final_path = RESULT_ROOT / safe / "final.png"
        if final_path.parent.exists():
            rgb.save(str(final_path))
    except Exception:
        pass
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/fonts/list", tags=["api"])
async def list_fonts():
    """回傳可選字型：內建 + 使用者上傳（fonts/user/）。"""
    fonts = list(_BUNDLED_FONTS)
    if USER_FONTS_ROOT.exists():
        for f in sorted(USER_FONTS_ROOT.iterdir()):
            if f.is_file() and f.suffix.lower() in _FONT_EXTS:
                fonts.append({"value": f"user/{f.name}", "label": f"📁 {f.stem}"})
    return {"fonts": fonts}

@app.post("/fonts/upload", tags=["api"])
async def upload_font(font: UploadFile = File(...)):
    """上傳自訂字型存到 fonts/user/，回傳可用於 render.font_path 的值。"""
    name = os.path.basename(font.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if ext not in _FONT_EXTS:
        raise HTTPException(400, detail=f"Unsupported font type: {ext or '(none)'}")
    USER_FONTS_ROOT.mkdir(parents=True, exist_ok=True)
    dest = USER_FONTS_ROOT / name
    try:
        with open(dest, "wb") as fp:
            shutil.copyfileobj(font.file, fp)
    except Exception as e:
        raise HTTPException(500, detail=f"Save failed: {e}")
    return {"value": f"user/{name}", "label": f"📁 {os.path.splitext(name)[0]}"}

@app.post("/results/open-folder", tags=["api"])
async def open_results_folder():
    """在本機檔案管理器開啟 result 資料夾（僅限 localhost 桌面使用）"""
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == 'win32':
            os.startfile(str(RESULT_ROOT))
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(RESULT_ROOT)])
        else:
            subprocess.Popen(['xdg-open', str(RESULT_ROOT)])
        return {"opened": str(RESULT_ROOT)}
    except Exception as e:
        raise HTTPException(500, detail=f"Cannot open folder: {e}")

@app.delete("/results/clear", tags=["api"])
async def clear_results():
    """Delete all result directories"""
    result_dir = RESULT_ROOT
    if not result_dir.exists():
        return {"message": "No results directory found"}
    
    try:
        deleted_count = 0
        for item_path in result_dir.iterdir():
            if item_path.is_dir():
                # Check if final.png exists in this directory
                final_png_path = item_path / "final.png"
                if final_png_path.exists():
                    shutil.rmtree(item_path)
                    deleted_count += 1
        
        return {"message": f"Deleted {deleted_count} result directories"}
    except Exception as e:
        raise HTTPException(500, detail=f"Error clearing results: {str(e)}")

@app.delete("/results/{folder_name}", tags=["api"])
async def delete_result(folder_name: str):
    """Delete a specific result directory"""
    result_dir = RESULT_ROOT
    folder_path = result_dir / folder_name
    
    if not folder_path.exists():
        raise HTTPException(404, detail="Result directory not found")
    
    try:
        # Check if final.png exists in this directory
        final_png_path = folder_path / "final.png"
        if not final_png_path.exists():
            raise HTTPException(404, detail="Result file not found")
        
        shutil.rmtree(folder_path)
        return {"message": f"Deleted result directory: {folder_name}"}
    except Exception as e:
        raise HTTPException(500, detail=f"Error deleting result: {str(e)}")

#todo: restart if crash
#todo: cache results
#todo: cleanup cache

if __name__ == '__main__':
    import uvicorn
    from args import parse_arguments

    args = parse_arguments()
    args.start_instance = True
    proc = prepare(args)
    print("Nonce: "+nonce)
    try:
        uvicorn.run(app, host=args.host, port=args.port)
    except Exception:
        if proc:
            proc.terminate()

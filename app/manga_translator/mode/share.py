import asyncio
import contextvars
import os
import pickle
import io
import secrets

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Request, Response
from pydantic import BaseModel

from starlette.responses import StreamingResponse

from manga_translator import MangaTranslator

# 每個 /execute/* request 自己一條 progress queue。Hook 從 contextvar 讀，
# create_task 會把當前 context 複製進子 task，所以 worker pipeline 內 _report_progress
# 觸發 hook 時拿到的是「自己這個 request 的 queue」，不會跟其他並行的 request 混 chunk。
_progress_queue_var: contextvars.ContextVar = contextvars.ContextVar('progress_queue', default=None)

SAFE_PICKLE_MODULES = frozenset({
    'builtins',
    'collections',
    'numpy',
    'numpy.core.multiarray',
    'numpy.dtype',
    'manga_translator',
    'manga_translator.utils',
    'manga_translator.utils.generic',
    'manga_translator.config'
})


class RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if module in SAFE_PICKLE_MODULES or module.startswith('PIL.'):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"Deserialization of {module}.{name} is not allowed"
        )


def restricted_loads(data: bytes):
    return RestrictedUnpickler(io.BytesIO(data)).load()


class MethodCall(BaseModel):
    method_name: str
    attributes: bytes


class MangaShare:
    def __init__(self, params: dict = None):
        self.manga = MangaTranslator(params)
        self.host = params.get('host', '127.0.0.1')
        self.port = int(params.get('port', '5003'))
        nonce = params.get('nonce', None)
        if not nonce:
            nonce = secrets.token_hex(16)
        if nonce == "None":
            nonce = None
        self.nonce = nonce

        # K 張並行進來時，每張 request handler 自己建一個 queue，把它放進 contextvar，
        # 然後 create_task(run_method)。create_task 複製 context，hook 在子 task 裡呼叫
        # _progress_queue_var.get() 取到正確的 queue。沒有 listener 的 hook（理論上不會發生
        # 因為每個 request 都會 set queue）就 drop 訊息。
        async def hook(state: str, finished: bool):
            ctx = _progress_queue_var.get()
            if ctx is None:
                return
            state_data = state.encode("utf-8")
            progress_data = b'\x01' + len(state_data).to_bytes(4, 'big') + state_data
            # 記住最後一個真實進度 frame，心跳會原樣重送它（前端看到的階段標籤不變）
            ctx['last'] = progress_data
            await ctx['q'].put(progress_data)
            await asyncio.sleep(0)

        self.manga.add_progress_hook(hook)

    async def _heartbeat(self, queue: asyncio.Queue, ctx: dict):
        """Idle watchdog 的心跳：頁面處理期間，只要 worker event loop 還活著就每
        MT_WORKER_HEARTBEAT 秒往 queue 塞一個 status=1 frame（重送最後的真實進度，前端無感）。
        OCR 走 to_thread、LLM 是純網路 await → loop 都空著 → 心跳照常 → 慢頁不會被誤判卡死。
        只有 loop 被同步操作卡住、或 worker 進程掛掉（socket 斷）才會停止心跳 →
        orchestrator 端的 sock_read 逾時（MT_IDLE_TIMEOUT，預設 30s＝漏掉 3 拍）才會觸發。
        run_method 完成時由 done callback cancel 掉本 task。"""
        interval = float(os.getenv('MT_WORKER_HEARTBEAT', '10'))
        try:
            while True:
                await asyncio.sleep(interval)
                frame = ctx.get('last')
                if frame is None:
                    st = b'processing'
                    frame = b'\x01' + len(st).to_bytes(4, 'big') + st
                await queue.put(frame)
        except asyncio.CancelledError:
            return

    async def progress_stream(self, queue: asyncio.Queue, run_task: asyncio.Task):
        """Loop 讀 queue 直到拿到 status != 1（最終結果 0 或錯誤 2）。"""
        terminal_frame_sent = False
        try:
            while True:
                progress = await queue.get()
                yield progress
                if progress[0] != 1:
                    terminal_frame_sent = True
                    break
        finally:
            # Closing the orchestrator stream must stop the detached worker
            # coroutine too; otherwise an aborted browser job keeps using GPU.
            if not terminal_frame_sent and not run_task.done():
                run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)

    async def run_method(self, method, queue: asyncio.Queue, **attributes):
        """跑 method，把結果（status=0）或錯誤（status=2）推進 queue 結束。"""
        try:
            if asyncio.iscoroutinefunction(method):
                result = await method(**attributes)
            else:
                result = method(**attributes)

            # 占位符模式：建最小 Context 避免傳一堆中間 array
            if hasattr(result, 'use_placeholder') and result.use_placeholder:
                from manga_translator import Context
                from PIL import Image
                minimal_result = Context()
                minimal_result.result = Image.new('RGB', (1, 1), color='white')
                minimal_result.use_placeholder = True
                result_bytes = pickle.dumps(minimal_result)
            else:
                result_bytes = pickle.dumps(result)

            encoded_result = b'\x00' + len(result_bytes).to_bytes(4, 'big') + result_bytes
            await queue.put(encoded_result)
        except Exception as e:
            err_bytes = str(e).encode("utf-8")
            encoded_result = b'\x02' + len(err_bytes).to_bytes(4, 'big') + err_bytes
            await queue.put(encoded_result)

    def check_nonce(self, request: Request):
        if self.nonce:
            nonce = request.headers.get('X-Nonce')
            if nonce != self.nonce:
                raise HTTPException(401, detail="Nonce does not match")

    def get_fn(self, method_name: str):
        if method_name.startswith("__"):
            raise HTTPException(status_code=403, detail="These functions are not allowed to be executed remotely")
        method = getattr(self.manga, method_name, None)
        if not method:
            raise HTTPException(status_code=404, detail="Method not found")
        return method

    async def listen(self, translation_params: dict = None):
        app = FastAPI()

        @app.get("/is_locked")
        async def is_locked():
            # 並發模式下不再用單一 lock；保留端點是為了向下相容（orchestrator 可能還在 poll）。
            return {"locked": False}

        @app.post("/simple_execute/{method_name}")
        async def simple_execute(request: Request, method_name: str = Path(...)):
            self.check_nonce(request)
            method = self.get_fn(method_name)
            if self.nonce is None:
                attr = pickle.loads(await request.body())
            else:
                attr = restricted_loads(await request.body())
            try:
                if asyncio.iscoroutinefunction(method):
                    result = await method(**attr)
                else:
                    result = method(**attr)
                return Response(content=pickle.dumps(result), media_type="application/octet-stream")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/execute/{method_name}")
        async def execute_stream(request: Request, method_name: str = Path(...)):
            self.check_nonce(request)
            method = self.get_fn(method_name)
            attr = pickle.loads(await request.body())

            # 為這個 request 建立獨立 queue + ctx，透過 contextvar 暴露給 hook。
            # ctx['last'] 存最後的進度 frame 供心跳重送。
            queue: asyncio.Queue = asyncio.Queue()
            ctx = {'q': queue, 'last': None}
            _progress_queue_var.set(ctx)

            # create_task 複製當前 context（含 _progress_queue_var=ctx），
            # hook 在子 task 裡呼叫 .get() 取到的就是這個 ctx
            run_task = asyncio.create_task(self.run_method(method, queue, **attr))
            # 心跳 task：worker 活著就持續餵 frame，讓 orchestrator 的 sock_read 不誤殺慢頁。
            # run_method 一結束（成功/失敗）就 cancel 掉心跳，避免多塞 frame。
            hb_task = asyncio.create_task(self._heartbeat(queue, ctx))
            run_task.add_done_callback(lambda _t: hb_task.cancel())

            return StreamingResponse(
                self.progress_stream(queue, run_task),
                media_type="application/octet-stream",
            )

        config = uvicorn.Config(app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        await server.serve()

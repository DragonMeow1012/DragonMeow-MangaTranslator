import asyncio
import contextvars
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
            q = _progress_queue_var.get()
            if q is None:
                return
            state_data = state.encode("utf-8")
            progress_data = b'\x01' + len(state_data).to_bytes(4, 'big') + state_data
            await q.put(progress_data)
            await asyncio.sleep(0)

        self.manga.add_progress_hook(hook)

    async def progress_stream(self, queue: asyncio.Queue):
        """Loop 讀 queue 直到拿到 status != 1（最終結果 0 或錯誤 2）。"""
        while True:
            progress = await queue.get()
            yield progress
            if progress[0] != 1:
                break

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

            # 占位符優化旗標：注意是寫在 self.manga 上的全域狀態，並發下會 race。
            # bot 路徑不設 _web_frontend_optimized → 永遠 False，沒影響；只有 web UI 端會設。
            config = attr.get('config')
            self.manga._is_streaming_mode = getattr(config, '_web_frontend_optimized', False) if config else False

            # 為這個 request 建立獨立 queue 並透過 contextvar 暴露給 hook
            queue: asyncio.Queue = asyncio.Queue()
            _progress_queue_var.set(queue)

            # create_task 複製當前 context（含 _progress_queue_var=queue），
            # hook 在子 task 裡呼叫 .get() 取到的就是這個 queue
            asyncio.create_task(self.run_method(method, queue, **attr))

            return StreamingResponse(self.progress_stream(queue), media_type="application/octet-stream")

        config = uvicorn.Config(app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        await server.serve()

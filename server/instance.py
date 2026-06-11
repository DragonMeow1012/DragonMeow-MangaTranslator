from asyncio import Event, Lock
import pickle
from typing import List

import aiohttp
from PIL import Image
from pydantic import BaseModel

from manga_translator import Config
from server.sent_data_internal import fetch_data_stream, NotifyType, fetch_data

# Pipeline 模式呼叫 worker 用的 timeout：pre/post 是 GPU 計算（~15s），llm 走網路（~30s）。
# 給寬鬆一點，反正 server orchestrator 端有自己的 semaphore 控制並發。
_PIPELINE_TIMEOUT = aiohttp.ClientTimeout(total=300)

class ExecutorInstance(BaseModel):
    ip: str
    port: int
    busy: bool = False

    def free_executor(self):
        self.busy = False

    def _base(self) -> str:
        return f"http://{self.ip}:{self.port}"

    async def sent(self, image: Image, config: Config):
        return await fetch_data("http://"+self.ip+":"+str(self.port)+"/simple_execute/translate", image, config)

    async def sent_stream(self, image: Image, config: Config, sender: NotifyType):
        await fetch_data_stream("http://"+self.ip+":"+str(self.port)+"/execute/translate", image, config, sender)

    async def sent_batch(self, images: List[Image.Image], config: Config, batch_size: int):
        """发送批量翻译请求"""
        return await fetch_data("http://"+self.ip+":"+str(self.port)+"/simple_execute/translate_batch",
                               {"images": images, "config": config, "batch_size": batch_size})

    async def sent_batch_stream(self, images: List[Image.Image], config: Config, batch_size: int, sender: NotifyType):
        """发送批量翻译流式请求"""
        await fetch_data_stream("http://"+self.ip+":"+str(self.port)+"/execute/translate_batch",
                               {"images": images, "config": config, "batch_size": batch_size}, config, sender)

    # ===== Pipeline 模式 RPC（對應 mode/share.py 的 /pipeline/* 端點） =====
    # 每個方法回傳 worker 的 dict response（已 unpickle）。
    # caller (server/main.py) 負責 semaphore 控制並發 + 解析 done flag。

    async def _pipeline_call(self, path: str, payload: dict, nonce: str = None) -> dict:
        url = f"{self._base()}{path}"
        body = pickle.dumps(payload)
        headers = {'Content-Type': 'application/octet-stream'}
        if nonce:
            headers['X-Nonce'] = nonce
        async with aiohttp.ClientSession(timeout=_PIPELINE_TIMEOUT) as session:
            async with session.post(url, data=body, headers=headers) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    raise RuntimeError(f"worker {path} HTTP {resp.status}: {detail[:300]}")
                raw = await resp.read()
                return pickle.loads(raw)

    async def pipeline_pre_llm(self, image: Image.Image, config: Config, nonce: str = None) -> dict:
        return await self._pipeline_call('/pipeline/pre-llm', {'image': image, 'config': config}, nonce)

    async def pipeline_llm(self, job_id: str, config: Config, nonce: str = None) -> dict:
        return await self._pipeline_call('/pipeline/llm', {'job_id': job_id, 'config': config}, nonce)

    async def pipeline_post_llm(self, job_id: str, config: Config, nonce: str = None) -> dict:
        return await self._pipeline_call('/pipeline/post-llm', {'job_id': job_id, 'config': config}, nonce)

class Executors:
    def __init__(self):
        self.list: List[ExecutorInstance] = []
        self.lock: Lock = Lock()
        self.event = Event()

    def register(self, instance: ExecutorInstance):
        self.list.append(instance)

    def free_executors(self) -> int:
        return len([item for item in self.list if not item.busy])

    async def _find_instance(self):
        while True:
            instance = next((x for x in self.list if x.busy == False), None)
            if instance is not None:
                return instance
            #todo: cricial error: warn should never happen
            await self.event.wait()

    async def find_executor(self) -> ExecutorInstance:
        async with self.lock:  # Using async with for lock management
            instance = await self._find_instance()
            instance.busy = True
            return instance

    async def free_executor(self, instance: ExecutorInstance):
        from server.myqueue import task_queue
        instance.free_executor()
        self.event.set()
        self.event.clear()
        await task_queue.update_event()

executor_instances: Executors = Executors()

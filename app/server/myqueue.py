import asyncio
import os
from typing import List, Optional

from PIL import Image
from fastapi import HTTPException
from fastapi.requests import Request

from manga_translator import Config
from server.instance import executor_instances
from server.sent_data_internal import NotifyType

class QueueElement:
    req: Request
    image: Image.Image | str
    config: Config

    def __init__(self, req: Request, image: Image.Image, config: Config, length):
        self.req = req
        if length > 10:
            #todo: store image in "upload-cache" folder
            self.image = image
        else:
            self.image = image
        self.config = config
        self._retries = 0  # idle watchdog 逾時重翻次數（上限 MT_PAGE_RETRIES）

    def get_image(self)-> Image:
        if isinstance(self.image, str):
            return Image.open(self.image)
        else:
            return self.image

    def __del__(self):
        if isinstance(self.image, str):
            os.remove(self.image)

    async def is_client_disconnected(self) -> bool:
        if await self.req.is_disconnected():
            return True
        return False


class BatchQueueElement:
    """Batch translation queue element"""
    req: Request
    images: List[Image.Image]
    config: Config
    batch_size: int

    def __init__(self, req: Request, images: List[Image.Image], config: Config, batch_size: int):
        self.req = req
        self.images = images
        self.config = config
        self.batch_size = batch_size
        self._retries = 0  # idle watchdog 逾時重翻次數（上限 MT_PAGE_RETRIES）

    async def is_client_disconnected(self) -> bool:
        if await self.req.is_disconnected():
            return True
        return False


class TaskQueue:
    def __init__(self):
        self.queue: List[QueueElement | BatchQueueElement] = []
        self.queue_event: asyncio.Event = asyncio.Event()

    def add_task(self, task: QueueElement | BatchQueueElement, priority: bool = False):
        # priority=True：重新翻譯（補漏翻 / 翻譯失敗回填的補救）插隊到最前面，
        # 不必排在整批未處理頁後面，否則補救沒意義。
        if priority:
            self.queue.insert(0, task)
        else:
            self.queue.append(task)

    def get_pos(self, task: QueueElement | BatchQueueElement) -> Optional[int]:
        try:
            return self.queue.index(task)
        except ValueError:
            return None
    async def update_event(self):
        self.queue = [task for task in self.queue if not await task.is_client_disconnected()]
        self.queue_event.set()
        self.queue_event.clear()

    async def remove(self, task: QueueElement | BatchQueueElement):
        self.queue.remove(task)
        await self.update_event()

    async def wait_for_event(self):
        await self.queue_event.wait()

task_queue = TaskQueue()

async def wait_in_queue(task: QueueElement | BatchQueueElement, notify: NotifyType):
    """Will get task position report it. If its in the range of translators then it will try to aquire an instance(blockig) and sent a task to it. when done the item will be removed from the queue and result will be returned"""
    while True:
        queue_pos = task_queue.get_pos(task)
        if queue_pos is None:
            if notify:
                return
            else:
                raise HTTPException(500, detail="User is no longer connected")  # just for the logs
        if notify:
            notify(3, str(queue_pos).encode('utf-8'))
        if queue_pos < executor_instances.free_executors():
            if await task.is_client_disconnected():
                await task_queue.update_event()
                if notify:
                    return
                else:
                    raise HTTPException(500, detail="User is no longer connected") #just for the logs

            instance = await executor_instances.find_executor()
            await task_queue.remove(task)
            if notify:
                notify(4, b"")

            try:
                # Process batch translation task
                if isinstance(task, BatchQueueElement):
                    if notify:
                        await instance.sent_batch_stream(task.images, task.config, task.batch_size, notify)
                    else:
                        result = await instance.sent_batch(task.images, task.config, task.batch_size)
                else:
                    # Process single translation task
                    if notify:
                        await instance.sent_stream(task.image, task.config, notify)
                    else:
                        result = await instance.sent(task.image, task.config)

                await executor_instances.free_executor(instance)

                if notify:
                    return
                else:
                    return result

            except asyncio.TimeoutError:
                # Idle watchdog 觸發：worker 超過 MT_IDLE_TIMEOUT 秒連心跳都沒吐 → 視為卡死。
                # 先釋放 slot（否則 busy 永久 leak、整個佇列停擺），再把這頁「插隊到最前面」重翻
                # （使用者要求：單張逾時直接重新插隊優先翻譯）。有重試上限避免真壞頁無限迴圈。
                await executor_instances.free_executor(instance)
                _idle = os.getenv('MT_IDLE_TIMEOUT', '30')
                _max = int(os.getenv('MT_PAGE_RETRIES', '3'))
                if task._retries < _max:
                    task._retries += 1
                    task_queue.add_task(task, priority=True)
                    if notify:
                        notify(1, f'逾時重翻（第 {task._retries}/{_max} 次）'.encode('utf-8'))
                    continue  # 回到迴圈頂端，slot 一空就立刻重新派發（插隊在最前）
                # 重試用盡 → 回錯誤 frame，讓前端自己決定要不要再排一次
                error_msg = f'翻譯逾時：worker {_idle}s 無回應，已重試 {_max} 次仍失敗。'
                if notify:
                    notify(2, error_msg.encode('utf-8'))
                    return
                else:
                    raise HTTPException(504, detail=error_msg)

            except Exception as e:
                # 确保实例被释放
                await executor_instances.free_executor(instance)

                # 如果是连接错误，发送友好的错误消息
                if "Cannot connect to host" in str(e) or "Connection refused" in str(e):
                    error_msg = "Translation service is starting up, please wait a moment and try again."
                else:
                    error_msg = f"Translation failed: {str(e)}"

                if notify:
                    notify(2, error_msg.encode('utf-8'))
                    return
                else:
                    raise HTTPException(500, detail=error_msg)
        else:
            await task_queue.wait_for_event()
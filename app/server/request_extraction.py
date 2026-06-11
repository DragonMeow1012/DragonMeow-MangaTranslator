import asyncio
import builtins
import io
import re
from base64 import b64decode
from typing import Union

import requests
from PIL import Image
from fastapi import Request, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from manga_translator import Config
from server.myqueue import task_queue, wait_in_queue, QueueElement, BatchQueueElement
from server.streaming import notify, stream

class TranslateRequest(BaseModel):
    """This request can be a multipart or a json request"""
    image: bytes|str
    """can be a url, base64 encoded image or a multipart image"""
    config: Config = Config()
    """in case it is a multipart this needs to be a string(json.stringify)"""

class BatchTranslateRequest(BaseModel):
    """Batch translation request"""
    images: list[bytes|str]
    """List of images, can be URLs, base64 encoded strings, or binary data"""
    config: Config = Config()
    """Translation configuration"""
    batch_size: int = 4
    """Batch size, default is 4"""

# 與 SDMDCBOT bot client 一致：小圖放大到 _MIN_IMG_DIM 再翻譯（inpainter/嵌字在合理
# 解析度上跑，避免糊、字級失準導致重疊爆框），超大圖縮到 _MAX_IMG_DIM（避免 OpenCV
# cv::remap 撞 SHRT_MAX）。輸出端在 _revert_upscale 依 config._orig_size 縮回原尺寸。
_MIN_IMG_DIM = 1280
_MAX_IMG_DIM = 12000


def _resize_for_translation(img: Image.Image, config: Config) -> Image.Image:
    """放大小圖 / 縮小超大圖；把原始尺寸記到 config._orig_size 供輸出還原。"""
    w, h = img.size
    cur_max = max(w, h)
    config._orig_size = (w, h)
    if _MIN_IMG_DIM <= cur_max <= _MAX_IMG_DIM:
        return img
    scale = (_MAX_IMG_DIM / cur_max) if cur_max > _MAX_IMG_DIM else (_MIN_IMG_DIM / cur_max)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.convert('RGB').resize(new_size, Image.LANCZOS)


async def to_pil_image(image: Union[str, bytes]) -> Image.Image:
    try:
        if isinstance(image, builtins.bytes):
            image = Image.open(io.BytesIO(image))
            return image
        else:
            if re.match(r'^data:image/.+;base64,', image):
                value = image.split(',', 1)[1]
                image_data = b64decode(value)
                image = Image.open(io.BytesIO(image_data))
                return image
            else:
                response = requests.get(image)
                image = Image.open(io.BytesIO(response.content))
                return image
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


async def get_ctx(req: Request, config: Config, image: str|bytes):
    image = await to_pil_image(image)
    image = _resize_for_translation(image, config)

    task = QueueElement(req, image, config, 0)
    task_queue.add_task(task)

    return await wait_in_queue(task, None)

async def while_streaming(req: Request, transform, config: Config, image: bytes | str):
    image = await to_pil_image(image)
    image = _resize_for_translation(image, config)

    task = QueueElement(req, image, config, 0)
    task_queue.add_task(task)

    messages = asyncio.Queue()

    def notify_internal(code: int, data: bytes) -> None:
        notify(code, data, transform, messages)
    streaming_response = StreamingResponse(stream(messages), media_type="application/octet-stream")
    asyncio.create_task(wait_in_queue(task, notify_internal))
    return streaming_response

async def get_batch_ctx(req: Request, config: Config, images: list[str|bytes], batch_size: int = 4):
    """Process batch translation request"""
    # Convert images to PIL Image objects
    pil_images = []
    for img in images:
        pil_img = await to_pil_image(img)
        pil_images.append(pil_img)
    
    # Create batch task
    batch_task = BatchQueueElement(req, pil_images, config, batch_size)
    task_queue.add_task(batch_task)
    
    return await wait_in_queue(batch_task, None)
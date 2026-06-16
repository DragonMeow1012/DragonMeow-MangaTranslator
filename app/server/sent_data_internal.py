import json
import os
import pickle
from typing import Mapping, Optional, Callable

import aiohttp
from PIL.Image import Image
from fastapi import HTTPException

from manga_translator import Config

NotifyType = Optional[Callable[[int, Optional[bytes]], None]]

# Idle watchdog（伺服器端「卡死偵測」）：worker 處理一頁時，除了各 pipeline 階段（detection/ocr/
# translating/inpainting/rendering）的進度 frame，還有 share.py 的「心跳」每 MT_WORKER_HEARTBEAT
# 秒重送一個 frame——只要 worker event loop 還活著（OCR 走 to_thread、LLM 純網路 await 時 loop 都空著）
# 心跳就照常。故用 sock_read（兩 byte 間最大間隔）偵測「連心跳都停了＝loop 被同步操作卡死 / 進程掛掉」。
# 預設 30s（漏掉 3 拍心跳）＝使用者要的單張逾時；逾時後 myqueue 會把該頁插隊到最前面重翻。
# **故意不用 total=**（健康的慢頁/排在 GPU 鎖後面的頁只要心跳還在就不該殺）。
_IDLE_TIMEOUT = float(os.getenv('MT_IDLE_TIMEOUT', '30'))
_STREAM_TIMEOUT = aiohttp.ClientTimeout(sock_read=_IDLE_TIMEOUT, total=None, sock_connect=30)

async def fetch_data_stream(url, image: Image, config: Config, sender: NotifyType, headers: Mapping[str, str] = {}):
    attributes = {"image": image, "config": config}
    data = pickle.dumps(attributes)

    async with aiohttp.ClientSession(timeout=_STREAM_TIMEOUT) as session:
        async with session.post(url, data=data, headers=headers) as response:
            if response.status == 200:
                await process_stream(response, sender)
            else:
                raise HTTPException(response.status, detail=await response.text())

async def fetch_data(url, image: Image, config: Config, headers: Mapping[str, str] = {}):
    attributes = {"image": image, "config": config}
    data = pickle.dumps(attributes)

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, headers=headers) as response:
            if response.status == 200:
                try:
                    return json.loads(await response.text())
                except json.JSONDecodeError:
                    raise HTTPException(502, detail='Invalid JSON response from upstream')
            else:
                raise HTTPException(response.status, detail=await response.text())

async def process_stream(response, sender: NotifyType):
    buffer = b''

    async for chunk in response.content.iter_any():
        if chunk:
            buffer += chunk
            buffer = handle_buffer(buffer, sender)



def handle_buffer(buffer, sender: NotifyType):
    while len(buffer) >= 5:
        status, expected_size = extract_header(buffer)

        if len(buffer) >= 5 + expected_size:
            data = buffer[5:5 + expected_size]
            sender(status, data)
            buffer = buffer[5 + expected_size:]
        else:
            break
    return buffer


def extract_header(buffer):
    """Extract the status and expected size from the buffer."""
    status = int.from_bytes(buffer[0:1], byteorder='big')
    expected_size = int.from_bytes(buffer[1:5], byteorder='big')
    return status, expected_size


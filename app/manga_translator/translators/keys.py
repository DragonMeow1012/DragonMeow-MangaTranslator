import os
from dotenv import load_dotenv
load_dotenv()

# Gemini（唯一保留的翻譯後端：gemini_2stage 走雲端 Gemini native）
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite')
# Vision-capable model for gemini_2stage stage 1 (OCR refinement)。
# 翻譯主力可以是任何 Gemini/Gemma 模型，但 stage 1 需要會看圖的。
GEMINI_VISION_MODEL = os.getenv('GEMINI_VISION_MODEL', 'gemini-3.1-flash-lite')

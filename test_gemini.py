import asyncio
from datetime import datetime
from app.config import load_settings
from app.parser import GeminiExtractor
import httpx

async def main():
    s = load_settings()
    ex = GeminiExtractor(s.gemini_api_key, s.gemini_model, s.tzinfo)
    try:
        res = await ex.extract('Bought a sandwich for 150', datetime.now(s.tzinfo))
        print(res)
    except httpx.HTTPStatusError as e:
        print("HTTP Error:", e.response.text)

asyncio.run(main())

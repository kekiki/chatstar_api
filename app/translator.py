import asyncio

from app.tools import get_http_client

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


class Translator:
    async def translate(self, text: str, tl="en", sl="auto") -> str:
        url = "https://translate.googleapis.com/translate_a/t"
        params = {
            "client": "dict-chrome-ex",
            "sl": sl,
            "tl": tl,
            "q": text,
        }
        client = await get_http_client()
        resp = await client.get(url, params=params, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
        if data and data[0]:
            result = data[0][0]
        else:
            result = ""
        return result


if __name__ == "__main__":
    async def _main():
        trans = Translator()
        print(await trans.translate("你好，世界！今天天气很好", tl="en"))

    asyncio.run(_main())

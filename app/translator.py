import re
import requests

class Translator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        })

    def translate(self, text: str, tl="en", sl="auto") -> str:
        url = "https://translate.googleapis.com/translate_a/t"
        params = {
            "client": "dict-chrome-ex",
            "sl": sl,
            "tl": tl,
            "q": text,
        }
        resp = self.session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data and data[0]:
            result = data[0][0]
        else:
            result = ""
        return result


if __name__ == "__main__":
    # 如果需要代理就填你的代理地址，不需要代理就传None
    trans = Translator()
    print(trans.translate("你好，世界！今天天气很好", tl="en"))
    # print(trans.translate("Hello world, nice day", tl="zh-CN"))

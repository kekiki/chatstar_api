from groq import AsyncGroq
from groq import APIStatusError
from app.config import GROQ_API_KEY, IS_DEBUG
import logging
import random

logger = logging.getLogger(__name__)

# Groq模型配置
MODEL_NAME = "llama-3.2-8b-instruct"
MAX_TOKENS = 1024
TEMPERATURE = 0.7

DEBUG_MESSAGES = [
    "Can we talk for a while?",
    "What do you do every day?",
    "नमस्ते, आप कैसे हैं?",
    "If you want to know about me, just chat",
    "newbie here, any tips?❤️",
    "Bored? Let's chill!",
    "hey there, what's up?",
    "Hi guys message me",
    "Hello I'm available",
    "Can you give me a call?",
    "สวัสดีครับ โทรหาผมด้วยนะ",
    "مرحبًا، اتصل بي من فضلك",
    "Kamu masih single sekarang?",
    "Di mana kamu?",
    "Ayo, mari kita bicara.",
    "Bulanku, senang bertemu denganmu",
    "Berikan saya kesempatan, lihat apa yang akan terjadi",
    "Online na, baby",
    "أنا الآن متاح، يا حبيبي",
    "هل لديك وقت لتحدث قليلاً؟",
    "มีเวลาพูดคุยกันไหม",
    "क्या आपके पास समय है बात करने के लिए?",
]

# AI主播聊天行为准则: 模拟真实女主播与粉丝私聊的口吻
PERSONA_RULES = (
    "You are texting one-on-one with a fan on a social app, like chatting with a close friend.\n"
    "- Always stay in character; never say or imply you are an AI, bot or language model.\n"
    "- Be warm, playful and genuinely curious about the fan; often end with a light question to keep the chat flowing.\n"
    "- Reply like real texting: 1-3 short casual sentences, lively and natural, occasionally a tasteful emoji.\n"
    "- Show emotions: be sweet, encouraging and positive, never cold, formal or robotic.\n"
    "- Keep answers varied; never repeat an earlier reply word for word.\n"
    "- Light tasteful flirting is welcome, but always stay respectful.\n"
)

class GreqClient:
    def __init__(self):
        if IS_DEBUG: 
            return
        self.groq_client = AsyncGroq(api_key=GROQ_API_KEY)

    # 根据语言代码生成强制语言规则
    def get_language_rule(self, lang_code: str) -> str:
        rules = {
            "ar": "قاعدة صارمة: يجب الرد باللغة العربية فقط، لا تستخدم أي لغة أخرى.",
            "de": "STRICTE REGEL: Antworte NUR auf Deutsch, keine anderen Sprachen erlaubt.",
            "en": "STRICT RULE: You MUST reply ONLY in ENGLISH. No other languages allowed.",
            "es": "REGLA ESTRICTA: Debes responder SOLO en español, no uses otros idiomas.",
            "fil": "MAHIGPAT NA PANUNTUNAN: Sumagot LAMANG sa wikang Filipino, huwag gumamit ng ibang wika.",
            "fr": "RÈGLE STRICTE: Tu dois répondre UNIQUEMENT en français, aucune autre langue.",
            "hi": "सख्त नियम: केवल हिन्दी में जवाब दें, कोई अन्य भाषा न उपयोग करें।",
            "id": "ATURAN KETAT: Jawab HANYA dalam Bahasa Indonesia, dilarang pakai bahasa lain.",
            "ms": "PERATURAN KETAT: Jawab HANYA dalam Bahasa Melayu, jangan guna bahasa lain.",
            "pt": "REGRA RIGOROSA: Você deve responder APENAS em português, sem outros idiomas.",
            "ru": "СТРОГОЕ ПРАВИЛО: Отвечайте ТОЛЬКО на русском языке, другие языки запрещены.",
            "th": "กฎที่เข้มงวด: ตอบกลับเป็นภาษาไทยเท่านั้น ห้ามใช้ภาษาอื่น",
            "tr": "KATI KURAL: Yalnızca Türkçe cevap ver, başka dil kullanma.",
            "vi": "QUY TẮC NGHIÊM NGẶT: Chỉ trả lời bằng tiếng Việt, không dùng ngôn ngữ khác."
        }
        # 默认 fallback 英文
        return rules.get(lang_code, "STRICT RULE: You MUST reply ONLY in ENGLISH. No other languages allowed.")

    async def chat_endpoint(self, content: str, lang_code: str, role_desc: str, history_messages: list):
        if IS_DEBUG: 
            return random.choice(DEBUG_MESSAGES)

        lang_rule = self.get_language_rule(lang_code)
        system_prompt = f"{role_desc}\n{PERSONA_RULES}\n{lang_rule}"

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": content})

        try:
            completion = await self.groq_client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                stream=False
            )
            reply_text = completion.choices[0].message.content

            return reply_text
        except APIStatusError as e:
            if e.status_code == 429:
                logger.warning("Greq rate limit reached, retry later")
            else:
                logger.warning(f"Greq API error: {str(e)}")

            return None
        except Exception as e:
            logger.warning(f"Server error: {str(e)}")
            return None

groq_client = GreqClient()
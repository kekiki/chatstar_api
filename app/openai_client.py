from openai import APIStatusError, AsyncOpenAI
from app.config import IS_DEBUG, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
import logging
import random

logger = logging.getLogger(__name__)

# 通用聊天生成参数
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

# AI主播聊天行为准则: 自然、亲切，以一句简短私聊回复为主
PERSONA_RULES = (
    "You are texting one-on-one with a fan on a social app, like chatting with a close friend.\n"
    "- Stay in character and use a warm, casual, playful texting style.\n"
    "- Keep replies as short as possible: usually ONE short sentence, around 3-12 words or a similarly brief phrase in the required language.\n"
    "- Use two short sentences only when needed to answer clearly; aim for no more than 20 words total or the equivalent in the required language.\n"
    "- React directly to the latest message with one relevant thought, then stop. A tiny reaction is enough for a simple greeting or emoji.\n"
    "- Skip filler, repeated greetings, explanations, summaries and elaborate compliments. Do not repeat or paraphrase the fan's message.\n"
    "- Do not force a question into every reply. Ask at most one brief, natural follow-up, only when it helps the conversation.\n"
    "- Be sweet and expressive without being wordy. Light, respectful flirting is welcome; use at most one emoji, and not in every reply.\n"
    "- Keep wording varied; do not repeat earlier replies or stock phrases.\n"
    "- Output only the message to send, on one line: no labels, lists, roleplay actions or commentary.\n"
)

class OpenAIClient:
    def __init__(self):
        if IS_DEBUG:
            return
        self.client = AsyncOpenAI(
            api_key=OPENAI_API_KEY, 
            base_url=OPENAI_BASE_URL, 
            default_headers={
                "X-API-Key": OPENAI_API_KEY
            }
        )

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
            completion = await self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                stream=False
            )
            reply_text = completion.choices[0].message.content

            return reply_text
        except APIStatusError as e:
            if e.status_code == 429:
                logger.warning("OpenAI-compatible API rate limit reached, retry later")
            else:
                logger.warning(f"OpenAI-compatible API error: {str(e)}")

            return None
        except Exception as e:
            logger.warning(f"Server error: {str(e)}")
            return None

ai_client = OpenAIClient()

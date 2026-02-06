import requests
import json
from groq import Groq  # ใช้ Groq แทน Gemini
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# --- [1] CONFIGURATION ---
THINGSBOARD_HOST = 'https://demo.thingsboard.io'
USERNAME = 'nexsterd2015@gmail.com'
PASSWORD = '8Cvv8FGjYRLK@Cr' 
DEVICE_ID = 'b208e720-e259-11f0-869d-9726f60f35d2'

# ใส่ API Key ของ Groq ที่นี่
GROQ_API_KEY = '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'
TELEGRAM_TOKEN = '8373253714:AAHW04WkBbdFemQnOD_GJ1lD7sRMlKAaris'

# เริ่มใช้งาน Groq Client
client = Groq(api_key=GROQ_API_KEY)
MODEL_ID = "llama-3.3-70b-versatile" # โมเดลตัวท็อปที่ฉลาดและฟรี

# --- [2] FUNCTIONS ---
def get_tb_data():
    try:
        auth_res = requests.post(f"{THINGSBOARD_HOST}/api/auth/login", 
                                 json={"username": USERNAME, "password": PASSWORD}, timeout=10)
        auth_res.raise_for_status()
        token = auth_res.json().get('token')
        
        headers = {'X-Authorization': f'Bearer {token}'}
        data_res = requests.get(f"{THINGSBOARD_HOST}/api/plugins/telemetry/DEVICE/{DEVICE_ID}/values/timeseries", 
                                headers=headers, timeout=10)
        data_res.raise_for_status()
        
        raw = data_res.json()
        clean_data = {k: v[0].get('value') for k, v in raw.items() if v}
        return clean_data
    except Exception as e:
        print(f"❌ Error ThingsBoard: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    latest_data = get_tb_data()
    user_query = update.message.text

    try:
        # การเรียกใช้งาน AI ผ่าน Groq
        completion = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "คุณคือ 'น้องไฟดี' ผู้เชี่ยวชาญ Smart ATS ตอบเป็นภาษาไทยที่สุภาพและเป็นกันเอง"},
                {"role": "user", "content": f"ข้อมูลไฟฟ้าล่าสุด: {json.dumps(latest_data)}\nคำถาม: {user_query}"}
            ],
            temperature=0.7,
        )
        
        response_text = completion.choices[0].message.content
        await update.message.reply_text(response_text)
        
    except Exception as e:
        print(f"❌ Groq Error: {e}")
        await update.message.reply_text("⚠️ น้องไฟดีขออภัย ระบบประมวลผลขัดข้องครับ")

# --- [3] START ---
if __name__ == '__main__':
    print("---------------------------------")
    print("🚀 'น้องไฟดี' (Groq Version) เริ่มทำงาน")
    print("💬 พร้อมให้บริการบน Telegram แล้ว")
    print("---------------------------------")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()
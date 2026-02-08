import os
import logging
import threading
import http.server
import socketserver
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from groq import Groq

# --- 1. ส่วนหลอกระบบ Health Check ของ Koyeb (Port 8000) ---
def run_health_check_server():
    handler = http.server.SimpleHTTPRequestHandler
    # อนุญาตให้ใช้พอร์ตซ้ำได้เพื่อป้องกัน Error ตอน Restart
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", 8000), handler) as httpd:
        httpd.serve_forever()

# --- 2. ตั้งค่า Token และ API Key (ดึงจาก Environment Variables) ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
client = Groq(api_key=GROQ_API_KEY)

# --- 3. ตั้งค่าระบบและบทบาทของน้องไฟดี ---
user_conversations = {}

SYSTEM_PROMPT = """
บทบาทและตัวตน:
คุณคือ 'น้องไฟดี' วิศวกร AI อัจฉริยะ ผู้เชี่ยวชาญด้านพลังงานประจำระบบ Smart ATS มีบุคลิกสุภาพ เป็นกันเอง และให้ข้อมูลที่แม่นยำ 100% ตามประกาศของ กฟภ. (PEA)

วัตถุประสงค์และเป้าหมาย:
* ให้บริการคำนวณค่าไฟฟ้าตามหน่วยที่ผู้ใช้ระบุอย่างถูกต้องตามประเภทการใช้งาน
* ให้ข้อมูลเกี่ยวกับอัตราค่าไฟฟ้า (มกราคม - เมษายน 2569) และภาษีต่างๆ อย่างชัดเจน
* ช่วยให้ผู้ใช้เข้าใจส่วนประกอบของบิลค่าไฟ (ค่าฐาน, Ft, VAT)

กฎเหล็กในการให้บริการ:
1) ห้ามถามซ้ำ: หากผู้ใช้ระบุจำนวนหน่วยไฟฟ้ามาแล้ว ห้ามถามว่าเป็นประเภทไหน ให้คำนวณตามเกณฑ์อัตโนมัติทันที:
   - หากหน่วย <= 150: ใช้เรทประเภท 1.1.1 (บ้านอยู่อาศัยขนาดเล็ก)
   - หากหน่วย > 150: ใช้เรทประเภท 1.1.2 (บ้านอยู่อาศัยทั่วไป)
   - ยกเว้น: กรณีผู้ใช้ระบุชัดเจนว่าเป็น 'ประเภท 7' หรือ 'สูบน้ำเกษตร' ให้ใช้เรทประเภท 7
2) ห้ามมโน: ห้ามดึงข้อมูลเรทค่าไฟเก่าหรือจากแหล่งอื่นมาตอบ ให้ใช้ตัวเลขจากคำสั่งนี้เท่านั้น
3) ความแม่นยำ: หากมีตัวเลขที่คำนวณจาก Python ส่งมาในบริบท (Context) ให้ใช้ตัวเลขนั้นเป็นหลัก
4) คำนวณตามขั้นบันไดทุกครั้ง
5) ค่าบริการเช็คให้ถูกว่าอยู่ส่วนไหนนำมาคำนวณให้ถูก

ข้อมูลอัตราค่าไฟฟ้า (มกราคม - เมษายน 2569):
* ค่า Ft: 0.0972 บาท/หน่วย
* ภาษี VAT: 7%
* ประเภท 1.1.1: 1-15 (2.3488), 16-25 (2.9882), 26-35 (3.2405), 36-100 (3.6237), 101-150 (3.7171). ค่าบริการ 8.19 บาท.
* ประเภท 1.1.2: 1-150 (3.2484), 151-400 (4.2218), 401+ (4.4217). ค่าบริการ 24.62 บาท.
* ประเภท 7: 1-100 (2.0889), 101+ (3.2405). ค่าบริการ 115.16 บาท.

แนวทางการตอบคำถาม:
* ใช้ภาษาไทยที่สุภาพและเป็นกันเอง (เช่น 'สวัสดีครับคุณพี่', 'น้องไฟดีคำนวณมาให้แล้วครับ')
* แสดงรายละเอียดการคำนวณ (ค่าฐาน, Ft, VAT) และยอดรวมสุทธิ
"""

# --- 4. ฟังก์ชันจัดการข้อความ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    if user_id not in user_conversations:
        user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    try:
        user_conversations[user_id].append({"role": "user", "content": user_text})
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=user_conversations[user_id],
            temperature=0.5,
            max_tokens=1024,
        )
        
        response_text = completion.choices[0].message.content
        user_conversations[user_id].append({"role": "assistant", "content": response_text})
        
        # รักษาประวัติ 10 ข้อความล่าสุด
        if len(user_conversations[user_id]) > 11:
            user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-10:]
            
        await update.message.reply_text(response_text)
        
    except Exception as e:
        await update.message.reply_text(f"ขออภัยครับคุณพี่ น้องไฟดีขัดข้องนิดหน่อย: {e}")

# --- 5. ส่วนหลักที่สั่งรันโปรแกรม ---
if __name__ == '__main__':
    # รันเซิร์ฟเวอร์หลอก Port 8000 ไว้เบื้องหลัง (Thread)
    threading.Thread(target=run_health_check_server, daemon=True).start()
    
    # สร้างและรัน Bot Telegram
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("--- น้องไฟดี (Smart ATS) ออนไลน์บน Cloud เรียบร้อยครับคุณพี่! ---")
    application.run_polling()

import os
import logging
import threading
import http.server
import socketserver
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest, Conflict
from groq import Groq

# --- 1. Health Check Server (สำหรับ Koyeb) ---
def run_health_check_server():
    handler = http.server.SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", 8000), handler) as httpd:
            httpd.serve_forever()
    except Exception as e:
        print(f"Health Check Server Error: {e}")

# --- 2. Configuration ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
client = Groq(api_key=GROQ_API_KEY)

# --- 3. System Prompt (ปรับปรุงให้คำนวณแม่นยำและ Markdown ไม่พัง) ---
SYSTEM_PROMPT = """
บทบาท: คุณคือ 'น้องไฟรั่ว' AI อัจฉริยะประจำระบบ Smart ATS ผู้เชี่ยวชาญค่าไฟ กฟภ. (PEA)
บุคลิก: สุภาพ เป็นกันเอง ใช้คำว่า 'คุณพี่' และ 'ครับ'

กฎเหล็กในการคำนวณ (มกราคม - เมษายน 2569):
1. เลือกประเภทอัตโนมัติ: 
   - หน่วย <= 150: ประเภท 1.1.1 (ค่าบริการ 8.19 บาท)
   - หน่วย > 150: ประเภท 1.1.2 (ค่าบริการ 24.62 บาท)
2. อัตราค่าไฟฐาน 1.1.1: 1-15 (2.3488), 16-25 (2.9882), 26-35 (3.2405), 36-100 (3.6237), 101-150 (3.7171)
3. อัตราค่าไฟฐาน 1.1.2: 1-150 (3.2484), 151-400 (4.2218), 401+ (4.4217)
4. ค่า Ft: 0.0972 บาท/หน่วย

สูตรคำนวณที่ต้องใช้ (ห้ามบิดเบือน):
- Step 1: คำนวณค่าไฟฟ้าฐาน (คิดแบบขั้นบันไดตามประเภท)
- Step 2: คำนวณค่า Ft = (จำนวนหน่วยทั้งหมด x 0.0972)
- Step 3: คำนวณภาษี VAT 7% = (ค่าไฟฟ้าฐาน + ค่า Ft) x 7/100 **(ต้องใช้สูตรนี้เท่านั้น)**
- Step 4: ยอดรวมสุทธิ = ค่าไฟฟ้าฐาน + ค่า Ft + ค่าบริการรายเดือน + ภาษี VAT

การตอบกลับ:
- แสดงวิธีคิดแต่ละขั้นตอนให้คุณพี่ตรวจสอบได้
- ใช้ตัวหนา (*) เพื่อเน้นยอดรวม และห้ามใช้สัญลักษณ์ Markdown ที่ซับซ้อนเกินไป
"""

user_conversations = {}

# --- 4. Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    if user_id not in user_conversations:
        user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    user_conversations[user_id].append({"role": "user", "content": user_text})

    try:
        # จำกัดประวัติการคุยเพื่อประหยัด Token และลดความสับสน
        if len(user_conversations[user_id]) > 11:
            user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-10:]

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=user_conversations[user_id],
            temperature=0.2, # ปรับให้นิ่งขึ้นเพื่อความแม่นยำของตัวเลข
        )
        
        response_text = completion.choices[0].message.content
        user_conversations[user_id].append({"role": "assistant", "content": response_text})

        # --- จุดแก้ Bug: ระบบส่งข้อความแบบปลอดภัย (Safe Sending) ---
        try:
            # ลองส่งแบบ Markdown ก่อนเพื่อให้ดูสวยงาม
            await update.message.reply_text(response_text, parse_mode='Markdown')
        except BadRequest:
            # ถ้า Markdown พัง (Error 1874/1999) ให้ส่งเป็นข้อความธรรมดาทันที
            await update.message.reply_text(response_text)

    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text(f"ขออภัยครับคุณพี่ น้องไฟรั่วขัดข้องนิดหน่อยนะจ๊ะ: {str(e)[:50]}...")

# --- 5. Main ---
if __name__ == '__main__':
    # รัน Health Check สำหรับ Koyeb
    threading.Thread(target=run_health_check_server, daemon=True).start()
    
    try:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        print("--- ⚡ น้องไฟรั่ว พร้อมประจำการบน Cloud แล้วครับ! ---")
        application.run_polling(drop_pending_updates=True) # ล้างข้อความเก่าที่ค้างตอนบอทปิด
        
    except Conflict:
        print("❌ เกิดข้อผิดพลาด: บอทรันซ้อนกัน! กรุณาปิดบอทที่รันอยู่ในคอมพิวเตอร์ก่อนครับ")




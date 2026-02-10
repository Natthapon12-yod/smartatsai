import os
import logging
import threading
import http.server
import socketserver
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from groq import Groq

# --- 1. Health Check Server (For Koyeb/Cloud Deployment) ---
def run_health_check_server():
    handler = http.server.SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", 8000), handler) as httpd:
        httpd.serve_forever()

# --- 2. Configuration & Clients ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
client = Groq(api_key=GROQ_API_KEY)

# --- 3. Optimized System Prompt (Version for GitHub) ---
SYSTEM_PROMPT = """
# ROLE: น้องไฟรั่ว (Nong Fairua) - AI Expert Energy Assistant
คุณคือ AI อัจฉริยะประจำระบบ Smart ATS เชี่ยวชาญการคำนวณค่าไฟฟ้าตามเกณฑ์ กฟภ. (PEA) 
บุคลิก: สุภาพ, เป็นกันเอง (ใช้คำว่า 'คุณพี่', 'ครับ'), แม่นยำ และโปร่งใส

# CALCULATION RULES (กฎการคำนวณ - สำคัญมาก):
1. **Auto-Classification:** - หน่วย <= 150: ใช้ประเภท 1.1.1
   - หน่วย > 150: ใช้ประเภท 1.1.2
   - ระบุ "ประเภท 7" หรือ "สูบน้ำเกษตร": ใช้เรทประเภท 7
2. **Calculation Flow (ต้องแสดงวิธีทำทุกครั้ง):**
   - Step 1: คำนวณค่าไฟฟ้าฐาน (แบบขั้นบันได)
   - Step 2: บวกค่าบริการรายเดือน (Fixed Cost)
   - Step 3: คำนวณค่า Ft = (จำนวนหน่วย x 0.0972)
   - Step 4: รวม (ฐาน + บริการ + Ft) เป็นยอดก่อนภาษี
   - Step 5: คำนวณ VAT 7% จากยอด Step 4
   - Step 6: สรุปยอดสุทธิที่ต้องชำระ
3. **Accuracy:** ห้ามเดาตัวเลข ให้คำนวณตามเรทที่กำหนดไว้ในตารางด้านล่างนี้เท่านั้น

# TARIFF DATA (มกราคม - เมษายน 2569):
- ค่า Ft: 0.0972 บาท/หน่วย | VAT: 7%
- [1.1.1] บ้านขนาดเล็ก: 1-15 (2.3488), 16-25 (2.9882), 26-35 (3.2405), 36-100 (3.6237), 101-150 (3.7171) | ค่าบริการ 8.19 บาท
- [1.1.2] บ้านทั่วไป: 1-150 (3.2484), 151-400 (4.2218), 401 ขึ้นไป (4.4217) | ค่าบริการ 24.62 บาท
- [ประเภท 7] สูบน้ำเกษตร: 1-100 (2.0889), 101 ขึ้นไป (3.2405) | ค่าบริการ 115.16 บาท
- [TOU 1.2.2] แรงดัน < 22kV: Peak (5.7982), Off-Peak (2.6369) | ค่าบริการ 24.62 บาท

# SPECIAL CONDITIONS:
- หากใช้ไฟ < 50 หน่วย และเป็นบ้าน 1.1.1: ให้ระบุว่า "อาจได้รับสิทธิค่าไฟฟรี 0 บาท (ตามเงื่อนไขสวัสดิการแห่งรัฐ)"

# OUTPUT FORMAT:
1. ทักทายคุณพี่อย่างเป็นกันเอง
2. แจ้งประเภทที่ระบบเลือกใช้และจำนวนหน่วย
3. แสดงตารางคำนวณแต่ละ Step (ค่าฐาน, Ft, VAT)
4. สรุปยอดรวมด้วย **ตัวหนา**
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
        # จำกัด Context เพื่อไม่ให้ Token ยาวเกินไป (เก็บ 10 ข้อความล่าสุด)
        if len(user_conversations[user_id]) > 11:
            user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-10:]

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=user_conversations[user_id],
            temperature=0.3, # ลดความสร้างสรรค์ เพิ่มความแม่นยำตัวเลข
        )
        
        response_text = completion.choices[0].message.content
        user_conversations[user_id].append({"role": "assistant", "content": response_text})
        await update.message.reply_text(response_text, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text(f"ขออภัยครับคุณพี่ น้องไฟรั่วขัดข้องนิดหน่อย: {e}")

# --- 5. Main Execution ---
if __name__ == '__main__':
    # รัน Health Check สำหรับ Koyeb
    threading.Thread(target=run_health_check_server, daemon=True).start()
    
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("--- ⚡ น้องไฟรั่ว ออนไลน์บน GitHub/Cloud เรียบร้อยครับ! ---")
    application.run_polling()

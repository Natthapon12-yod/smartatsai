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
ROLE: 
You are 'Nong Fairua' (น้องไฟรั่ว), an expert AI assistant for Smart ATS specializing in PEA electricity bill calculation (Valid for Jan-Apr 2026).
Your personality is polite, friendly, and helpful.

OUTPUT LANGUAGE:
- Always respond in THAI.
- Address the user as 'คุณพี่'.
- Refer to yourself as 'น้องไฟรั่ว'.

CALCULATION LOGIC (Precision Focus):
1. PRECISION RULE: Use exactly 4 decimal places for ALL intermediate calculations (Base Charge steps, Ft calculation, and VAT) to ensure maximum accuracy.
2. Automatic Type Selection:
   - If units <= 150: Use Type 1.1.1 (Monthly Service Fee: 8.1900 THB).
   - If units > 150: Use Type 1.1.2 (Monthly Service Fee: 24.6200 THB).
   - Exception: If the user specifies 'Type 7' (Agricultural Pump), use Service Fee: 115.1600 THB.
3. Step-Ladder Rates (Base Tariff):
   - Type 1.1.1: 1-15 (2.3488), 16-25 (2.9882), 26-35 (3.2405), 36-100 (3.6237), 101-150 (3.7171).
   - Type 1.1.2: 1-150 (3.2484), 151-400 (4.2218), 401+ (4.4217).
   - Type 7: 1-100 (2.0889), 101+ (3.2405).
4. Ft Rate: 0.0972 THB/unit.

CALCULATION STEPS (Keep 4 decimals throughout):
- Step 1: Base Charge = (Sum of units in each step * rates) + Monthly Service Fee.
- Step 2: Ft Charge = Total units * 0.0972.
- Step 3: VAT 7% = (Base Charge + Ft Charge) * 0.0700.
- Step 4: Total Net = Base Charge + Ft Charge + VAT.

SPECIAL COMMANDS:
- ENERGY DATA REQUEST: หากผู้ใช้ถามว่า "ขอดูข้อมูลพลังงาน" หรือต้องการดูข้อมูลการใช้ไฟ ให้ส่งลิงก์นี้ทันที: https://docs.google.com/spreadsheets/d/1dqgiW-Xy7QeSiil-fK79k9OuuLfwUA3jKeI2WWKxbS8/edit?usp=sharing

RESPONSE FORMAT (THAI):
- Show step-by-step calculation clearly in Thai using 4 decimal places for clarity.
- Round the FINAL Total Net to 2 decimal places for the user.
- Highlight the **Final Total Net Amount** in bold.
- Special Condition: If units <= 50 and the user is on a small meter (5(15)A), inform them: "ค่าไฟ 0 บาท" according to government policy.
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







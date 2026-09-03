import os
import sys
import time

from musicbot_core import run_bot

# ==============================================================================
# ไฟล์นี้ใช้สำหรับ deploy ขึ้น Railway (หรือโฮสต์ Linux อื่นๆ) ให้รันบอท 24 ชั่วโมง
# โดยไม่ต้องเปิดหน้าต่าง GUI ใดๆ — อ่าน Bot Token จาก Environment Variable แทน
# ==============================================================================

RETRY_DELAY_SECONDS = 10


def main():
    token = os.environ.get("DISCORD_TOKEN") or os.environ.get("TOKEN")
    if not token:
        print("❌ ไม่พบ Bot Token! กรุณาตั้งค่า Environment Variable ชื่อ 'DISCORD_TOKEN' ใน Railway ก่อนนะ")
        print("   ไปที่ Project -> Variables -> New Variable -> ใส่ชื่อ DISCORD_TOKEN และวาง Token ของบอท")
        sys.exit(1)

    print("🚀 กำลังเริ่มบอทแบบรัน 24 ชั่วโมงบน Railway...")

    while True:
        try:
            run_bot(token)
        except Exception as e:
            print(f"[Fatal] เกิดข้อผิดพลาดร้ายแรง: {e}")

        print(f"[Restart] บอทหยุดทำงาน กำลังลองเชื่อมต่อใหม่ใน {RETRY_DELAY_SECONDS} วินาที...")
        time.sleep(RETRY_DELAY_SECONDS)


if __name__ == "__main__":
    main()

import sys
import os
import json
import threading
import queue as py_queue
import subprocess
import customtkinter as ctk

from musicbot_core import run_bot, request_stop_bot

# ==============================================================================
# หน้าต่างโปรแกรม GUI สำหรับ Windows (ใช้รันบอทบนเครื่องตัวเอง)
# ถ้าต้องการรันแบบ 24 ชั่วโมงบน Railway ให้ใช้ railway_bot.py แทนไฟล์นี้
# ==============================================================================

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MusicBotGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Discord Music Bot Launcher")
        self.geometry("550x450")
        self.resizable(False, False)

        if os.path.exists("icon.ico"):
            try:
                self.iconbitmap("icon.ico")
                import ctypes
                myappid = 'veloxgg.musicbot.launcher.v1'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        self.bot_thread = None
        self.is_running = False
        self.log_queue = py_queue.Queue()

        self.create_widgets()
        self.load_token()
        self.after(100, self.update_logs)

    def load_token(self):
        token_file = "config.json"
        if os.path.exists(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "token" in data:
                        self.token_entry.insert(0, data["token"])
            except Exception:
                pass

    def save_token(self, token):
        token_file = "config.json"
        data = {}
        if os.path.exists(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        data["token"] = token

        try:
            with open(token_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def create_widgets(self):
        self.title_label = ctk.CTkLabel(self, text="Discord Music Bot", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(pady=(20, 10))

        self.token_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.token_frame.pack(fill="x", padx=30, pady=10)

        self.token_label = ctk.CTkLabel(self.token_frame, text="Bot Token:", font=ctk.CTkFont(size=14))
        self.token_label.pack(side="left", padx=(0, 10))

        self.token_entry = ctk.CTkEntry(self.token_frame, placeholder_text="วาง Token บอทของคุณที่นี่...", width=300, show="*")
        self.token_entry.pack(side="left", fill="x", expand=True)

        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.pack(fill="x", padx=30, pady=(10, 20))

        self.start_btn = ctk.CTkButton(self.button_frame, text="▶ Start Bot", fg_color="green", hover_color="darkgreen", command=self.start_bot)
        self.start_btn.pack(side="left", expand=True, padx=(0, 10))

        self.stop_btn = ctk.CTkButton(self.button_frame, text="⏹ Stop Bot", fg_color="red", hover_color="darkred", state="disabled", command=self.stop_bot)
        self.stop_btn.pack(side="right", expand=True, padx=(10, 0))

        self.update_btn = ctk.CTkButton(self, text="🔄 Update YouTube DL (แก้บั๊กเปิดเพลงไม่ได้)",
                                         fg_color="transparent", border_width=1, text_color="gray", command=self.update_ytdlp)
        self.update_btn.pack(pady=(0, 10))

        self.log_label = ctk.CTkLabel(self, text="Console Logs:", font=ctk.CTkFont(size=12, weight="bold"))
        self.log_label.pack(padx=30, anchor="w")

        self.log_box = ctk.CTkTextbox(self, width=500, height=150, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.pack(padx=30, pady=(0, 20))
        self.log_box.insert("0.0", "ระบบพร้อมทำงาน รอคำสั่ง Start...\n")
        self.log_box.configure(state="disabled")

        self.redirect_stdout()

    def write_log(self, text):
        self.log_queue.put(text)

    def redirect_stdout(self):
        class StdoutRedirector:
            def __init__(self, text_widget, queue_ref):
                self.queue = queue_ref

            def write(self, string):
                if string.strip():
                    self.queue.put(string)

            def flush(self):
                pass

        sys.stdout = StdoutRedirector(self.log_box, self.log_queue)
        sys.stderr = StdoutRedirector(self.log_box, self.log_queue)

    def update_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"{msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self.update_logs)

    def update_ytdlp(self):
        self.write_log("กำลังดาวน์โหลดแพทช์อัปเดต YouTube DL ล่าสุด รอสักครู่...")
        self.update_btn.configure(state="disabled")

        def run_update():
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-U", "https://github.com/yt-dlp/yt-dlp/archive/master.zip"],
                    check=True, capture_output=True, text=True
                )
                self.write_log("✅ อัปเดต YouTube DL สำเร็จแล้ว!")
            except Exception as e:
                self.write_log(f"❌ เกิดข้อผิดพลาดในการอัปเดต: {e}")
            finally:
                self.update_btn.configure(state="normal")

        threading.Thread(target=run_update, daemon=True).start()

    def start_bot(self):
        token = self.token_entry.get().strip()
        if not token:
            self.write_log("❌ กรุณาใส่ Bot Token ก่อนเริ่มการทำงาน!")
            return

        self.save_token(token)

        self.is_running = True
        self.start_btn.configure(state="disabled")
        self.token_entry.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.write_log("กำลังเริ่มทำงานของบอท...")

        def bot_runner():
            try:
                run_bot(token)
            except Exception as e:
                self.write_log(f"Bot Thread Error: {e}")
                self.on_bot_stopped()

        self.bot_thread = threading.Thread(target=bot_runner, daemon=True)
        self.bot_thread.start()

    def on_bot_stopped(self):
        self.is_running = False
        self.start_btn.configure(state="normal")
        self.token_entry.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def stop_bot(self):
        self.write_log("กำลังส่งสัญญาณให้บอทออกจากระบบอย่างนุ่มนวล...")
        request_stop_bot()
        self.on_bot_stopped()
        self.write_log("✅ บอทหยุดทำงานแล้ว!")


if __name__ == "__main__":
    app = MusicBotGUI()
    app.mainloop()

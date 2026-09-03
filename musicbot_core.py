import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp as youtube_dl
import asyncio
import threading
import os
import json
import random

# ==============================================================================
# ส่วนที่ 1: การตั้งค่า yt-dlp / ffmpeg
# ==============================================================================

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _validate_cookie_file(path):
    """เช็คคร่าวๆ ว่าไฟล์ cookies หน้าตาถูกต้องตามฟอร์แมต Netscape ไหม (ป้องกัน tab เพี้ยนตอน copy-paste)"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if "# Netscape HTTP Cookie File" not in content and "# HTTP Cookie File" not in content:
            print("[Cookies] ⚠️ ไฟล์ cookies ไม่มีบรรทัดหัวไฟล์ตามมาตรฐาน Netscape "
                  "อาจไม่ใช่ไฟล์ cookies.txt ที่ถูกต้อง")
        # แถวข้อมูลจริงของ Netscape cookie ต้องคั่นด้วย TAB (\t) ไม่ใช่ space
        data_lines = [ln for ln in content.splitlines() if ln and not ln.startswith("#")]
        if data_lines and not any("\t" in ln for ln in data_lines):
            print("[Cookies] ⚠️ ไม่พบตัวคั่น TAB ในไฟล์ cookies — ไฟล์อาจเพี้ยนจากการ copy-paste "
                  "(tab ถูกแปลงเป็น space) แนะนำให้ใช้วิธีตั้งค่าแบบ Base64 (YTDLP_COOKIES_B64) แทน")
            return False
        return True
    except Exception as e:
        print(f"[Cookies] ⚠️ ตรวจสอบไฟล์ cookies ไม่สำเร็จ: {e}")
        return False


def _resolve_cookies_file():
    """
    หาไฟล์ cookies.txt สำหรับให้ yt-dlp ใช้ยืนยันตัวตนกับ YouTube
    (จำเป็นมากเมื่อรันบนโฮสต์คลาวด์อย่าง Railway ที่มักโดน YouTube บล็อกว่าเป็นบอท)

    รองรับ 3 วิธี เรียงตามลำดับความสำคัญ:
    1. YTDLP_COOKIES_B64 — เนื้อหาไฟล์ cookies.txt เข้ารหัส Base64 (แนะนำที่สุดสำหรับ Railway
       เพราะกันปัญหา tab ถูกแปลงเป็น space ตอน copy-paste ลงกล่อง Variables)
    2. YTDLP_COOKIES — เนื้อหาไฟล์ cookies.txt แบบข้อความตรงๆ
    3. ไฟล์ cookies.txt ที่วางไว้ในโฟลเดอร์โปรเจกต์เอง
    """
    cookie_path = os.path.join(_BASE_DIR, "cookies.txt")

    cookies_b64 = os.environ.get("YTDLP_COOKIES_B64")
    if cookies_b64:
        try:
            import base64
            raw = base64.b64decode(cookies_b64.strip()).decode("utf-8")
            with open(cookie_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(raw)
            if _validate_cookie_file(cookie_path):
                print("[Cookies] ✅ โหลด cookies จาก YTDLP_COOKIES_B64 แล้ว (ผ่านการตรวจสอบฟอร์แมต)")
            return cookie_path
        except Exception as e:
            print(f"[Cookies] ⚠️ ถอดรหัส Base64 จาก YTDLP_COOKIES_B64 ไม่สำเร็จ: {e}")

    cookies_env = os.environ.get("YTDLP_COOKIES")
    if cookies_env:
        try:
            with open(cookie_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(cookies_env)
            if _validate_cookie_file(cookie_path):
                print("[Cookies] ✅ โหลด cookies จาก Environment Variable YTDLP_COOKIES แล้ว")
            else:
                print("[Cookies] ⚠️ cookies จาก YTDLP_COOKIES ดูเหมือนจะเพี้ยน "
                      "ลองเปลี่ยนไปใช้ YTDLP_COOKIES_B64 แทน (ดูวิธีใน README)")
            return cookie_path
        except Exception as e:
            print(f"[Cookies] ⚠️ เขียนไฟล์ cookies จาก YTDLP_COOKIES ไม่สำเร็จ: {e}")

    if os.path.exists(cookie_path):
        if _validate_cookie_file(cookie_path):
            print("[Cookies] ✅ พบไฟล์ cookies.txt ในโปรเจกต์ ใช้ยืนยันตัวตนกับ YouTube")
        return cookie_path

    print("[Cookies] ℹ️ ไม่พบ cookies.txt — ถ้าเจอ error 'Sign in to confirm you're not a bot' ให้ตั้งค่า cookies ตามคำแนะนำใน README")
    return None


_COOKIES_FILE = _resolve_cookies_file()
_PROXY_URL = os.environ.get("YTDLP_PROXY")


def _resolve_ffmpeg_executable():
    """
    หา path ของโปรแกรม ffmpeg ที่จะใช้เล่นเสียง เรียงตามลำดับความสำคัญ:
    1. Environment Variable FFMPEG_PATH — ถ้าตั้งไว้ให้ใช้ path นั้นตรงๆ (เผื่อกรณีติดตั้งไว้ตำแหน่งพิเศษ)
    2. ffmpeg ที่มีอยู่ใน PATH ของระบบอยู่แล้ว (หาโดย shutil.which)
    3. ffmpeg แบบ static binary จากไลบรารี imageio-ffmpeg (ติดตั้งผ่าน pip)
       วิธีนี้ช่วยแก้ปัญหา "ffmpeg was not found" ได้เกือบทุกกรณี เพราะไม่ต้องพึ่ง PATH ของระบบเลย
       ไม่ว่าจะรันบน Windows (ที่บางทีติดตั้ง ffmpeg ไม่สำเร็จ/ไม่รีเฟรช PATH) หรือ Railway
    ถ้าหาไม่เจอเลยจริงๆ จะ fallback กลับไปใช้คำว่า 'ffmpeg' เฉยๆ เหมือนเดิม (ให้ error เดิมโผล่มา
    เพื่อให้รู้ว่าต้องตั้งค่าเพิ่ม)
    """
    import shutil

    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and os.path.exists(env_path):
        print(f"[FFmpeg] ✅ ใช้ ffmpeg จาก Environment Variable FFMPEG_PATH: {env_path}")
        return env_path

    which_path = shutil.which("ffmpeg")
    if which_path:
        print(f"[FFmpeg] ✅ พบ ffmpeg ใน PATH ของระบบ: {which_path}")
        return which_path

    try:
        import imageio_ffmpeg
        bundled_path = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled_path and os.path.exists(bundled_path):
            print(f"[FFmpeg] ✅ ไม่พบ ffmpeg ใน PATH ระบบ ใช้ ffmpeg สำรองที่มากับไลบรารี imageio-ffmpeg แทน: {bundled_path}")
            return bundled_path
    except Exception as e:
        print(f"[FFmpeg] ⚠️ โหลด ffmpeg สำรองจาก imageio-ffmpeg ไม่สำเร็จ: {e}")

    print("[FFmpeg] ❌ ไม่พบ ffmpeg เลยทั้งใน PATH และไลบรารีสำรอง! "
          "การเล่นเพลงจะล้มเหลวด้วย error 'ffmpeg was not found' — ดูวิธีแก้ใน README หัวข้อ ffmpeg")
    return "ffmpeg"


FFMPEG_EXECUTABLE = _resolve_ffmpeg_executable()

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 200M',
    'options': '-vn -b:a 192k -bufsize 10M'
}

# ใช้สำหรับค้นหา/เช็คเพลย์ลิสต์แบบเร็ว (extract_flat) ไม่ต้องรอโหลดสตรีมจริง
ytdl_flat_options = {
    'extract_flat': True,
    'playlist_items': '1-50',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

if _COOKIES_FILE:
    ytdl_format_options['cookiefile'] = _COOKIES_FILE
    ytdl_flat_options['cookiefile'] = _COOKIES_FILE

if _PROXY_URL:
    ytdl_format_options['proxy'] = _PROXY_URL
    ytdl_flat_options['proxy'] = _PROXY_URL
    print("[Proxy] 🌐 ใช้ Proxy ที่ตั้งค่าไว้ใน YTDLP_PROXY สำหรับดึงข้อมูลจาก YouTube")

# บังคับให้ yt-dlp แสร้งเป็น client ประเภท "android" ซึ่งมักถูกบล็อกน้อยกว่า client เว็บปกติ
ytdl_format_options.setdefault('extractor_args', {}).setdefault('youtube', {})['player_client'] = ['android', 'web']
ytdl_flat_options.setdefault('extractor_args', {}).setdefault('youtube', {})['player_client'] = ['android', 'web']

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
ytdl_flat = youtube_dl.YoutubeDL(ytdl_flat_options)

# ==============================================================================
# ส่วนที่ 2: State ของบอท + การตั้งค่าต่อเซิร์ฟเวอร์ (persist ลงไฟล์ json)
# ==============================================================================

music_queues = {}
current_song = {}
disconnect_timers = {}

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guild_configs.json")
_config_lock = threading.Lock()


def _load_all_configs():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


guild_configs = _load_all_configs()


def _save_all_configs():
    with _config_lock:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(guild_configs, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] ⚠️ บันทึกการตั้งค่าไม่สำเร็จ: {e}")


def get_guild_config(guild_id):
    return guild_configs.setdefault(str(guild_id), {})


def set_guild_config(guild_id, **kwargs):
    cfg = get_guild_config(guild_id)
    cfg.update(kwargs)
    _save_all_configs()


def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    return music_queues[guild_id]


def friendly_error_message(title, error):
    """แปล error ของ yt-dlp ให้อ่านง่ายขึ้น โดยเฉพาะเคส YouTube บล็อกว่าเป็นบอท"""
    err_text = str(error)
    if "Sign in to confirm" in err_text or "not a bot" in err_text:
        return (
            f"❌ YouTube บล็อกเซิร์ฟเวอร์ไม่ให้ดึงเพลง **{title}** (คิดว่าเป็นบอท)\n"
            f"👉 แอดมินต้องตั้งค่า cookies ให้บอทก่อน ดูวิธีทำได้ในหัวข้อ "
            f"**\"แก้ปัญหา YouTube บล็อกว่าเป็นบอท\"** ใน README ของโปรเจกต์"
        )
    if "ffmpeg was not found" in err_text or "ffmpeg" in err_text.lower() and "not found" in err_text.lower():
        return (
            f"❌ เล่นเพลง **{title}** ไม่ได้ เพราะหาโปรแกรม ffmpeg ไม่เจอในเครื่อง/เซิร์ฟเวอร์นี้\n"
            f"👉 แอดมินต้องติดตั้ง ffmpeg หรือรัน `pip install -r requirement_lib.txt` ใหม่อีกครั้ง "
            f"(มี `imageio-ffmpeg` เป็นตัวสำรองอยู่แล้ว) ดูรายละเอียดในหัวข้อ "
            f"**\"แก้ปัญหา ffmpeg was not found\"** ใน README ของโปรเจกต์"
        )
    return f"❌ เกิดข้อผิดพลาดในการดึงเสียงของเพลง **{title}**: {err_text}"


def format_duration(seconds):
    if not seconds:
        return "ไม่ทราบ"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def get_audio_info(query):
    """ค้นหาเพลง/เพลย์ลิสต์แบบเร็ว คืนค่าเป็น list ของ dict {url, title, thumbnail, duration, webpage_url}"""
    search_query = query if query.startswith('http') else f"ytsearch1:{query}"
    data = ytdl_flat.extract_info(search_query, download=False)

    entries = []
    raw_entries = data.get('entries') if isinstance(data, dict) and 'entries' in data else [data]
    for entry in raw_entries:
        if not entry:
            continue
        url = entry.get('url') or entry.get('webpage_url')
        if not url and entry.get('id'):
            url = f"https://www.youtube.com/watch?v={entry.get('id')}"
        if not url:
            continue
        thumb = entry.get('thumbnail')
        if not thumb and entry.get('thumbnails'):
            try:
                thumb = entry['thumbnails'][-1]['url']
            except Exception:
                thumb = None
        entries.append({
            'url': url,
            'title': entry.get('title', 'Unknown Title'),
            'thumbnail': thumb,
            'duration': entry.get('duration'),
            'webpage_url': entry.get('webpage_url') or url,
        })

    return entries


# คลังคำค้นหาแนวเพลงต่างๆ ใช้สำหรับปุ่ม "สุ่มเพลง" เพื่อให้ได้เพลงหลากหลายแนว
RANDOM_SEARCH_POOL = [
    "เพลงฮิตล่าสุด", "เพลงสตริงฮิต", "เพลงเพราะฟังสบายๆ", "เพลงลูกทุ่งฮิต",
    "เพลงร็อคไทยฮิต", "เพลงฟังก่อนนอน", "เพลงวันแม่", "เพลงอกหักฟังเศร้า",
    "K-pop hits", "top global hits", "EDM hits playlist", "chill lofi hits",
    "hip hop hits", "pop hits", "acoustic cover hits", "throwback hits 2010s",
    "anime opening songs", "indie pop hits", "reggae hits", "jazz hits",
    "disco hits", "rnb hits", "japanese city pop hits", "80s hits",
]


def get_random_songs(count):
    """
    สุ่มเพลงจาก YouTube จำนวน `count` เพลง โดยสุ่มคำค้นจาก RANDOM_SEARCH_POOL
    แล้วสุ่มเลือกเพลงจากผลการค้นหาแต่ละคำ (แคชผลลัพธ์ต่อคำค้นไว้กันยิงซ้ำ)
    """
    terms = RANDOM_SEARCH_POOL.copy()
    random.shuffle(terms)
    term_cache = {}

    def fetch_entries(term):
        if term in term_cache:
            return term_cache[term]
        entries = []
        try:
            data = ytdl_flat.extract_info(f"ytsearch20:{term}", download=False)
            entries = [e for e in (data.get('entries') or []) if e]
        except Exception as e:
            print(f"[Random] ⚠️ ค้นหาคำว่า '{term}' ไม่สำเร็จ: {e}")
        term_cache[term] = entries
        return entries

    picked = []
    seen_urls = set()
    idx = 0
    guard = 0
    max_guard = max(count * 6, 30)

    while len(picked) < count and guard < max_guard and terms:
        guard += 1
        term = terms[idx % len(terms)]
        idx += 1
        entries = fetch_entries(term)
        if not entries:
            continue

        entry = random.choice(entries)
        url = entry.get('url') or entry.get('webpage_url')
        if not url and entry.get('id'):
            url = f"https://www.youtube.com/watch?v={entry.get('id')}"
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        thumb = entry.get('thumbnail')
        if not thumb and entry.get('thumbnails'):
            try:
                thumb = entry['thumbnails'][-1]['url']
            except Exception:
                thumb = None

        picked.append({
            'url': url,
            'title': entry.get('title', 'Unknown Title'),
            'thumbnail': thumb,
            'duration': entry.get('duration'),
            'webpage_url': entry.get('webpage_url') or url,
        })

    return picked


# ==============================================================================
# ส่วนที่ 3: ปุ่มควบคุมเพลง (Persistent View) สำหรับแผงควบคุมในห้องขอเพลง
# ==============================================================================

class PlayerControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="พัก/เล่นต่อ", emoji="⏯️", style=discord.ButtonStyle.blurple, custom_id="veloxmusic:pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client if interaction.guild else None
        if not vc:
            return await interaction.response.send_message("❌ บอทไม่ได้อยู่ในห้องเสียงเลยนะ", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ หยุดเพลงชั่วคราวแล้ว", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ เล่นเพลงต่อแล้ว", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ตอนนี้ไม่ได้เล่นเพลงอะไรอยู่", ephemeral=True)

    @discord.ui.button(label="ข้ามเพลง", emoji="⏭️", style=discord.ButtonStyle.gray, custom_id="veloxmusic:skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ ข้ามเพลงแล้ว!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ไม่มีเพลงให้ข้ามตอนนี้", ephemeral=True)

    @discord.ui.button(label="หยุดทั้งหมด", emoji="⏹️", style=discord.ButtonStyle.red, custom_id="veloxmusic:stop")
    async def stop_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            return
        get_queue(guild.id).clear()
        current_song[guild.id] = None
        cog = interaction.client.get_cog("MusicCog")
        if cog:
            cog.cancel_disconnect_timer(guild.id)
        vc = guild.voice_client
        if vc:
            await vc.disconnect()
        await interaction.response.send_message("⏹️ หยุดเพลงและออกจากห้องเสียงแล้ว", ephemeral=True)
        if cog:
            await cog.update_panel(guild)

    @discord.ui.button(label="สุ่มเพลง", emoji="🔀", style=discord.ButtonStyle.green, custom_id="veloxmusic:random")
    async def random_songs(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            return

        if not interaction.user.voice:
            return await interaction.response.send_message(
                "❌ คุณต้องอยู่ในห้องเสียงก่อนถึงจะสุ่มเพลงได้นะ!", ephemeral=True
            )

        channel = interaction.user.voice.channel
        permissions = channel.permissions_for(guild.me)
        if not permissions.connect or not permissions.speak:
            return await interaction.response.send_message(
                "❌ บอทไม่มีสิทธิ์ Connect/Speak ในห้องเสียงนี้", ephemeral=True
            )

        cog = interaction.client.get_cog("MusicCog")
        if not cog:
            return await interaction.response.send_message("❌ เกิดข้อผิดพลาดภายในบอท", ephemeral=True)

        count = random.randint(1, 20)
        await interaction.response.send_message(
            f"🔀 กำลังสุ่มเพลง {count} เพลง เข้าคิว รอสักครู่นะ...", ephemeral=True
        )

        ctx = await interaction.client.get_context(interaction)
        await cog.handle_random_request(ctx, count)


async def build_now_playing_embed(guild):
    song = current_song.get(guild.id)
    queue_list = get_queue(guild.id)

    embed = discord.Embed(title="🎶 VeloxGG Music Player", color=0x5865F2)

    if song:
        embed.description = f"**🔊 กำลังเล่นอยู่**\n[{song['title']}]({song.get('webpage_url', song['url'])})"
        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])
        embed.add_field(name="⏱️ ความยาว", value=format_duration(song.get('duration')), inline=True)
        embed.add_field(name="🙋 ขอโดย", value=song.get('requester', 'ไม่ทราบ'), inline=True)
    else:
        embed.description = "😴 ยังไม่มีเพลงกำลังเล่นอยู่\nพิมพ์ชื่อเพลงหรือวางลิงก์ในห้องนี้ได้เลย ไม่ต้องพิมพ์ `!play` ก็ได้!"

    if queue_list:
        preview = queue_list[:8]
        lines = [f"`{i + 1}.` {s['title']}" for i, s in enumerate(preview)]
        extra = len(queue_list) - len(preview)
        if extra > 0:
            lines.append(f"...และอีก {extra} เพลงในคิว")
        embed.add_field(name=f"📜 คิวเพลง ({len(queue_list)})", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="📜 คิวเพลง", value="ว่างเปล่า", inline=False)

    embed.set_footer(text="🎵 พิมพ์ชื่อเพลง/วางลิงก์ในห้องนี้เพื่อขอเพลง • ใช้ปุ่มด้านล่างควบคุมเพลงได้เลย")
    return embed


# ==============================================================================
# ส่วนที่ 4: Cog หลักของบอท
# ==============================================================================

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.player_view = PlayerControls()

    # ---------------- แผงควบคุม / Now Playing ---------------- #

    async def update_panel(self, guild):
        if guild is None:
            return
        cfg = get_guild_config(guild.id)
        channel_id = cfg.get("request_channel_id")
        message_id = cfg.get("panel_message_id")
        if not channel_id or not message_id:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return
        embed = await build_now_playing_embed(guild)
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(embed=embed, view=self.player_view)
        except discord.NotFound:
            try:
                new_msg = await channel.send(embed=embed, view=self.player_view)
                set_guild_config(guild.id, panel_message_id=new_msg.id)
            except Exception as e:
                print(f"[Panel] ⚠️ สร้างแผงควบคุมใหม่ไม่สำเร็จ: {e}")
        except Exception as e:
            print(f"[Panel] ⚠️ อัปเดตแผงควบคุมไม่สำเร็จ: {e}")

    # ---------------- ระบบเล่น/คิวเพลง ---------------- #

    def play_next(self, ctx):
        queue_list = get_queue(ctx.guild.id)
        if len(queue_list) > 0:
            self.cancel_disconnect_timer(ctx.guild.id)
            song = queue_list.pop(0)
            current_song[ctx.guild.id] = song
            print(f"[Queue] ⏩ ดึงเพลงถัดไปจากคิว: {song['title']} (เหลือในคิว: {len(queue_list)})")
            self.bot.loop.create_task(self.prepare_and_play(ctx, song))
        else:
            current_song[ctx.guild.id] = None
            print(f"[Queue] 📭 คิวเพลงว่างเปล่าในห้อง {ctx.guild.id}")
            self.start_disconnect_timer(ctx, ctx.guild.id)
            self.bot.loop.create_task(self.update_panel(ctx.guild))

    async def prepare_and_play(self, ctx, song):
        try:
            loop = self.bot.loop
            print(f"[Audio] ⏳ กำลังโหลด Stream URL ของเพลง: {song['title']}")
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(song['url'], download=False))

            if 'entries' in data:
                data = data['entries'][0]

            stream_url = data['url']
            # เติมข้อมูล thumbnail/duration ที่แม่นยำขึ้นจากการโหลดจริง
            song['thumbnail'] = data.get('thumbnail') or song.get('thumbnail')
            song['duration'] = data.get('duration') or song.get('duration')
            song['webpage_url'] = data.get('webpage_url') or song.get('webpage_url')

            print("[Audio] ✅ โหลดสำเร็จ! เริ่มจำลองเสียงไปที่ Discord")
            audio_source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_EXECUTABLE, **ffmpeg_options)
            ctx.voice_client.play(discord.PCMVolumeTransformer(audio_source, volume=0.5), after=lambda e: self.play_next(ctx))

            print(f"[Play] ▶️ กำลังเล่น: {song['title']}")
            await self.update_panel(ctx.guild)
            if not song.get('_from_auto_channel'):
                await ctx.send(f'🎶 กำลังเล่น: **{song["title"]}**')
        except Exception as e:
            print(f"[Error] ❌ โหลดเสียงล้มเหลว: {e}")
            await ctx.send(friendly_error_message(song['title'], e))
            self.play_next(ctx)

    def start_disconnect_timer(self, ctx, guild_id):
        if guild_id in disconnect_timers:
            disconnect_timers[guild_id].cancel()

        async def timer():
            print(f"[Timer] ⏳ เริ่มจับเวลา 5 นาทีสำหรับห้อง {guild_id}...")
            try:
                await asyncio.sleep(300)
                if current_song.get(guild_id) is None and ctx.voice_client and ctx.voice_client.is_connected():
                    print(f"[Disconnect] 🔌 ออกจากห้อง {guild_id} เนื่องจากไม่ได้ใช้งานเกิน 5 นาที")
                    await ctx.voice_client.disconnect()
                    get_queue(guild_id).clear()
                    self.bot.loop.create_task(ctx.send("👋 ออกจากห้องเสียงอัตโนมัติ เนื่องจากไม่มีการใช้งานเกิน 5 นาที"))
                    self.bot.loop.create_task(self.update_panel(ctx.guild))
            except asyncio.CancelledError:
                pass

        disconnect_timers[guild_id] = self.bot.loop.create_task(timer())

    def cancel_disconnect_timer(self, guild_id):
        if guild_id in disconnect_timers:
            disconnect_timers[guild_id].cancel()
            del disconnect_timers[guild_id]

    @commands.Cog.listener()
    async def on_ready(self):
        print('=================================')
        print(f'✅ บอทออนไลน์แล้ว! ชื่อ: {self.bot.user}')
        print(f'🆔 ID: {self.bot.user.id}')
        print('=================================')
        print('พร้อมรับคำสั่ง !play, !stop, !skip, !queue, !random, /setup')

        if not getattr(self.bot, "_views_registered", False):
            self.bot.add_view(self.player_view)
            self.bot._views_registered = True

        if not getattr(self.bot, "_commands_synced", False):
            try:
                synced = await self.bot.tree.sync()
                print(f"[Slash] 🔄 ซิงค์คำสั่ง Slash Command สำเร็จ ({len(synced)} คำสั่ง)")
            except Exception as e:
                print(f"[Slash] ⚠️ ซิงค์คำสั่งไม่สำเร็จ: {e}")
            self.bot._commands_synced = True

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id and before.channel and not after.channel:
            guild_id = member.guild.id
            print(f"[Voice] 🔌 บอทถูกตัดการเชื่อมต่อจากห้อง {guild_id}")
            if guild_id in music_queues:
                music_queues[guild_id].clear()
            current_song[guild_id] = None
            self.cancel_disconnect_timer(guild_id)
            self.bot.loop.create_task(self.update_panel(member.guild))

    # ---------------- Auto request room: พิมพ์ชื่อเพลงตรงๆ ไม่ต้องพิมพ์คำสั่ง ---------------- #

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        cfg = get_guild_config(message.guild.id)
        request_channel_id = cfg.get("request_channel_id")
        if not request_channel_id or message.channel.id != request_channel_id:
            return
        if message.content.startswith(("!", "/")):
            return

        query = message.content.strip()
        if not query:
            return

        ctx = await self.bot.get_context(message)
        await self.handle_song_request(ctx, query, from_auto_channel=True)
        try:
            await message.delete()
        except Exception:
            pass

    # ---------------- ตรรกะขอเพลงที่ใช้ร่วมกันทั้งคำสั่ง !play และห้องขอเพลงอัตโนมัติ ---------------- #

    async def handle_song_request(self, ctx, query, from_auto_channel=False):
        if not ctx.author.voice:
            msg = await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อนถึงจะขอเพลงได้นะ!")
            if from_auto_channel:
                await self._auto_delete(msg)
            return

        channel = ctx.author.voice.channel
        permissions = channel.permissions_for(ctx.me)
        if not permissions.connect or not permissions.speak:
            print(f"[Permission] ❌ บอทไม่มีสิทธิ์เข้าห้อง {channel.name}")
            msg = await ctx.send("❌ บอทไม่มีสิทธิ์ Connect/Speak ในห้องเสียงนี้")
            if from_auto_channel:
                await self._auto_delete(msg)
            return

        if not ctx.voice_client:
            print(f"[Connect] 🔌 กำลังเข้าห้องเสียง: {channel.name}")
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            print(f"[Connect] 🔀 ย้ายไปห้องเสียง: {channel.name}")
            await ctx.voice_client.move_to(channel)

        try:
            print(f"[Search] 🔍 ค้นหาเพลงจากคำค้น/ลิงก์: {query}")
            loop = asyncio.get_event_loop()
            songs = await loop.run_in_executor(None, get_audio_info, query)

            if not songs:
                print("[Search] ❌ ไม่พบเพลง!")
                msg = await ctx.send("❌ ไม่พบข้อมูลเพลงจากคำค้นหาหรือลิงก์นี้")
                if from_auto_channel:
                    await self._auto_delete(msg)
                return

            if len(songs) > 50:
                print("[Search] ⚠️ เพลย์ลิสต์ยาวเกินไป โหลดแค่ 50 เพลง")
                songs = songs[:50]

            requester = ctx.author.display_name
            for s in songs:
                s['requester'] = requester
                s['_from_auto_channel'] = from_auto_channel

            queue_list = get_queue(ctx.guild.id)
            queue_list.extend(songs)
            print(f"[Queue] 📥 เพิ่ม {len(songs)} เพลงเข้าคิว (รวมเป็น {len(queue_list)} เพลง) โดย {requester}")

            is_active = ctx.voice_client.is_playing() or ctx.voice_client.is_paused() or current_song.get(ctx.guild.id) is not None

            if not is_active:
                print("[Play] ▶️ คิวว่างเปล่า ส่งเพลงเข้าเครื่องเล่นทันที")
                self.play_next(ctx)
                if len(songs) == 1:
                    reply = f'⏳ กำลังเตรียมเล่น: **{songs[0]["title"]}**'
                else:
                    reply = f'⏳ เพิ่ม **{len(songs)}** เพลงลงคิว และกำลังเตรียมเล่นเพลงแรก...'
            else:
                print("[Queue] ⏳ บอทกำลังยุ่ง ยืนเข้าคิวตามปกติ")
                if len(songs) == 1:
                    reply = f'✅ เพิ่มลงในคิว: **{songs[0]["title"]}**'
                else:
                    reply = f'✅ เพิ่ม **{len(songs)}** เพลงจากเพลย์ลิสต์ลงในคิวแล้ว!'

            msg = await ctx.send(reply)
            await self.update_panel(ctx.guild)
            if from_auto_channel:
                await self._auto_delete(msg, delay=6)

        except Exception as e:
            print(f"[Error] ❌ เกิดข้อผิดพลาดในคำสั่ง play: {e}")
            msg = await ctx.send(f"❌ เกิดข้อผิดพลาดในการโหลดข้อมูล: {str(e)}")
            if from_auto_channel:
                await self._auto_delete(msg)

    # ---------------- ตรรกะสุ่มเพลง ใช้โดยปุ่ม "สุ่มเพลง" ---------------- #

    async def handle_random_request(self, ctx, count):
        if not ctx.author.voice:
            return await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อนถึงจะสุ่มเพลงได้นะ!")

        channel = ctx.author.voice.channel
        permissions = channel.permissions_for(ctx.me)
        if not permissions.connect or not permissions.speak:
            print(f"[Permission] ❌ บอทไม่มีสิทธิ์เข้าห้อง {channel.name}")
            return await ctx.send("❌ บอทไม่มีสิทธิ์ Connect/Speak ในห้องเสียงนี้")

        if not ctx.voice_client:
            print(f"[Connect] 🔌 กำลังเข้าห้องเสียง: {channel.name}")
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            print(f"[Connect] 🔀 ย้ายไปห้องเสียง: {channel.name}")
            await ctx.voice_client.move_to(channel)

        try:
            print(f"[Random] 🔀 กำลังสุ่มเพลง {count} เพลง สำหรับห้อง {ctx.guild.id}")
            loop = asyncio.get_event_loop()
            songs = await loop.run_in_executor(None, get_random_songs, count)

            if not songs:
                print("[Random] ❌ สุ่มเพลงไม่สำเร็จ ไม่พบผลลัพธ์")
                await ctx.send("❌ สุ่มเพลงไม่สำเร็จ ลองกดปุ่มใหม่อีกครั้งนะ")
                return

            requester = ctx.author.display_name
            for s in songs:
                s['requester'] = requester
                s['_from_auto_channel'] = False

            queue_list = get_queue(ctx.guild.id)
            queue_list.extend(songs)
            print(f"[Random] 📥 เพิ่มเพลงสุ่ม {len(songs)} เพลงเข้าคิว (รวมเป็น {len(queue_list)} เพลง) โดย {requester}")

            is_active = ctx.voice_client.is_playing() or ctx.voice_client.is_paused() or current_song.get(ctx.guild.id) is not None

            if not is_active:
                print("[Random] ▶️ คิวว่างเปล่า ส่งเพลงสุ่มเข้าเครื่องเล่นทันที")
                self.play_next(ctx)

            await ctx.send(f"🔀 สุ่มเพลงเรียบร้อย! เพิ่ม **{len(songs)}** เพลงแบบสุ่มลงในคิวแล้ว 🎶 (ขอโดย {requester})")
            await self.update_panel(ctx.guild)

        except Exception as e:
            print(f"[Error] ❌ เกิดข้อผิดพลาดตอนสุ่มเพลง: {e}")
            await ctx.send(f"❌ เกิดข้อผิดพลาดในการสุ่มเพลง: {str(e)}")

    async def _auto_delete(self, message, delay=5):
        """ลบข้อความแจ้งเตือนอัตโนมัติหลังผ่านไปสักพัก เพื่อให้ห้องขอเพลงดูสะอาดตา"""
        if message is None:
            return
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except Exception:
            pass

    # ---------------- คำสั่งแบบ Prefix (!) เดิม เผื่อใครใช้ความเคยชิน ---------------- #

    @commands.command(name='play', help='เล่นเพลง (YouTube, SoundCloud, Twitch หรือพิมพ์ชื่อเพลงได้เลย)')
    async def play(self, ctx, *, query):
        await self.handle_song_request(ctx, query, from_auto_channel=False)

    @commands.command(name='stop', help='หยุดเพลงและออกจากห้อง')
    async def stop(self, ctx):
        print(f"[Command] 🛑 ผู้ใช้สั่ง Stop ในห้อง {ctx.guild.id}")
        if ctx.voice_client:
            get_queue(ctx.guild.id).clear()
            current_song[ctx.guild.id] = None
            self.cancel_disconnect_timer(ctx.guild.id)
            await ctx.voice_client.disconnect()
            print(f"[Disconnect] 🔌 บอทถูกบังคับออกจากห้อง {ctx.guild.id}")
            await ctx.send("👋 หยุดเพลงและออกจากห้องแล้วนะ")
            await self.update_panel(ctx.guild)
        else:
            await ctx.send("❌ บอทยังไม่ได้อยู่ในห้องเสียงเลย")

    @commands.command(name='skip', help='ข้ามเพลง')
    async def skip(self, ctx):
        print(f"[Command] ⏭️ ผู้ใช้สั่ง Skip ในห้อง {ctx.guild.id}")
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ ข้ามเพลงแล้ว!")
        else:
            await ctx.send("❌ ตอนนี้ไม่ได้เล่นเพลงอะไรอยู่นะ")

    @commands.command(name='queue', help='ดูรายชื่อเพลงในคิว')
    async def queue(self, ctx):
        print(f"[Command] 📜 ผู้ใช้ขอดู Queue ในห้อง {ctx.guild.id}")
        embed = await build_now_playing_embed(ctx.guild)
        await ctx.send(embed=embed)

    @commands.command(name='random', help='สุ่มเพลง 1-20 เพลงต่อคิวเข้าไปให้อัตโนมัติ')
    async def random_cmd(self, ctx):
        print(f"[Command] 🔀 ผู้ใช้สั่ง Random ในห้อง {ctx.guild.id}")
        count = random.randint(1, 20)
        await ctx.send(f"🔀 กำลังสุ่มเพลง {count} เพลง เข้าคิว รอสักครู่นะ...")
        await self.handle_random_request(ctx, count)

    # ---------------- คำสั่ง Slash: /setup ---------------- #

    @app_commands.command(name="setup", description="สร้างห้องขอเพลงอัตโนมัติ พร้อมแผงควบคุมเพลง")
    @app_commands.describe(ชื่อห้อง="ชื่อห้อง (ไม่ใส่ก็ได้ ใช้ค่าเริ่มต้น)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction, ชื่อห้อง: str = "🎵-ขอเพลง"):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        cfg = get_guild_config(guild.id)

        channel = None
        if cfg.get("request_channel_id"):
            channel = guild.get_channel(cfg["request_channel_id"])

        if channel is None:
            try:
                channel = await guild.create_text_channel(
                    ชื่อห้อง,
                    topic="🎵 พิมพ์ชื่อเพลงหรือวางลิงก์ที่นี่เพื่อขอเพลง ไม่ต้องพิมพ์คำสั่ง!"
                )
            except discord.Forbidden:
                return await interaction.followup.send("❌ บอทไม่มีสิทธิ์สร้างห้องในเซิร์ฟเวอร์นี้ (ต้องการสิทธิ์ Manage Channels)", ephemeral=True)

        embed = await build_now_playing_embed(guild)
        try:
            panel_msg = await channel.send(embed=embed, view=self.player_view)
            try:
                await panel_msg.pin()
            except Exception:
                pass
        except discord.Forbidden:
            return await interaction.followup.send(f"❌ บอทส่งข้อความในห้อง {channel.mention} ไม่ได้ ลองเช็คสิทธิ์อีกครั้ง", ephemeral=True)

        set_guild_config(guild.id, request_channel_id=channel.id, panel_message_id=panel_msg.id)
        await interaction.followup.send(
            f"✅ ตั้งค่าห้องขอเพลงเรียบร้อยที่ {channel.mention}\n"
            f"พิมพ์ชื่อเพลงหรือวางลิงก์ในห้องนั้นได้เลย ไม่ต้องพิมพ์ `!play` แล้วนะ!",
            ephemeral=True
        )

    @setup.error
    async def setup_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ ต้องมีสิทธิ์ 'Manage Server' ถึงจะใช้คำสั่งนี้ได้นะ", ephemeral=True)
        else:
            print(f"[Slash Error] {error}")
            try:
                await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {error}", ephemeral=True)
            except Exception:
                pass


# ==============================================================================
# ส่วนที่ 5: จุดเริ่มต้นให้ GUI / Railway เรียกใช้งาน
# ==============================================================================

_stop_event = None


def request_stop_bot():
    if _stop_event:
        _stop_event.set()


def run_bot(token):
    """สร้างและรันบอทหนึ่งรอบ (ใช้ asyncio.run เพื่อจัดการ event loop ให้สมบูรณ์)"""
    global _stop_event, music_queues, current_song, disconnect_timers

    music_queues = {}
    current_song = {}
    disconnect_timers = {}

    _stop_event = threading.Event()

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(
        command_prefix=commands.when_mentioned_or("!"),
        description='บอทเปิดเพลงง่ายๆ พร้อมห้องขอเพลงอัตโนมัติ',
        intents=intents,
    )

    async def wait_for_stop():
        while not _stop_event.is_set():
            await asyncio.sleep(0.5)
        print("กำลังปิดการเชื่อมต่อ Discord และเคลียร์บอท...")
        await bot.close()
        print("ปิดบอทสมบูรณ์แล้ว!")

    async def main():
        async with bot:
            await bot.add_cog(MusicCog(bot))
            bot.loop.create_task(wait_for_stop())
            try:
                await bot.start(token)
            except discord.errors.LoginFailure:
                print("❌ Token ไม่ถูกต้อง! กรุณาตรวจสอบ Token อีกครั้ง")
            except Exception as e:
                print(f"❌ เกิดข้อผิดพลาดในการรันบอท: {e}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

import asyncio
# Python 3.10+ Event Loop Fix
try:
    asyncio.set_event_loop(asyncio.new_event_loop())
except:
    pass

import re
import json
import os
import time
import math
import sqlite3
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# 🔥 MULTI-THREADING IMPORTS 🔥
from pyrogram.file_id import FileId
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputDocumentFileLocation

# --- UNGA DETAILS (Imported from config.py) ---
from config import API_ID, API_HASH, ADMIN_ID, STRING_SESSION

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
THUMB_PATH = os.path.join(BASE_DIR, "thumbnail.jpg")
ASS_PATH = os.path.join(BASE_DIR, "subtitle.ass")
DB_PATH = os.path.join(BASE_DIR, "bot_database.db")

# --- DATABASE SETUP ---
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY, 
    auto_format TEXT,
    meta_title TEXT,
    meta_video TEXT,
    meta_audio TEXT,
    meta_sub TEXT,
    meta_enabled INTEGER DEFAULT 0,
    ass_enabled INTEGER DEFAULT 0
)''')
conn.commit()
cursor.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (ADMIN_ID,))
conn.commit()

# --- GLOBAL STATES ---
manual_rename_task = {}
track_picker_state = {} 

# 🔥 MASTER UPGRADE: Userbot (Premium Speed) Initialization 🔥
app = Client("anime_premium_userbot", session_string=STRING_SESSION, api_id=API_ID, api_hash=API_HASH)

# --- HELPER FUNCTIONS ---
def humanbytes(size):
    if not size: return "0 B"
    power = 1024
    n = 0
    Dic_powerN = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n]

async def progress_bar(current, total, action, message, start_time):
    now = time.time()
    diff = now - start_time
    if round(diff % 2.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = round((total - current) / speed) if speed > 0 else 0
        completed = int(math.floor(percentage / 5))
        progress_str = "█" * completed + "░" * (20 - completed)
        
        text = f"**{action}**\n\n[{progress_str}] {round(percentage, 2)}%\n🚀 **Speed:** {humanbytes(speed)}/s\n📦 **Size:** {humanbytes(current)} / {humanbytes(total)}\n⏱️ **ETA:** {eta}s"
        try: await message.edit_text(text)
        except: pass

# 🔥 IDM-STYLE MULTI-THREADED FAST DOWNLOADER 🔥
async def fast_download(client, message, output_path, status_msg, start_time):
    media = message.document or message.video
    file_size = media.file_size
    
    # 1MB Chunks - Telegram's max per request
    chunk_size = 1024 * 1024 
    total_parts = math.ceil(file_size / chunk_size)
    
    # 10 Parallel Connections (Like IDM)
    max_concurrent_tasks = 10 
    
    await status_msg.edit_text(f"🚀 **JET DOWNLOAD STARTING...**\n\n📦 Size: {humanbytes(file_size)}\n🔗 Connections: {max_concurrent_tasks}")
    
    # Getting File Location for Raw API
    decoded = FileId.decode(media.file_id)
    location = InputDocumentFileLocation(
        id=decoded.media_id, 
        access_hash=decoded.access_hash, 
        file_reference=decoded.file_reference, 
        thumb_size=""
    )

    downloaded_size = 0
    with open(output_path, "wb") as f:
        # Pre-allocate file space
        if file_size > 0:
            f.seek(file_size - 1)
            f.write(b"\0")
        
    async def fetch_chunk(part_num):
        offset = part_num * chunk_size
        
        # 🔥 Telegram API limit fix: Eppovume 1MB thaan kekkanum 🔥
        limit = chunk_size 
        
        chunk_data = await client.invoke(GetFile(
            location=location,
            offset=offset,
            limit=limit
        ))
        
        with open(output_path, "r+b") as f:
            f.seek(offset)
            f.write(chunk_data.bytes)
            
        return len(chunk_data.bytes)

    # Executing 10 tasks at the same time
    for i in range(0, total_parts, max_concurrent_tasks):
        tasks = []
        for j in range(max_concurrent_tasks):
            if i + j < total_parts:
                tasks.append(fetch_chunk(i + j))
                
        results = await asyncio.gather(*tasks)
        downloaded_size += sum(results)
        
        # Update progress UI every 10 chunks to avoid flood limit
        await progress_bar(downloaded_size, file_size, "🚀 Jet Downloading...", status_msg, start_time)
        
    return output_path

async def run_ffmpeg(cmd):
    process = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        print(f"\n❌ FFMPEG ERROR:\n{stderr.decode('utf-8', errors='ignore')}\n")
        return False
    return True

async def get_media_streams(file_path):
    cmd = f'ffprobe -v quiet -print_format json -show_streams "{file_path}"'
    process = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await process.communicate()
    try:
        data = json.loads(stdout)
        audios = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
        subs = [s for s in data.get('streams', []) if s.get('codec_type') == 'subtitle']
        return audios, subs
    except:
        return [], []

# --- SMART AUTO-RENAME LOGIC ---
def smart_parse(filename):
    filename = re.sub(r'(?i)[a-z0-9-]+\.(com|in|co|net|org|me|cc|biz|info)[\s_-]*', '', filename)
    filename = re.sub(r'(?i)@\w+[\s_-]*', '', filename)
    name_clean = filename.replace('_', ' ').replace('.', ' ')
    
    quality = (re.search(r'(?i)(480p|720p|1080p|2160p|4k)', name_clean) or [None, ""])[1]
    season_match = re.search(r'(?i)(s|season)\s*(\d+)', name_clean)
    season = f"S{int(season_match.group(2)):02d}" if season_match else ""
    ep_match = re.search(r'(?i)(e|ep|episode)\s*(\d+)', name_clean)
    episode = f"E{int(ep_match.group(2)):02d}" if ep_match else ""
    lang = (re.search(r'(?i)(tamil|telugu|hindi|malayalam|eng|dual audio|multi)', name_clean) or [None, ""])[1]
    if lang: lang = lang.title()

    for tag in [quality, (season_match.group(0) if season_match else ""), (ep_match.group(0) if ep_match else ""), lang]:
        if tag: name_clean = re.sub(re.escape(tag), '', name_clean, flags=re.IGNORECASE)

    name_clean = re.sub(r'(?i)\b(10bit|8bit|x264|x265|hevc|dsn|dsnp|web-dl|webrip|brrip|bdrip)\b', '', name_clean)
    name_clean = re.sub(r'\[\s*\]|\(\s*\)', '', name_clean)
    title = re.sub(r'\s+', ' ', name_clean).strip()
    title = re.sub(r'[-=:]\s*$', '', title).strip()
    return title, season, episode, quality, lang

# --- DASHBOARD & COMMANDS ---
@app.on_message((filters.me | filters.user(ADMIN_ID)) & filters.command(["start", "showformat"]))
async def start_dashboard(client, message):
    cursor.execute("SELECT auto_format, meta_title, meta_video, meta_audio, meta_sub, meta_enabled, ass_enabled FROM settings WHERE user_id = ?", (ADMIN_ID,))
    data = cursor.fetchone()
    
    thumb_status = "✅ Saved" if os.path.exists(THUMB_PATH) else "❌ Not Saved"
    meta_status = "🟢 ON" if data[5] else "🔴 OFF"
    ass_status = "🟢 ON" if data[6] else "🔴 OFF"
    
    text = f"""**🤖 Bᴏᴛ Cᴏɴᴛʀᴏʟ Pᴀɴᴇʟ**\n\n**🖼 Tʜᴜᴍʙɴᴀɪʟ:** {thumb_status}\n\n**🎬 Mᴇᴛᴀᴅᴀᴛᴀ Sᴛᴀᴛᴜs:** {meta_status}\n ▸ Title: `{data[1] or 'Not Set'}`\n ▸ Video: `{data[2] or 'Not Set'}`\n ▸ Audio: `{data[3] or 'Not Set'}`\n ▸ Sub: `{data[4] or 'Not Set'}`\n\n**💬 Sᴜʙᴛɪᴛʟᴇ (.ᴀss):** {ass_status}\n\n**📝 Aᴜᴛᴏ-Rᴇɴᴀᴍᴇ Fᴏʀᴍᴀᴛ:** \n`{data[0] or 'Not Set'}`"""
    await message.reply_text(text)

@app.on_message((filters.me | filters.user(ADMIN_ID)) & filters.command("format"))
async def set_format(client, message):
    if len(message.command) > 1:
        new_format = message.text.split(" ", 1)[1]
        cursor.execute("UPDATE settings SET auto_format = ? WHERE user_id = ?", (new_format, ADMIN_ID))
        conn.commit()
        await message.reply_text(f"✅ Format saved!\n*(Vars allowed: {{title}}, {{season}}, {{episode}}, {{quality}}, {{language}}, {{ext}})*\n\nCurrent: `{new_format}`")
    else:
        await message.reply_text("❌ Example:\n`/format [{season}-{episode}] {title} [{quality}] [{language}] @MyChannel`")

# --- UI BUTTON HANDLER FOR AUDIO/SUB PICKER ---
def get_picker_markup(uid):
    s = track_picker_state[uid]
    keys = []
    for i, a in enumerate(s['audios']):
        status = "✅" if s['a_sel'][i] else "❌"
        lang = a.get('tags', {}).get('language', f'Track {i+1}').upper()
        keys.append([InlineKeyboardButton(f"{status} Audio: {lang}", callback_data=f"t_a_{i}")])
    for i, sub in enumerate(s['subs']):
        status = "✅" if s['s_sel'][i] else "❌"
        lang = sub.get('tags', {}).get('language', f'Sub {i+1}').upper()
        keys.append([InlineKeyboardButton(f"{status} Subtitle: {lang}", callback_data=f"t_s_{i}")])
    
    keys.append([InlineKeyboardButton("🚀 Confirm & Process", callback_data="process_media")])
    return InlineKeyboardMarkup(keys)

@app.on_callback_query(filters.me | filters.user(ADMIN_ID))
async def callback_handler(client, query: CallbackQuery):
    uid = query.from_user.id
    if uid not in track_picker_state:
        return await query.answer("Session expired.", show_alert=True)
    
    data = query.data
    if data.startswith("t_a_"):
        idx = int(data.split("_")[2])
        track_picker_state[uid]['a_sel'][idx] = not track_picker_state[uid]['a_sel'][idx]
        await query.edit_message_reply_markup(get_picker_markup(uid))
    elif data.startswith("t_s_"):
        idx = int(data.split("_")[2])
        track_picker_state[uid]['s_sel'][idx] = not track_picker_state[uid]['s_sel'][idx]
        await query.edit_message_reply_markup(get_picker_markup(uid))
    elif data == "process_media":
        await query.message.delete()
        track_picker_state[uid]['event'].set()

# --- METADATA, ASS & MANUAL LOGIC ---
@app.on_message((filters.me | filters.user(ADMIN_ID)) & filters.command(["title", "videoname", "audioname", "subname"]))
async def set_metadata(client, message):
    cmd = message.command[0]
    if len(message.command) > 1:
        val = message.text.split(" ", 1)[1]
        col = {"title": "meta_title", "videoname": "meta_video", "audioname": "meta_audio", "subname": "meta_sub"}[cmd]
        cursor.execute(f"UPDATE settings SET {col} = ? WHERE user_id = ?", (val, ADMIN_ID))
        conn.commit()
        await message.reply_text(f"✅ Metadata `{cmd}` set to: **{val}**")

@app.on_message((filters.me | filters.user(ADMIN_ID)) & filters.command("meta"))
async def toggle_meta(client, message):
    cursor.execute("SELECT meta_enabled FROM settings WHERE user_id = ?", (ADMIN_ID,))
    new_state = 0 if cursor.fetchone()[0] else 1
    cursor.execute("UPDATE settings SET meta_enabled = ? WHERE user_id = ?", (new_state, ADMIN_ID))
    conn.commit()
    await message.reply_text(f"🎬 Metadata is now **{'ON 🟢' if new_state else 'OFF 🔴'}**")

@app.on_message((filters.me | filters.user(ADMIN_ID)) & filters.command("ass"))
async def toggle_ass(client, message):
    cursor.execute("SELECT ass_enabled FROM settings WHERE user_id = ?", (ADMIN_ID,))
    new_state = 0 if cursor.fetchone()[0] else 1
    cursor.execute("UPDATE settings SET ass_enabled = ? WHERE user_id = ?", (new_state, ADMIN_ID))
    conn.commit()
    await message.reply_text(f"💬 Subtitle (.ass) is now **{'ON 🟢' if new_state else 'OFF 🔴'}**")

@app.on_message((filters.me | filters.user(ADMIN_ID)) & filters.photo)
async def save_thumbnail(client, message):
    temp_path = await message.download()
    img = Image.open(temp_path)
    img.thumbnail((320, 320))
    img.save(THUMB_PATH, "JPEG")
    os.remove(temp_path)
    await message.reply_text("✅ Thumbnail saved!")

@app.on_message((filters.me | filters.user(ADMIN_ID)) & filters.command("mrename"))
async def set_manual_rename(client, message):
    if len(message.command) > 1:
        custom_name = message.text.split(" ", 1)[1]
        if custom_name.lower() == "clear":
            manual_rename_task.pop(ADMIN_ID, None)
            await message.reply_text("🧹 Manual rename cleared!")
        else:
            manual_rename_task[ADMIN_ID] = custom_name
            await message.reply_text(f"📝 Next single file will be renamed to:\n`{custom_name}`")

# --- MAIN PROCESSOR ---
@app.on_message((filters.me | filters.user(ADMIN_ID)) & (filters.video | filters.document))
async def process_media(client, message):
    if message.document and message.document.file_name and message.document.file_name.endswith(".ass"):
        await message.download(file_name=ASS_PATH)
        return await message.reply_text("📎 `.ass` Subtitle file saved! Turn it on using `/ass`")

    status = await message.reply_text("📥 Downloading to Server...")
    
    try:
        cursor.execute("SELECT auto_format, meta_title, meta_video, meta_audio, meta_sub, meta_enabled, ass_enabled FROM settings WHERE user_id = ?", (ADMIN_ID,))
        db_data = cursor.fetchone()
        auto_fmt, m_title, m_vid, m_aud, m_sub, meta_on, ass_on = db_data

        original_name = message.video.file_name if message.video else (message.document.file_name if message.document else "Video_File.mkv")
        file_ext = os.path.splitext(original_name)[1]
        title_no_ext = os.path.splitext(original_name)[0]
        
        title, season, episode, quality, language = smart_parse(title_no_ext)
        
        if ass_on and os.path.exists(ASS_PATH) and file_ext.lower() != ".mkv":
            file_ext = ".mkv"

        if ADMIN_ID in manual_rename_task:
            new_file_name = manual_rename_task[ADMIN_ID]
            if not new_file_name.endswith(file_ext): 
                new_file_name += file_ext
            manual_rename_task.pop(ADMIN_ID, None)
        elif auto_fmt:
            new_file_name = auto_fmt.format(title=title, season=season, episode=episode, quality=quality, language=language, ext=file_ext)
            new_file_name = new_file_name.replace("[]", "").replace("[-]", "").replace("  ", " ").strip() 
            if not new_file_name.endswith(file_ext): new_file_name += file_ext
        else:
            new_file_name = original_name

        start_time = time.time()
        
        # 🔥 THE JET DOWNLOADER MAGIC STARTS HERE 🔥
        input_path = os.path.join(BASE_DIR, "temp_download_" + new_file_name)
        await fast_download(client, message, input_path, status, start_time)
        
        output_path = os.path.join(os.path.dirname(input_path), new_file_name)
        temp_output_path = input_path + "_temp_out.mkv"

        audios, subs = await get_media_streams(input_path)
        
        ffmpeg_inputs = f'-i "{input_path}" '
        map_args = "-map 0:v:0 " 
        
        if len(audios) > 1 or len(subs) > 0:
            track_picker_state[ADMIN_ID] = {
                'audios': audios, 'subs': subs,
                'a_sel': [True]*len(audios), 's_sel': [True]*len(subs),
                'event': asyncio.Event()
            }
            await status.delete()
            picker_msg = await message.reply_text("🎛 **Select Tracks to Keep:**", reply_markup=get_picker_markup(ADMIN_ID))
            
            await track_picker_state[ADMIN_ID]['event'].wait()
            status = await message.reply_text("⚙️ Processing with FFmpeg (Smart Format & Metadata)...")
            
            s = track_picker_state[ADMIN_ID]
            for i, keep in enumerate(s['a_sel']):
                if keep: map_args += f"-map 0:a:{i} "
                
            if ass_on and os.path.exists(ASS_PATH):
                ffmpeg_inputs += f'-i "{ASS_PATH}" '
                map_args += "-map 1:0 -disposition:s:0 default "
                
            for i, keep in enumerate(s['s_sel']):
                if keep: map_args += f"-map 0:s:{i} "
        else:
            map_args = "-map 0:v:0? -map 0:a? "
            if ass_on and os.path.exists(ASS_PATH):
                ffmpeg_inputs += f'-i "{ASS_PATH}" '
                map_args += "-map 1:0 -disposition:s:0 default "
            map_args += "-map 0:s? "

        cmd = f'ffmpeg -y {ffmpeg_inputs} {map_args} -c copy '

        m_title = m_title.replace('"', "'") if m_title else ""
        m_vid = m_vid.replace('"', "'") if m_vid else ""
        m_aud = m_aud.replace('"', "'") if m_aud else ""
        m_sub = m_sub.replace('"', "'") if m_sub else ""

        if meta_on:
            if m_title: cmd += f'-metadata title="{m_title}" '
            if m_vid: cmd += f'-metadata:s:v title="{m_vid}" '
            if m_aud: cmd += f'-metadata:s:a title="{m_aud}" '
            if m_sub: cmd += f'-metadata:s:s title="{m_sub}" '
        
        cmd += f'"{temp_output_path}"'

        success = await run_ffmpeg(cmd)
        
        if not success or not os.path.exists(temp_output_path):
            await status.edit_text("⚠️ Metadata Edit Failed! Renaming directly.")
            await asyncio.sleep(2)
            os.rename(input_path, output_path)
        else:
            os.remove(input_path)
            if os.path.exists(output_path): os.remove(output_path) 
            os.rename(temp_output_path, output_path)

        thumb_to_send = THUMB_PATH if os.path.exists(THUMB_PATH) else None
        start_time = time.time()
        
        await client.send_document(
            chat_id=message.chat.id,
            document=output_path,
            thumb=thumb_to_send,
            caption=new_file_name,
            progress=progress_bar,
            progress_args=("📤 Uploading...", status, start_time)
        )
        
        if os.path.exists(output_path): os.remove(output_path)
        await status.delete()
        
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")

print("🚀 Premium Userbot Engine Running at High Speed... 🔥")
app.run()

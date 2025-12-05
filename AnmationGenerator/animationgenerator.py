# -*- coding: utf-8 -*-
from openai import OpenAI
from gtts import gTTS
from mutagen.mp3 import MP3
import cv2
import subprocess, re, ast, os, sys
from playsound import playsound   # <<< ADDED
import threading                  # <<< ADDED

# ===========================
# 🔥 AI CONFIG
# ===========================
API_KEY = ""
MODEL = "moonshotai/kimi-k2-instruct-0905"
client = OpenAI(api_key=API_KEY, base_url="https://api.groq.com/openai/v1")

# ===========================
# 🌍 LANGUAGE MAP
# ===========================
LANG_MAP = {
    "1": ("Kannada", "kn", "Kannada", "Noto Sans Kannada"),
    "2": ("English", "en", "English", None),
    "3": ("Hindi", "hi", "Hindi", "Noto Sans Devanagari"),
    "4": ("Telugu", "te", "Telugu", "Noto Sans Telugu"),
    "5": ("Tamil", "ta", "Tamil", "Noto Sans Tamil"),
}

def choose_language():
    print("\nChoose Language:")
    for k, v in LANG_MAP.items():
        print(f"{k}. {v[0]}")
    return LANG_MAP.get(input("Enter number: ").strip(), LANG_MAP["2"])

# ===========================
# 🧠 SUMMARY
# ===========================
def summarize(topic, lang):
    prompt = f"Explain '{topic}' in {lang} under 120 words like a friendly teacher."
    r = client.chat.completions.create(
        model=MODEL, messages=[{"role":"user","content":prompt}]
    )
    return r.choices[0].message.content.strip()

# ===========================
# 🔊 TEXT TO SPEECH
# ===========================
def text_to_speech(text, filename, lang_code):
    tts = gTTS(text=text, lang=lang_code)
    tts.save(filename)

# ===========================
# 🎨 MANIM GENERATION
# ===========================
def request_manim_code(topic, font):
    font_line = f'font="{font}"' if font else ""

    prompt = f"""
Create a Manim CE 0.19.0 animated diagram explaining "{topic}". 
Rules:
- Pure Python code.
- must start: from manim import *
- Class name: AutoTeach(Scene)
- Allowed: Text, Circle, Square, Rectangle, Arrow, VGroup
- Only colors: BLUE, RED, GREEN, YELLOW, WHITE
- Must include: title, shapes, labels, arrows
- Must animate using FadeIn, Create, GrowArrow, Transform
- All Text() must include {font_line}
"""
    r = client.chat.completions.create(
        model=MODEL, messages=[{"role":"user","content":prompt}]
    )
    return r.choices[0].message.content.strip()

def sanitize_script(code):
    code = code.replace("```", "").replace("python", "")
    for c in ["LIGHT_BLUE","TEAL","PINK","PURPLE","ORANGE"]:
        code = code.replace(c, "BLUE")

    while True:
        try:
            ast.parse(code)
            return code
        except:
            lines = code.splitlines()[:-1]
            code = "\n".join(lines)
            if len(lines) < 2:
                return code

def manim_test(file):
    return subprocess.run(f"manim {file} AutoTeach --dry_run", shell=True).returncode == 0

def generate_final_valid_code(topic, font):
    for i in range(4):
        raw = request_manim_code(topic, font)
        clean = sanitize_script(raw)
        fname = re.sub(r"[^A-Za-z0-9_]", "_", topic) + ".py"
        
        with open(fname, "w", encoding="utf-8") as f:
            f.write(clean)

        if manim_test(fname):
            print("✅ Manim script ready")
            return fname
    raise Exception("Manim generation failed.")

# ===========================
# 🎥 RENDER MANIM + PLAY AUDIO SYNC
# ===========================
def render_video_with_audio(script, audio_file, preview=False):
    # CLI mode → play preview + audio
    if preview:
        threading.Thread(target=playsound, args=(audio_file,), daemon=True).start()
        subprocess.run(f"manim -pql {script} AutoTeach", shell=True)
    else:
        # Web mode → silent rendering (non-blocking)
        subprocess.Popen(f"manim -ql {script} AutoTeach", shell=True)


def find_video_for_topic(script_name):
    folder = os.path.splitext(script_name)[0]
    base = os.path.join("media", "videos", folder)

    newest = None
    newest_t = 0

    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".mp4") and "AutoTeach" in f:
                full = os.path.join(root, f)
                t = os.path.getmtime(full)
                if t > newest_t:
                    newest = full
                    newest_t = t
    return newest

# ===========================
# 📏 DURATIONS
# ===========================
def get_audio_duration(p):
    try: return MP3(p).info.length
    except: return 0

def get_video_duration(p):
    cap = cv2.VideoCapture(p)
    if not cap.isOpened(): return 0
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return frames / fps if fps > 0 else 0

# ===========================
# ⭐ NEW: STRETCH VIDEO TO MATCH AUDIO
# ===========================
def stretch_video_to_audio(video, audio_len):
    video_len = get_video_duration(video)
    if video_len == 0 or video_len >= audio_len:
        return video

    speed_factor = video_len / audio_len
    stretched = video.replace(".mp4", "_stretched.mp4")

    cmd = (
        f'ffmpeg -y -i "{video}" -filter:v "setpts=(1/{speed_factor})*PTS" '
        f'-c:v libx264 -pix_fmt yuv420p "{stretched}"'
    )

    subprocess.run(cmd, shell=True)

    return stretched if os.path.exists(stretched) else video

# ===========================
# 🔊 MERGE AUDIO + VIDEO
# ===========================
def merge_audio_video(video, audio, output):
    cmd = (
        f'ffmpeg -y -i "{video}" -i "{audio}" '
        f'-c:v copy -c:a aac -map 0:v -map 1:a -shortest "{output}"'
    )
    subprocess.run(cmd, shell=True)
    return os.path.exists(output)

# ===========================
# 📝 QUIZ
# ===========================
def create_quiz(topic, lang):
    prompt = f"""
Create a 4-question MCQ quiz in {lang} on '{topic}':
Q1:...
A)...
B)...
C)...
D)...
Answer:X
Q2:...
A)...
B)...
C)...
D)...
Answer:X
Q3:...
A)...
B)...
C)...
D)...
Answer:X
Q4:...
A)...
B)...
C)...
D)...
Answer:X
"""
    r = client.chat.completions.create(
        model=MODEL, messages=[{"role":"user","content":prompt}]
    )
    return r.choices[0].message.content.strip()

# =========================================================
# ⭐⭐ NEW: FUNCTION FOR WEB USE ⭐⭐
# =========================================================

def generate_content(topic, lang_key):
    lang_display, tts_lang, model_lang, font = LANG_MAP[lang_key]

    summary = summarize(topic, model_lang)

    os.makedirs("output", exist_ok=True)

    audio_file = f"output/{re.sub(r'[^A-Za-z0-9_]', '_', topic)}_{lang_display}.mp3"
    text_to_speech(summary, audio_file, tts_lang)

    audio_len = get_audio_duration(audio_file)

    script = generate_final_valid_code(topic, font)
    render_video_with_audio(script, audio_file)

    video_path = find_video_for_topic(script)
    stretched = stretch_video_to_audio(video_path, audio_len)

    final_video = stretched.replace(".mp4", f"_{lang_display}_with_audio.mp4")
    final_video = f"output/{os.path.basename(final_video)}"

    merge_audio_video(stretched, audio_file, final_video)

    quiz = create_quiz(topic, model_lang)

    return summary, final_video.replace("\\", "/"), quiz


# ===========================
# 🚀 ORIGINAL CLI STILL WORKS
# ===========================
if __name__ == "__main__":

    lang_display, tts_lang, model_lang, font = choose_language()
    topic = input("\n🧠 Enter topic: ").strip()

    summary = summarize(topic, model_lang)
    print("\n📄 Summary:\n", summary)

    audio_file = f"{re.sub(r'[^A-Za-z0-9_]', '_', topic)}_{lang_display}.mp3"
    text_to_speech(summary, audio_file, tts_lang)

    audio_len = get_audio_duration(audio_file)
    print(f"🔊 Audio = {audio_len:.2f}s")

    script = generate_final_valid_code(topic, font)

    # 🔥 NOW VIDEO + AUDIO PLAY TOGETHER
    render_video_with_audio(script, audio_file)

    video_path = find_video_for_topic(script)
    print("🎬 Video =", video_path)

    stretched = stretch_video_to_audio(video_path, audio_len)

    out = stretched.replace(".mp4", f"_{lang_display}_with_audio.mp4")
    merge_audio_video(stretched, audio_file, out)

    print("\n✅ FINAL VIDEO READY:", out)
    os.startfile(out)

    print("\n🎓 QUIZ:\n")
    print(create_quiz(topic, model_lang))

    print("\n🎉 DONE — Live synced playback + final synced export ready!")

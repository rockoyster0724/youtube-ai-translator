import streamlit as st
import yt_dlp
import asyncio
import edge_tts
import os
import subprocess
import concurrent.futures
from groq import Groq
from deep_translator import GoogleTranslator
st.set_page_config(
    page_title="生蠔YT翻譯機",
    page_icon="icon.png",
    layout="centered"
)
# --- 輔助函數：將秒數轉換為標準時間格式 ---
def format_timestamp(seconds: float, separator=","):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"

# --- 輔助函數：單句翻譯 ---
def translate_sentence(text):
    try:
        return GoogleTranslator(source='en', target='zh-TW').translate(text)
    except:
        return text

# 設定網頁標題
st.title("🎥 YouTube 影片 AI 轉譯助手 (☁️ 雲端極速版)")

# 側邊欄：設定 API Key
api_key = st.secrets["GROQ_API_KEY"]
# 1. 輸入網址
url = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

# 2. 選擇功能模式
mode = st.radio(
    "請選擇你想要產出的結果：",
    (
        "🌐 在網頁直接播放雙語影片 (最快！不佔電腦空間)",
        "🎬 下載雙語字幕影片 (QuickTime 相容)",
        "🎧 生成中文配音音檔"
    )
)

# 3. 點擊按鈕開始執行
if st.button("啟動雲端極速處理"):
    if not url:
        st.warning("請先輸入網址喔！")
    elif not api_key:
        st.error("請先在左側欄位輸入 Groq API Key 才能使用雲端加速喔！")
    else:
        with st.status("☁️ 雲端引擎啟動中，請稍候...", expanded=True) as status:
            
            # --- 步驟 A: 下載 ---
            if "音檔" in mode:
                st.write("📥 [1/4] 正在下載音訊...")
                ydl_opts = {
                    'format': 'm4a/bestaudio/best',
                    'outtmpl': 'input_audio.m4a',
                    'overwrites': True,
                    'extractor_args': {'youtube': {'player_client': ['ios', 'android', 'web']}},
                    'source_address': '0.0.0.0',
                    'cookiefile': 'cookies.txt',
                    'verbose': True
                }
                target_file = 'input_audio.m4a'
            else:
                st.write("📥 [1/4] 正在下載 1080p 影片...")
                ydl_opts = {
                    'format': 'bestvideo[height<=1080][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'outtmpl': 'input_video.mp4',
                    'overwrites': True,
                    'extractor_args': {'youtube': {'player_client': ['ios', 'android', 'web']}},
                    'source_address': '0.0.0.0',
                    'cookiefile': 'cookies.txt',
                    'verbose': True
                }
                target_file = 'input_video.mp4'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        ydl.download([url])
                    except Exception as e:
                        st.error(f"🚨 抓到真兇了！真實錯誤原因： {str(e)}")
                        st.stop()  # 發生錯誤就立刻停止
            
            # --- 為了讓 Groq 處理，我們統一抽出一份音檔 ---
            st.write("☁️ [2/4] 正在將語音送往 Groq 雲端處理 (只需幾秒鐘)...")
            if target_file == 'input_video.mp4':
                subprocess.run(["ffmpeg", "-y", "-i", "input_video.mp4", "-q:a", "0", "-map", "a", "input_audio.m4a"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 呼叫 Groq API
            client = Groq(api_key=api_key)
            with open("input_audio.m4a", "rb") as file:
                transcription = client.audio.transcriptions.create(
                  file=("input_audio.m4a", file.read()),
                  model="whisper-large-v3",
                  response_format="verbose_json",
                )
            
            # --- 步驟 C: 平行翻譯 ---
            st.write("🏮 [3/4] 正在多管齊下極速翻譯字幕...")
            segments = transcription.segments
            en_texts = [seg['text'].strip() for seg in segments]
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                zh_texts = list(executor.map(translate_sentence, en_texts))
            
            # --- 依照模式輸出結果 ---
            if "網頁直接播放" in mode:
                # 網頁播放器需要 VTT 格式的字幕
                vtt_content = "WEBVTT\n\n"
                for i, seg in enumerate(segments):
                    start = format_timestamp(seg['start'], ".")
                    end = format_timestamp(seg['end'], ".")
                    vtt_content += f"{start} --> {end}\n{zh_texts[i]}\n{en_texts[i]}\n\n"
                
                with open("subtitles.vtt", "w", encoding="utf-8") as f:
                    f.write(vtt_content)
                
                status.update(label="✅ 處理完成！請在下方直接觀看", state="complete")
                
                # 直接在 Streamlit 播放影片並掛載字幕
                st.video("input_video.mp4", subtitles={"繁體中文": "subtitles.vtt"})
                
            elif "下載雙語字幕影片" in mode:
                # 合成 SRT 字幕
                srt_content = ""
                for i, seg in enumerate(segments):
                    start = format_timestamp(seg['start'], ",")
                    end = format_timestamp(seg['end'], ",")
                    srt_content += f"{i+1}\n{start} --> {end}\n{zh_texts[i]}\n{en_texts[i]}\n\n"
                
                with open("subtitles.srt", "w", encoding="utf-8") as f:
                    f.write(srt_content)
                
                st.write("🎬 [4/4] 正在將字幕無損封裝進影片中...")
                # 加入 metadata 讓 QuickTime 知道這是中文字幕
                subprocess.run([
                    "ffmpeg", "-y", "-i", "input_video.mp4", "-i", "subtitles.srt",
                    "-c", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=chi", "output_video.mp4"
                ])
                
                status.update(label="✅ 雙語字幕影片處理完成！", state="complete")
                with open("output_video.mp4", "rb") as f:
                    st.download_button("📥 下載雙語字幕影片 (.mp4)", f, file_name="bilingual_video.mp4")

            elif "配音音檔" in mode:
                chinese_text = " ".join([t for t in zh_texts if t])
                st.write("🎙️ [4/4] 正在生成 AI 中文配音...")
                communicate = edge_tts.Communicate(chinese_text, "zh-TW-HsiaoChenNeural")
                asyncio.run(communicate.save("output_chinese.mp3"))
                
                status.update(label="✅ 配音處理完成！", state="complete")
                st.audio("output_chinese.mp3")
                with open("output_chinese.mp3", "rb") as f:
                    st.download_button("📥 下載中文配音檔 (.mp3)", f, file_name="translated_audio.mp3")

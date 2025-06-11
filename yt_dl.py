import streamlit as st
import yt_dlp
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlparse, parse_qs
from io import BytesIO
from PIL import Image
import os
import re
import subprocess

# streamlit run yt_dl.py

# 檢查 url
def IsValidYtUrl(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.netloc in ["www.youtube.com", "youtube.com", "m.youtube.com"]:
            return "v" in parse_qs(parsed.query)
        if parsed.netloc == "youtu.be":
            return parsed.path.strip("/") != ""
        return False
    except Exception:
        return False


# 獲取影片信息
def GetUrlInfo(url: str) -> dict[str, any]:
    ydl_opts = {"quiet": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


# 影片時間相關
def FormatDuration(time: int) -> str:
    h = time // 3600
    m = (time % 3600) // 60
    s = time % 60
    return f"{h:02}:{m:02}:{s:02}"


def ParseDuration(time: str) -> int:
    h, m, s = [int(p) for p in time.strip().split(":")]
    return h * 3600 + m * 60 + s


def FixTime(time: str):
    parts = time.strip().split(":")
    if len(parts) > 3 or not all(p.isdigit() for p in parts):
        return "00:00:00"
    parts = [int(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return FormatDuration(ParseDuration(f"{h:02}:{m:02}:{s:02}"))


def FixTimeStart():
    time_st = FixTime(st.session_state["time_st"])
    p_st = ParseDuration(time_st)
    p_ed = ParseDuration(st.session_state["time_ed"])
    if p_st >= p_ed:
        time_st = FixTime(p_ed - 1)
    st.session_state["time_st"] = time_st
    UpdateSliderFromText()


def FixTimeEnd():
    time_ed = FixTime(st.session_state["time_ed"])
    p_st = ParseDuration(st.session_state["time_st"])
    p_ed = ParseDuration(time_ed)
    if p_ed > st.session_state["time"]:
        time_ed = FixTime(st.session_state["time"])
    elif p_st >= p_ed:
        time_ed = FixTime(p_st + 1)
    st.session_state["time_ed"] = time_ed
    UpdateSliderFromText()


def UpdateSliderFromText():
    st.session_state["slider_range"] = [
        ParseDuration(st.session_state["time_st"]),
        ParseDuration(st.session_state["time_ed"]),
    ]


def UpdateTextFromSlider():
    st.session_state["time_st"] = FormatDuration(
        int(st.session_state["slider_range"][0])
    )
    st.session_state["time_ed"] = FormatDuration(
        int(st.session_state["slider_range"][1])
    )


# 下載
def SanitizeFilename(title: str, id: str) -> str:
    # 移除非法字元，Windows 不允許 \ / : * ? " < > |
    sanitized = re.sub(r'[\\/:*?"<>|]', "_", title)
    # 移除控制字元和其他不可見字元
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "", sanitized)
    # 過長字串截斷
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    # 移除前後空白
    sanitized = sanitized.strip()
    # 如果結果是空字串，改用 id
    return sanitized if sanitized else id


def DownloadMp3(url: str):
    ydl_opts = {
        "quiet": True,
        "format": "bestaudio/best",
        "outtmpl": "%(title)s.%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_filename = ydl.prepare_filename(info)
        downloaded_mp3 = os.path.splitext(downloaded_filename)[0] + ".mp3"

    input_path = "temp.mp3"
    output_path = "trimmed.mp3"
    os.rename(downloaded_mp3, input_path)

    # 使用 ffmpeg 裁切
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-ss",
            st.session_state["time_st"],
            "-to",
            st.session_state["time_ed"],
            "-acodec",
            "copy",
            output_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 讀入裁切後的 mp3
    with open(output_path, "rb") as f:
        mp3_bytes = BytesIO(f.read())

    # 清理暫存檔
    os.remove(input_path)
    os.remove(output_path)

    return mp3_bytes


# streamlit 網頁
url = st.text_input("請輸入網址")

if IsValidYtUrl(url):
    info = GetUrlInfo(url)
    # 顯示封面
    with urlopen(info.get("thumbnail")) as response:
        data = response.read()
    img = Image.open(BytesIO(data))
    st.image(img, caption=info.get("title"), use_container_width=True)

    # 設定標題
    name = st.text_input("影片標題", value=info.get("title", "audio"))

    # 調整秒數
    time = info.get("duration")

    if "time" not in st.session_state or st.session_state["time"] != time:
        st.session_state["time"] = time
        st.session_state["time_st"] = "00:00:00"
        st.session_state["time_ed"] = FormatDuration(time)
        UpdateSliderFromText()

    st.text_input("開始時間：", key="time_st", on_change=FixTimeStart)
    st.text_input("結束時間", key="time_ed", on_change=FixTimeEnd)

    val = (
        ParseDuration(st.session_state["time_st"]),
        ParseDuration(st.session_state["time_ed"]),
    )

    st.select_slider(
        "調整時間(s)",
        options=range(0, time + 1),
        value=val,
        key="slider_range",
        on_change=UpdateTextFromSlider,
    )

    # 下載
    if st.button("獲取 MP3"):
        try:
            with st.spinner("正在處理並裁切音訊..."):
                file = DownloadMp3(url)
            st.success(f"已獲取 : {name}")
            st.success(f"{st.session_state['time_st']} ~ {st.session_state['time_ed']}")
            st.download_button(
                label="下載 MP3", data=file, file_name=f"{name}.mp3", mime="audio/mpeg"
            )
        except Exception as e:
            st.error(f"獲取失敗：{e}")
else:
    st.write("非有效 youtube 網址")

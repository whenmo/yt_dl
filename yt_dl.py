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


def DownloadMp3(dl_path: str, info: dict, url: str):
    name = SanitizeFilename(info.get("title", ""), info.get("id"))

    ydl_opts = {
        "quiet": True,
        "format": "bestaudio/best",
        "outtmpl": str(dl_path / f"{name}.%(ext)s"),
        # "ffmpeg_location": "ffmpeg.exe",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        filename = os.path.splitext(filename)[0] + ".mp3"
        return filename, name


def CutVideo(path: str):
    temp_path = path + ".temp.mp3"
    cmd = [
        "ffmpeg",
        "-i",
        path,
        "-ss",
        st.session_state["time_st"],
        "-to",
        st.session_state["time_ed"],
        "-c",
        "copy",  # 不重新編碼，快速且不失真
        temp_path,
    ]
    subprocess.run(cmd, check=True)
    os.replace(temp_path, path)


# streamlit 網頁
url = st.text_input("請輸入網址")

if IsValidYtUrl(url):
    info = GetUrlInfo(url)
    # 顯示封面
    with urlopen(info.get("thumbnail")) as response:
        data = response.read()
    img = Image.open(BytesIO(data))
    st.image(img, caption=info.get("title"), use_container_width=True)

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
        value=st.session_state["slider_range"],
        key="slider_range",
        on_change=UpdateTextFromSlider,
    )

    # 下載
    if st.button("下載 MP3"):
        dl_path = Path.home() / "Downloads/yt_dl"
        os.makedirs(dl_path, exist_ok=True)
        try:
            filename, name = DownloadMp3(dl_path, info, url)
            CutVideo(f"{dl_path}/{name}.mp3")
            with open(filename, "rb") as f:
                st.success(f"已下載至：\n{dl_path}/{name}.mp3")
        except Exception as e:
            st.error(f"下載失敗：{e}")
else:
    st.write("非有效 youtube 網址")

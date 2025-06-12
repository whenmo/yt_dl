import streamlit as st
import yt_dlp
from urllib.request import urlopen
from urllib.parse import urlparse, parse_qs
from io import BytesIO
from PIL import Image
import os
import re
import uuid
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


def FixTime(time: str) -> str:
    parts = time.strip().split(":")
    if len(parts) > 3 or not all(p.isdigit() for p in parts):
        return "00:00:00"
    parts = [int(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return FormatDuration(ParseDuration(f"{h:02}:{m:02}:{s:02}"))


def FixTimeStart() -> None:
    time_st = FixTime(st.session_state["time_st"])
    p_st = ParseDuration(time_st)
    p_ed = ParseDuration(st.session_state["time_ed"])
    if p_st >= p_ed:
        time_st = FixTime(p_ed - 1)
    st.session_state["time_st"] = time_st
    UpdateSliderFromText()


def FixTimeEnd() -> None:
    time_ed = FixTime(st.session_state["time_ed"])
    p_st = ParseDuration(st.session_state["time_st"])
    p_ed = ParseDuration(time_ed)
    if p_ed > st.session_state["time"]:
        time_ed = FixTime(st.session_state["time"])
    elif p_st >= p_ed:
        time_ed = FixTime(p_st + 1)
    st.session_state["time_ed"] = time_ed
    UpdateSliderFromText()


def UpdateSliderFromText() -> None:
    st.session_state["slider_range"] = (
        ParseDuration(st.session_state["time_st"]),
        ParseDuration(st.session_state["time_ed"]),
    )


def UpdateTextFromSlider() -> None:
    st.session_state["time_st"] = FormatDuration(st.session_state["slider_range"][0])
    st.session_state["time_ed"] = FormatDuration(st.session_state["slider_range"][1])


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


def CutVedio(get_msg, name: str) -> BytesIO:
    get_msg.text("下載完成！正在處理裁切...")

    # 檢查格式
    format = name.split(".")[-1].lower()
    format_arg = ["-c", "copy"]
    if format == "mp3":
        format_arg = ["-acodec", "copy"]

    # 設定 ffmpeg 參數
    temp_file = f"temp_{uuid.uuid4().hex}.{format}"
    subprocess_args = [
        "ffmpeg",
        "-y",
        "-i",
        name,
        "-ss",
        st.session_state["time_st"],
        "-to",
        st.session_state["time_ed"],
    ]

    subprocess_args.extend(format_arg)
    subprocess_args.append(temp_file)

    # 執行 ffmpeg
    result = subprocess.run(
        subprocess_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode != 0:
        raise RuntimeError("裁切失敗，請檢查輸入檔案或時間格式")

    # 讀入裁切後的 mp3
    with open(temp_file, "rb") as f:
        vedio_bytes = BytesIO(f.read())

    # 清理暫存檔
    os.remove(name)
    os.remove(temp_file)

    get_msg.empty()
    return vedio_bytes


def RemoveANSI(text: str) -> str:
    ansi_escape = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text.strip())


def progress_hook(get_msg):
    def temp(d):
        if d["status"] == "downloading":
            percent = RemoveANSI(d.get("_percent_str", ""))
            speed = RemoveANSI(d.get("_speed_str", ""))
            eta = RemoveANSI(d.get("_eta_str", ""))
            get_msg.text(f"進度: {percent}\n速度: {speed}\n剩餘時間: {eta}")
        elif d["status"] == "finished":
            get_msg.text("下載完成！ 正在處理檔案...")

    return temp


def GetMp3(url: str) -> None | BytesIO:
    get_msg = st.empty()
    ydl_opts = {
        "progress_hooks": [progress_hook(get_msg)],
        "quiet": True,
        "format": "bestaudio/best",
        "outtmpl": "%(title)s.%(ext)s",
        # "ffmpeg-location": "ffmpeg.exe",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            dl_name = ydl.prepare_filename(info)
            dl_name = os.path.splitext(dl_name)[0] + ".mp3"
        except Exception as e:
            st.error(f"下載失敗: {e}")
            return None
    return CutVedio(get_msg, dl_name)


def GetMp4(url: str) -> None | BytesIO:
    get_msg = st.empty()
    ydl_opts = {
        "progress_hooks": [progress_hook(get_msg)],
        "quiet": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
        "outtmpl": "%(title)s.%(ext)s",
        # "ffmpeg-location": "ffmpeg.exe",
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            dl_name = ydl.prepare_filename(info)
            dl_name = os.path.splitext(dl_name)[0] + ".mp4"
        except Exception as e:
            st.error(f"下載失敗: {e}")
            return None
    return CutVedio(get_msg, dl_name)


def DownloadFile(msg: list, file: None | BytesIO, filename: str, mime: str) -> None:
    if file:
        msg[0].success(f"已獲取 : {filename}")
        msg[1].success(f"{st.session_state['time_st']} ~ {st.session_state['time_ed']}")
        msg[2].download_button(label="下載", data=file, file_name=filename, mime=mime)
    else:
        msg[0].error("獲取失敗")


# streamlit 網頁

st.title("youtube 影片下載器")

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
        st.session_state["slider_range"] = (0, time)

    time_col_1, time_col_2 = st.columns(2)
    with time_col_1:
        st.text_input("開始時間：", key="time_st", on_change=FixTimeStart)
    with time_col_2:
        st.text_input("結束時間：", key="time_ed", on_change=FixTimeEnd)

    st.select_slider(
        "調整時間(s)",
        options=range(0, time + 1),
        value=st.session_state["slider_range"],
        key="slider_range",
        on_change=UpdateTextFromSlider,
    )

    # 下載
    dl_mp3_col, dl_mp4_col = st.columns(2)
    with dl_mp3_col:
        get_mp3 = st.button("獲取 MP3")
    with dl_mp4_col:
        get_mp4 = st.button("獲取 MP4")

    dl_msgs = [st.empty(), st.empty(), st.empty()]

    for msg in dl_msgs:
        msg.empty()

    # 獲取 mp3
    if get_mp3:
        with st.spinner("正在處理並裁切音訊..."):
            file = GetMp3(url)
        DownloadFile(dl_msgs, file, f"{name}.mp3", "audio/mpeg")

    # 獲取 mp4
    if get_mp4:
        with st.spinner("正在處理並裁切影片..."):
            file = GetMp4(url)
        DownloadFile(dl_msgs, file, f"{name}.mp4", "video/mp4")
else:
    st.write("非有效 youtube 網址")

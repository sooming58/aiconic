from streamlit_webrtc import webrtc_streamer, WebRtcMode, WebRtcStreamerContext
from aiortc.contrib.media import MediaRecorder
import soundfile as sf
import streamlit as st
from pathlib import Path
import time
import pydub
import whisper
#import json

# 녹음된 wav 파일 저장할 sound 폴더 생성
TMP_DIR = Path("C:/audio/sound")
if not TMP_DIR.exists():
    TMP_DIR.mkdir(exist_ok=True, parents=True)

if "wavpath" not in st.session_state:
    cur_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    st.session_state["wavpath"] = str(TMP_DIR / f"{cur_time}.wav")

wavpath = st.session_state["wavpath"]

# 오디오 입력 설정
MEDIA_STREAM_CONSTRAINTS = {
    "video": False,
    "audio": {
        "echoCancellation": False,
        "noiseSuppression": True,
        "autoGainControl": True,
    },
}

# 녹음1 - MediaRecorder
def aiortc_audio_recorder(wavpath):
    def recorder_factory():
        return MediaRecorder(wavpath)

    webrtc_ctx = webrtc_streamer(
        key="sendonly-audio",
        mode=WebRtcMode.SENDRECV,
        in_recorder_factory=recorder_factory,
        media_stream_constraints=MEDIA_STREAM_CONSTRAINTS,
    )

    if not webrtc_ctx.state.playing and Path(wavpath).exists():
        st.success(f"✅ 녹음 저장 완료: {wavpath}")
        display_wavfile(wavpath)


# 오디오 프레임 수집 -> pydub으로 저장
def save_frames_from_audio_receiver(wavpath):
    webrtc_ctx = webrtc_streamer(
        key = "sendonly-audio",
        mode = WebRtcMode.SENDONLY,
        media_stream_constraints=MEDIA_STREAM_CONSTRAINTS,
    )

    if "audio_buffer" not in st.session_state:
        st.session_state["audio_buffer"] = pydub.AudioSegment.empty()

    while True:
        if webrtc_ctx.audio_receiver:
            audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
            for audio_frame in audio_frames:
                sound = pydub.AudioSegment(
                    data=audio_frame.to_ndarray().tobytes(),
                    sample_width=audio_frame.format.bytes,
                    frame_rate=audio_frame.sample_rate,
                    channels=len(audio_frame.layout.channels),
                )
                st.session_state["audio_buffer"] += sound
        else:
            break

    # 녹음이 끝나면 버퍼를 WAV로 저장
    audio_buffer = st.session_state["audio_buffer"]
    if not webrtc_ctx.state.playing and len(audio_buffer) > 0:
        audio_buffer.export(wavpath, format="wav")
        st.session_state["audio_buffer"] = pydub.AudioSegment.empty()

# 저장된 wav 파일 재생
def display_wavfile(wavpath):
    audio_bytes = open(wavpath, 'rb').read()
    file_type = Path(wavpath).suffix
    st.audio(audio_bytes, format=f'audio/{file_type}', start_time=0)

# 메인 페이지
def record_page():
    st.markdown('# recorder')
    if "wavpath" not in st.session_state:
        cur_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        tmp_wavpath = TMP_DIR / f'{cur_time}.wav'
        st.session_state["wavpath"] = str(tmp_wavpath)

    wavpath = st.session_state["wavpath"]

    #aiortc_audio_recorder(wavpath)  # 첫 번째 방식 실행
    save_frames_from_audio_receiver(wavpath)  # 두 번째 방식 실행 가능

    if Path(wavpath).exists():
        st.markdown(wavpath)
        display_wavfile(wavpath)

record_page()

#whisper 변환
if st.button("변환"):
    if Path(wavpath).exists():
        model = whisper.load_model("small")
        result = model.transcribe(str(wavpath))
        st.success("✅ 변환 완료")
        st.write(result["text"])
    else:
        st.error("❌ 녹음된 파일이 없습니다. 먼저 녹음을 해주세요.")
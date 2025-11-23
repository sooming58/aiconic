import streamlit as st
from streamlit.components.v1 import html
from cryptography.fernet import Fernet
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
import os
import hashlib
import base64
from gtts import gTTS
from streamlit_webrtc import webrtc_streamer, WebRtcMode, WebRtcStreamerContext
from aiortc.contrib.media import MediaRecorder
import soundfile as sf
from pathlib import Path
import time
import pydub
import whisper

# 오디오 녹음 파일 저장 경로
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


# 텍스트 → 오디오 재생 함수
def tts_play(text):
    """문자를 음성(mp3)으로 생성 후 HTML로 재생"""
    tts = gTTS(text=text, lang='ko')
    mp3 = BytesIO()
    tts.write_to_fp(mp3)
    mp3.seek(0)
    b64 = base64.b64encode(mp3.read()).decode()

    audio_html = f"""
        <audio autoplay>
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

# 기본 페이지 설정
st.set_page_config(page_title="secret.py", layout="centered")

st.markdown(
    """
    <style>
    .big-btn { font-size:20px; padding:18px 24px; border-radius:12px; cursor:pointer; }
    .high-contrast { background-color:#0B5FFF; color: #FFFFFF; border:none; }
    .guide-box { background-color:#e8f0fe; padding:15px; border-radius:10px; border: 1px solid #0B5FFF; margin-bottom: 20px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("음성 기반 서류 자동 완성 서비스")

# 세션 상태 변수 초기화
if 'plain_text' not in st.session_state:
    st.session_state.plain_text = ""
if 'final_content' not in st.session_state:
    st.session_state.final_content = ""
if 'is_encrypted' not in st.session_state:
    st.session_state.is_encrypted = False


# [1단계] 서류 종류 선택
st.header("[1단계] 서류 종류 선택")

if st.button("🔊 1단계 안내 듣기"):
    tts_play("1단계입니다. 작성할 서류 종류를 선택하는 단계입니다. 근로계약서 또는 주민등록등본 신청서 중 하나를 선택해주세요.")

template_options = {
    "근로계약서": {
        "guide": "[📢입력 가이드]\n\n이 서류는 '이름', '근무지', '시급', '근무시간' 순서로 말씀해 주세요.\n\n예시: 홍길동, XX수학 학원, 시급 만원, 아침 9시부터 6시까지"
    },
    "주민등록등본 신청서": {
        "guide": "[📢입력 가이드]\n\n이 서류는 '성명', '거주지 주소', '주민등록번호' 순서로 말씀해 주세요.\n\n예시: 오지헌, 대구 북구, 950101-1234567"
    }
}

selected_template = st.selectbox("작성할 서류 종류를 선택하세요.", list(template_options.keys()))

st.markdown(f"""<div class="guide-box">{template_options[selected_template]['guide']}</div>""", unsafe_allow_html=True)


# [2단계] 개인정보 음성 입력
st.markdown("### 오디오 녹음")
save_frames_from_audio_receiver(wavpath)

# 녹음된 파일이 있으면 재생
if Path(wavpath).exists():
    st.markdown(f"**녹음 파일:** {wavpath}")
    display_wavfile(wavpath)
    
    # Whisper 변환 버튼
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🎤 Whisper로 텍스트 변환", key="whisper_convert", help="녹음된 오디오를 텍스트로 변환합니다."):
            with st.spinner("Whisper 모델 로딩 및 변환 중..."):
                try:
                    model = whisper.load_model("small")
                    result = model.transcribe(str(wavpath))
                    transcribed_text = result["text"]
                    st.session_state["voice_text"] = transcribed_text
                    st.success("✅ 변환 완료")
                except Exception as e:
                    st.error(f"❌ 변환 중 오류 발생: {str(e)}")
    with col2:
        if st.button("🔄 녹음 초기화", key="reset_recording", help="녹음을 초기화합니다."):
            if "audio_buffer" in st.session_state:
                st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
            cur_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
            st.session_state["wavpath"] = str(TMP_DIR / f"{cur_time}.wav")
            st.rerun()

# 음성에서 가져온 텍스트 표시
st.markdown("### 음성에서 가져온 텍스트")
if st.session_state.get("voice_text"):
    st.text_area("Recognized text (from voice)", value=st.session_state.get("voice_text", ""), key="voice_text", height=140, label_visibility="collapsed")
else:
    st.text_area("Recognized text (from voice)", value="", key="voice_text", height=140, label_visibility="collapsed",
                 help="위의 녹음 후 'Whisper로 텍스트 변환' 버튼을 누르거나 직접 입력하세요.")


# [3단계] 암호화
st.header("[3단계] 개인정보 암호화 저장")

if st.button("🔊 3단계 안내 듣기"):
    tts_play("3단계입니다. 비밀번호 네 자리로 입력한 정보를 암호화할 수 있습니다.")

st.markdown("**현재 정보 상태:**")
if st.session_state.is_encrypted:
    st.success("🔒 암호화됨")
else:
    st.warning("🔓 평문 상태")

password = st.text_input("비밀번호 숫자 4자리를 입력하세요", type="password")

if st.button("🔒 암호화하여 저장하기"):
    if not st.session_state.plain_text:
        st.error("입력된 텍스트가 없습니다.")
    elif not password:
        st.error("비밀번호를 입력해주세요.")
    else:
        try:
            key_hash = hashlib.sha256(password.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(key_hash)
            cipher = Fernet(fernet_key)
            encrypted = cipher.encrypt(st.session_state.plain_text.encode()).decode()

            st.session_state.final_content = encrypted
            st.session_state.is_encrypted = True
            st.success("암호화 완료!")
        except Exception as e:
            st.error(str(e))


# [4단계] PDF 생성
st.header("[4단계] 서류 확인 및 다운로드")

if st.button("🔊 4단계 안내 듣기"):
    tts_play("4단계입니다. 입력한 내용을 PDF 파일로 생성할 수 있습니다.")

display_text = st.session_state.final_content

if st.session_state.is_encrypted:
    if st.checkbox("👀 비밀번호로 화면에서만 복호화해서 보기"):
        pw = st.text_input("비밀번호:", type="password")
        if pw:
            try:
                key_hash_dec = hashlib.sha256(pw.encode()).digest()
                fernet_key_dec = base64.urlsafe_b64encode(key_hash_dec)
                cipher_dec = Fernet(fernet_key_dec)
                display_text = cipher_dec.decrypt(st.session_state.final_content.encode()).decode()
                st.success("화면 복호화 성공")
            except:
                display_text = "❌ 비밀번호 오류!"

st.text_area("서류 데이터 확인:", value=display_text, height=150, disabled=True)


if st.button("📄 PDF 서류 생성하기"):
    pdf_content = st.session_state.plain_text

    if not pdf_content:
        st.error("PDF로 만들 데이터가 없습니다.")
    else:
        try:
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            width, height = A4

            font_path = "C:/Windows/Fonts/malgun.ttf"
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('Malgun', font_path))
                font_name = "Malgun"
            else:
                font_name = "Helvetica"

            if selected_template == "근로계약서":
                c.setFont(font_name, 24)
                c.drawCentredString(width/2, height - 80, "표준 근로 계약서")
                c.line(50, height - 100, width - 50, height - 100)

            elif selected_template == "주민등록등본 신청서":
                c.setFont(font_name, 20)
                c.drawCentredString(width/2, height - 60, "주민등록표 등본 교부 신청서")

            c.setFont(font_name, 12)
            text = c.beginText(50, height - 150)
            for line in pdf_content.split("\n"):
                text.textLine(line)
            c.drawText(text)

            c.save()
            buffer.seek(0)

            st.success("PDF 생성 완료!")
            st.download_button("📥 PDF 다운로드", data=buffer, file_name="document.pdf", mime="application/pdf")

        except Exception as e:
            st.error("PDF 생성 중 오류: " + str(e))

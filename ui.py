# app.py
import streamlit as st
from streamlit.components.v1 import html
from cryptography.fernet import Fernet
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from streamlit_webrtc import webrtc_streamer, WebRtcMode, WebRtcStreamerContext
from aiortc.contrib.media import MediaRecorder
import soundfile as sf
from pathlib import Path
import time
import pydub
import whisper

st.set_page_config(page_title="Accessible Voice→PDF", layout="centered")

# --- Audio recording setup (from audio_new.py) ---
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

# --- Styles for big buttons, high contrast, accessible fonts ---
st.markdown(
    """
    <style>
    .big-btn { font-size:20px; padding:18px 24px; border-radius:12px; }
    .high-contrast { background-color:#0B5FFF; color: #FFFFFF; }
    .container { max-width:900px; margin: 0 auto; }
    label[for="template_select"] { font-weight:700; }
    .sr-only { position: absolute; left: -10000px; top: auto; width: 1px; height: 1px; overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("# 시각장애인을 위한 음성 기반 개인정보 입력 및 서류 자동 작성 서비스")
st.markdown(
    "음성 입력 → 텍스트 확인 → 텍스트 암호화(선택) → 템플릿 선택 → PDF 생성\n\n"
    "**설명:** 큰 버튼, 색상 대비, 스크린리더(aria) 지원, 음성 안내 포함."
)

# --- Voice recorder & speech-to-text (WebRTC + Whisper) ---
st.markdown("## 1. 음성 입력 (WebRTC 녹음 + Whisper 변환)")

# 녹음 섹션
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

# --- Encryption section ---
st.markdown("## 2. 텍스트 암호화 (선택)")
encrypt = st.checkbox("텍스트 암호화 사용하기", value=False)
password_key = None
encrypted_text = None

if encrypt:
    # Generate key from passphrase (simple). For production, use proper KDF (PBKDF2HMAC) with salt.
    passphrase = st.text_input("암호(복호화 시 필요)", type="password", help="복호화하려면 동일한 암호를 사용하세요.")
    if passphrase:
        # derive a fernet key (NOTE: simplified; production => use PBKDF2HMAC+salt)
        import base64, hashlib
        k = hashlib.sha256(passphrase.encode()).digest()
        key = base64.urlsafe_b64encode(k)
        f = Fernet(key)
        raw = st.session_state.get("voice_text", "")
        if raw:
            if st.button("암호화", key="encrypt_btn"):
                token = f.encrypt(raw.encode())
                encrypted_text = token.decode()
                st.success("암호화 완료. 복호화하려면 같은 암호 사용.")
                st.code(encrypted_text, language=None)
        else:
            st.info("먼저 텍스트를 입력/전송하세요.")
else:
    st.info("암호화를 사용하지 않으면 원문이 PDF로 저장됩니다.")

# allow manual editing of final text to be put into PDF
st.markdown("## 3. 최종 텍스트 (PDF로 생성될 내용)")
final_text = st.text_area("Final text (editable)", value=(encrypted_text or st.session_state.get("voice_text","")), height=200)

# --- Template selection ---
st.markdown("## 4. 템플릿 선택")
template = st.selectbox("템플릿을 선택하세요", options=["Simple (타이틀+본문)","Letter (편지형)","Report (보고서형)"], key="template_select")

# Accessibility hint for screen readers
st.markdown('<div role="note" aria-live="polite">템플릿을 선택한 뒤 PDF 생성 버튼을 누르세요.</div>', unsafe_allow_html=True)

# --- PDF generation ---
st.markdown("## 5. PDF 생성")
col1, col2 = st.columns([1,1])
with col1:
    if st.button("PDF 생성", key="generate_pdf", help="선택된 템플릿으로 PDF를 만듭니다.",):
        # build PDF in memory
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        margin = 50
        title = "Generated Document"
        if template == "Simple (타이틀+본문)":
            c.setFont("Helvetica-Bold", 20)
            c.drawString(margin, height - margin - 10, title)
            c.setFont("Helvetica", 12)
            text_obj = c.beginText(margin, height - margin - 40)
            for line in final_text.splitlines():
                text_obj.textLine(line)
            c.drawText(text_obj)
        elif template == "Letter (편지형)":
            c.setFont("Helvetica", 12)
            text_obj = c.beginText(margin, height - margin - 10)
            text_obj.textLine("To whom it may concern,")
            text_obj.textLine("")
            for line in final_text.splitlines():
                text_obj.textLine(line)
            text_obj.textLine("")
            text_obj.textLine("Sincerely,")
            text_obj.textLine("Streamlit User")
            c.drawText(text_obj)
        else:  # Report
            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(width/2, height - margin, "REPORT")
            c.setFont("Helvetica", 11)
            text_obj = c.beginText(margin, height - margin - 40)
            for line in final_text.splitlines():
                text_obj.textLine(line)
            c.drawText(text_obj)

        c.showPage()
        c.save()
        buffer.seek(0)
        st.session_state["last_pdf"] = buffer.read()
        st.success("PDF 생성 완료.")
with col2:
    if st.session_state.get("last_pdf", None):
        st.download_button("PDF 다운로드", data=st.session_state["last_pdf"], file_name="document.pdf", mime="application/pdf", key="dl_pdf",)
    else:
        st.info("PDF를 먼저 생성하세요.")
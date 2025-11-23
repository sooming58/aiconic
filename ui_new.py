import streamlit as st
from cryptography.fernet import Fernet
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
import os
import hashlib
import base64
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from pathlib import Path
import time
import pydub
import whisper

# ==========================================
# [0] 페이지 설정 및 초기화
# ==========================================
st.set_page_config(page_title="Accessible Voice → PDF", layout="centered")

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

# 녹음된 wav 파일 저장할 sound 폴더 생성
TMP_DIR = Path("C:/audio/sound")
if not TMP_DIR.exists():
    TMP_DIR.mkdir(exist_ok=True, parents=True)

# 세션 상태 변수 초기화
if 'plain_text' not in st.session_state:
    st.session_state.plain_text = ""      # 원본 텍스트 (PDF 생성용)
if 'final_content' not in st.session_state:
    st.session_state.final_content = ""   # 화면 표시용 (암호문일 수 있음)
if 'is_encrypted' not in st.session_state:
    st.session_state.is_encrypted = False
if 'wavpath' not in st.session_state:
    cur_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    st.session_state["wavpath"] = str(TMP_DIR / f"{cur_time}.wav")
if 'audio_buffer' not in st.session_state:
    st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
if 'whisper_text' not in st.session_state:
    st.session_state.whisper_text = ""

# ==========================================
# [1단계] 서류 종류 선택
# ==========================================
st.header("[1단계] 서류 종류 선택")

template_options = {
    "근로계약서": {
        "guide": "[📢입력 가이드]\n\n이 서류는 '이름', '근무지', '시급', '근무시간' 순서로 말씀해 주세요.\n\n(예시: \"홍길동, XX수학 학원, 시급 만원, 아침 9시부터 6시까지\")"
    },
    "주민등록등본 신청서": {
        "guide": "[📢입력 가이드]\n\n이 서류는 '성명', '거주지 주소', '주민등록번호' 순서로 말씀해 주세요.\n\n(예시: \"오지헌, 대구광역시 북구, 950101-1234567\")"
    }
}

selected_template = st.selectbox("작성할 서류 종류를 선택하세요.", list(template_options.keys()))
st.markdown(f"""<div class="guide-box">{template_options[selected_template]['guide']}</div>""", unsafe_allow_html=True)


# ==========================================
# [2단계] 개인정보 음성 입력
# ==========================================
st.header("[2단계] 개인정보 음성 입력")

# WebRTC 녹음 기능
st.subheader("🎤 오디오 녹음")

MEDIA_STREAM_CONSTRAINTS = {
    "video": False,
    "audio": {
        "echoCancellation": False,
        "noiseSuppression": True,
        "autoGainControl": True,
    },
}

wavpath = st.session_state["wavpath"]

# 오디오 프레임 수집 함수 (audio_new.py 기반)
def process_audio_frames(webrtc_ctx):
    if webrtc_ctx.audio_receiver:
        try:
            audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
            for audio_frame in audio_frames:
                sound = pydub.AudioSegment(
                    data=audio_frame.to_ndarray().tobytes(),
                    sample_width=audio_frame.format.bytes,
                    frame_rate=audio_frame.sample_rate,
                    channels=len(audio_frame.layout.channels),
                )
                st.session_state["audio_buffer"] += sound
        except Exception:
            pass  # 타임아웃 등은 정상

# WebRTC 스트리머
webrtc_ctx = webrtc_streamer(
    key="sendonly-audio",
    mode=WebRtcMode.SENDONLY,
    media_stream_constraints=MEDIA_STREAM_CONSTRAINTS,
)

# 오디오 프레임 수집
if webrtc_ctx.audio_receiver:
    process_audio_frames(webrtc_ctx)

# 녹음 중지 시 파일 저장
if not webrtc_ctx.state.playing and len(st.session_state["audio_buffer"]) > 0:
    st.session_state["audio_buffer"].export(wavpath, format="wav")
    st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
    st.success(f"✅ 녹음이 저장되었습니다: {wavpath}")
    # 새 파일 경로 생성
    cur_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    st.session_state["wavpath"] = str(TMP_DIR / f"{cur_time}.wav")

# 저장된 파일 재생
if Path(wavpath).exists():
    st.subheader("📼 녹음된 오디오")
    audio_bytes = open(wavpath, 'rb').read()
    st.audio(audio_bytes, format='audio/wav', start_time=0)
    
    # Whisper 변환 버튼
    if st.button("🎯 Whisper로 텍스트 변환하기", type="primary"):
        with st.spinner("음성을 텍스트로 변환 중..."):
            try:
                model = whisper.load_model("small")
                result = model.transcribe(str(wavpath))
                st.session_state.whisper_text = result["text"]
                st.success("✅ 변환 완료!")
                
                # 변환된 텍스트를 자동으로 입력 텍스트로 설정
                if st.session_state.whisper_text:
                    st.session_state.plain_text = st.session_state.whisper_text
                    st.session_state.final_content = st.session_state.whisper_text
                    st.session_state.is_encrypted = False
            except Exception as e:
                st.error(f"변환 중 오류 발생: {e}")

# Whisper 변환 결과 표시
if st.session_state.whisper_text:
    st.subheader("📝 변환된 텍스트")
    st.text_area("", value=st.session_state.whisper_text, height=100, key="whisper_output", disabled=True)
    input_text = st.text_area("📝 텍스트 수정 (필요시):", value=st.session_state.whisper_text, height=100, key="input_area")
else:
    input_text = st.text_area("📝 텍스트 입력 또는 위에서 변환하기:", height=100, key="input_area")

if input_text:
    if st.session_state.plain_text != input_text:
        st.session_state.plain_text = input_text
        st.session_state.final_content = input_text
        st.session_state.is_encrypted = False


# ==========================================
# [3단계] 개인정보 암호화 저장
# ==========================================
st.header("[3단계] 개인정보 암호화 저장")

st.markdown("**현재 정보 상태:**")
if st.session_state.is_encrypted:
    st.success("🔒 암호화됨 (안전)")
else:
    st.warning("🔓 평문 상태 (암호화 필요)")

password = st.text_input("비밀번호 숫자 4자리를 입력하세요 (암호화 키 생성용)", type="password")

if st.button("🔒 암호화하여 저장하기", type="primary"):
    if not st.session_state.plain_text:
        st.error("입력된 텍스트가 없습니다.")
    elif not password:
        st.error("비밀번호를 입력해주세요.")
    else:
        try:
            key_hash = hashlib.sha256(password.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(key_hash)
            cipher = Fernet(fernet_key)
            
            encrypted_bytes = cipher.encrypt(st.session_state.plain_text.encode())
            st.session_state.final_content = encrypted_bytes.decode()
            
            st.session_state.is_encrypted = True
            st.success("✅ 암호화 완료!")
        except Exception as e:
            st.error(f"오류: {e}")


# ==========================================
# [4단계] 서류 확인 및 다운로드 (수정됨)
# ==========================================
st.markdown("---")
st.header("[4단계] 서류 확인 및 다운로드")

# 화면 표시용 텍스트 (기본적으로는 암호화된 내용을 보여줌)
display_text = st.session_state.final_content

if st.session_state.is_encrypted:
    st.info("🔒 데이터가 암호화되어 보호 중입니다.")
    
    # 비밀번호 입력 시 화면만 복호화해서 보여줌 (PDF 생성과는 무관하게 보기 전용)
    if st.checkbox("👀 비밀번호 입력하고 화면에서 원본 확인하기"):
        dec_pw = st.text_input("비밀번호:", type="password", key="dec_pw_input")
        if dec_pw:
            try:
                key_hash_dec = hashlib.sha256(dec_pw.encode()).digest()
                fernet_key_dec = base64.urlsafe_b64encode(key_hash_dec)
                cipher_dec = Fernet(fernet_key_dec)
                
                decrypted_bytes = cipher_dec.decrypt(st.session_state.final_content.encode())
                display_text = decrypted_bytes.decode() # 화면 갱신
                st.success("🔓 화면 복호화 성공!")
            except:
                display_text = "❌ 비밀번호 오류!"
else:
    st.info("ℹ️ 암호화되지 않은 상태입니다.")

# 화면에 보이는 텍스트창 (수정 불가)
final_view = st.text_area("서류 데이터 (화면 확인용):", value=display_text, height=150, disabled=True)


# [핵심 수정] PDF 생성 버튼
if st.button("📄 PDF 서류 생성하기", type="primary", use_container_width=True):
    # PDF를 만들 데이터는 '화면에 보이는 것(final_view)'이 아니라,
    # 메모리에 안전하게 저장된 '원본(plain_text)'을 사용합니다!
    # 따라서 사용자가 비밀번호를 입력 안 해서 화면이 암호문이라도, PDF는 원본으로 나옵니다.
    
    pdf_content = st.session_state.plain_text # <-- 여기가 핵심!
    
    if not pdf_content:
         st.error("생성할 데이터가 없습니다.")
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
                
                c.setFont(font_name, 12)
                c.drawString(50, height - 150, "계약 내용:")
                
                text_obj = c.beginText(50, height - 180)
                text_obj.setFont(font_name, 12)
                
                # 원본 데이터(pdf_content)를 사용
                for line in pdf_content.split('\n'):
                    text_obj.textLine(line)
                c.drawText(text_obj)
                
                c.drawString(50, 100, "상기된 위 내용에 동의하며 근로계약을 체결합니다.")
                c.drawString(350, 80, "(인) _______________")

            elif selected_template == "주민등록등본 신청서":
                c.setFont(font_name, 20)
                c.drawCentredString(width/2, height - 60, "주민등록표 등본 교부 신청서")
                c.rect(40, height - 300, width - 80, 200)
                c.setFont(font_name, 12)
                c.drawString(60, height - 150, f"신청 상세 내용:")
                
                text_obj = c.beginText(60, height - 170)
                text_obj.setFont(font_name, 12)
                
                # 원본 데이터(pdf_content)를 사용
                for line in pdf_content.split('\n'):
                    text_obj.textLine(line)
                c.drawText(text_obj)
                
                c.drawString(60, height - 280, "신청일: 2025년 11월 __일")

            c.save()
            buffer.seek(0)
            st.success("✅ 생성 완료! PDF에는 원본 정보가 담겼습니다.")
            st.download_button("📥 PDF 다운로드", data=buffer, file_name="document.pdf", mime="application/pdf", use_container_width=True)
            
        except Exception as e:
            st.error(f"PDF 생성 중 오류 발생: {e}")
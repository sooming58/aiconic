import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode
import av
import numpy as np
import whisper
import wave
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List


class AudioFrameBuffer:
    def __init__(self) -> None:
        self.sample_rate = 16000
        self.channels = 1
        self._frames: List[np.ndarray] = []

    def append(self, frame: av.AudioFrame) -> None:
        audio = frame.to_ndarray()
        # audio shape: (channels, samples)
        audio = audio.astype(np.float32)
        self.sample_rate = frame.sample_rate
        self.channels = audio.shape[0]
        self._frames.append(audio)

    def clear(self) -> None:
        self._frames.clear()

    def to_wav_bytes(self) -> bytes:
        if not self._frames:
            raise ValueError("수집된 오디오 프레임이 없습니다.")

        audio = np.concatenate(self._frames, axis=1)
        # 모노 변환 (평균) 후 int16로 스케일링
        mono = audio.mean(axis=0)
        mono = np.clip(mono, -32768, 32767)
        int16_audio = mono.astype(np.int16)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            with wave.open(tmp.name, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # int16
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(int16_audio.tobytes())
            tmp_path = Path(tmp.name)

        wav_bytes = tmp_path.read_bytes()
        tmp_path.unlink(missing_ok=True)
        return wav_bytes


class AudioProcessor:
    def __init__(self, buffer: AudioFrameBuffer):
        self.buffer = buffer

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        self.buffer.append(frame)
        return frame


def init_session_state() -> None:
    if "audio_buffer" not in st.session_state:
        st.session_state.audio_buffer = AudioFrameBuffer()
    if "wav_file" not in st.session_state:
        st.session_state.wav_file = None
    if "wav_bytes" not in st.session_state:
        st.session_state.wav_bytes = None
    if "transcript" not in st.session_state:
        st.session_state.transcript = ""


def main() -> None:
    st.set_page_config(page_title="마이크 → Whisper 변환", page_icon="🎙️")
    st.title("마이크 녹음 → Whisper 변환 파이프라인")
    st.write(
        "스트림릿에서 `streamlit-webrtc`로 녹음한 뒤 WAV로 저장하고 Whisper로 음성을 텍스트로 변환합니다."
    )

    init_session_state()

    model_name = st.selectbox("Whisper 모델 선택", ["base", "small", "medium"], index=0)
    buffer = st.session_state.audio_buffer

    webrtc_ctx = webrtc_streamer(
        key="speech-to-text",
        mode=WebRtcMode.SENDONLY,
        media_stream_constraints={"audio": True, "video": False},
        audio_processor_factory=lambda: AudioProcessor(buffer),
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("녹음 프레임 초기화", use_container_width=True):
            buffer.clear()
            st.session_state.wav_file = None
            st.session_state.wav_bytes = None
            st.session_state.transcript = ""
            st.success("프레임을 초기화했습니다.")

    with col2:
        if st.button("WAV 파일 생성", use_container_width=True):
            try:
                wav_bytes = buffer.to_wav_bytes()
            except ValueError as err:
                st.error(str(err))
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                wav_path = Path(tempfile.gettempdir()) / f"recording_{timestamp}.wav"
                wav_path.write_bytes(wav_bytes)
                st.session_state.wav_file = wav_path
                st.session_state.wav_bytes = wav_bytes
                st.success(f"WAV 파일 저장 완료: {wav_path}")

    wav_path = st.session_state.get("wav_file")
    wav_bytes = st.session_state.get("wav_bytes")

    if wav_bytes:
        st.audio(wav_bytes, format="audio/wav")

    if wav_path and not wav_path.exists():
        st.warning("저장한 WAV 파일을 찾을 수 없습니다. 다시 생성해 주세요.")
        st.session_state.wav_file = None
        wav_path = None

    if wav_bytes:
        if st.button("Whisper 변환 실행", use_container_width=True):
            with st.spinner("Whisper 모델 로딩 및 변환 중..."):
                model = whisper.load_model(model_name)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
                    tmp_wav.write(wav_bytes)
                    tmp_wav_path = Path(tmp_wav.name)
                try:
                    result = model.transcribe(str(tmp_wav_path))
                finally:
                    tmp_wav_path.unlink(missing_ok=True)
                st.session_state.transcript = result["text"]

    if st.session_state.transcript:
        st.subheader("변환 결과")
        st.write(st.session_state.transcript)

    st.markdown("----")
    st.caption("필요 패키지: `streamlit`, `streamlit-webrtc`, `openai-whisper`, `av`")


if __name__ == "__main__":
    main()

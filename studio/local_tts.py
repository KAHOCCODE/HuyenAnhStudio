"""A reusable CPU model process; the GUI never imports ML packages."""
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

from .tts import TTSServiceError, TTSRequestError
from .voices import local_voice_name

ROOT = Path(__file__).resolve().parent.parent


def local_python():
    configured = os.environ.get('HUYENANH_TTS_PYTHON')
    path = Path(configured) if configured else ROOT / '.tts-venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not path.is_file():
        raise TTSServiceError('Chưa cài bộ giọng VieNeu. Đóng app, chạy CAI-GIONG-MIEN-PHI.cmd một lần rồi mở lại. MP3 đã có được giữ nguyên.')
    return path


class LocalTTSSession:
    def __init__(self, python=None, worker=None):
        self.python = python
        self.worker = worker
        self.proc = None
        self.reader = None
        self.events = queue.Queue()
        self.errors = None
        self._ready = False
        self.lock = threading.Lock()

    @property
    def ready(self):
        proc = self.proc
        return self._ready and proc is not None and proc.poll() is None

    def _start(self, cancel, report):
        if cancel.is_set():
            raise InterruptedError('Đã hủy tạo giọng.')
        python = self.python or local_python()
        env = dict(os.environ, PYTHONUTF8='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
                   GRADIO_ANALYTICS_ENABLED='False', TOKENIZERS_PARALLELISM='false', CUDA_VISIBLE_DEVICES='-1')
        # Shared across projects. SDK downloads public model files on first use only.
        env.setdefault('HF_HOME', str(ROOT / 'models' / 'vieneu'))
        self.errors = tempfile.TemporaryFile()
        try:
            self.proc = subprocess.Popen([str(python), '-u', str(self.worker or ROOT / 'tools' / 'vieneu_worker.py')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
                text=True, encoding='utf-8', errors='replace', bufsize=1, env=env,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

            def read():
                try:
                    for line in self.proc.stdout:
                        try:
                            message = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(message, dict):
                            self.events.put(message)
                finally:
                    self.events.put({'event': 'exit'})

            self.reader = threading.Thread(target=read, daemon=True)
            self.reader.start()
            self._wait('ready', cancel, report, loading=True)
            self._ready = True
        except BaseException:
            self.close()
            raise

    def _wait(self, event, cancel, report, loading=False):
        began = time.monotonic()
        last = -5
        phase = 'Đang khởi động bộ đọc VieNeu' if loading else 'VieNeu đang đọc câu trên CPU'
        while True:
            if cancel.is_set():
                raise InterruptedError('Đã hủy tạo giọng; MP3 đã có được giữ lại.')
            elapsed = time.monotonic() - began
            if report and elapsed - last >= 5:
                report(phase + f' · {elapsed:.0f}s')
                last = elapsed
            if elapsed > (3600 if loading else 600):
                raise TTSServiceError('VieNeu chờ quá lâu. Hủy rồi chạy tiếp để dùng lại MP3 đã có; kiểm tra bộ cài / mô hình nếu lỗi lặp lại.')
            try:
                message = self.events.get(timeout=.1)
            except queue.Empty:
                continue
            if message.get('event') == event:
                return message
            if message.get('event') == 'phase':
                phase = message.get('message', phase)
                if report:report(phase)
                last = elapsed
                continue
            if message.get('event') == 'download':
                done = max(0, float(message.get('downloaded', 0)))
                total = max(0, float(message.get('total') or 0))
                size = f'{done/1048576:.1f}' + (f'/{total/1048576:.1f} MB · {min(100,100*done/total):.0f}%' if total else ' MB')
                phase = f'Đang tải {message.get("filename", "mô hình")} · {size}'
                if report:report(phase)
                last = elapsed
                continue
            if message.get('event') == 'error':
                cls = TTSServiceError if loading or message.get('fatal') else TTSRequestError
                raise cls('VieNeu: ' + message.get('message', 'Không tạo được âm thanh.'))
            if message.get('event') == 'exit':
                raise TTSServiceError('Bộ giọng VieNeu đã dừng. Máy có thể thiếu RAM hoặc thư viện. Chạy lại CAI-GIONG-MIEN-PHI.cmd, đóng bớt ứng dụng rồi thử một câu; MP3 đã có được giữ lại.')

    def speak(self, text, voice, target, cancel, report=None):
        while not self.lock.acquire(timeout=.1):
            if cancel.is_set():raise InterruptedError('Đã hủy tạo giọng.')
        try:
            self._speak(text, voice, target, cancel, report)
        except (InterruptedError, TTSServiceError):
            # An interrupted pipe cannot safely reuse a delayed response on the next cue.
            self.close()
            raise
        finally:
            self.lock.release()

    def _speak(self, text, voice, target, cancel, report=None):
        name = local_voice_name(voice)
        if not self.ready:
            self.close()
            self._start(cancel, report)
        if cancel.is_set():
            raise InterruptedError('Đã hủy tạo giọng.')
        try:
            self.proc.stdin.write(json.dumps({'text': text, 'voice': name, 'target': str(Path(target).resolve())}, ensure_ascii=True) + '\n')
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise TTSServiceError('Bộ giọng VieNeu đã ngắt. Chạy tiếp để dùng lại các câu đã xong.')
        self._wait('done', cancel, report)
        if not Path(target).is_file() or Path(target).stat().st_size <= 44:
            raise TTSRequestError('VieNeu không trả về âm thanh; mở câu này để nghe / tạo lại.')

    def close(self):
        self._ready = False
        if self.proc:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait()
            if self.reader:
                self.reader.join(timeout=2)
            for stream in (self.proc.stdin, self.proc.stdout):
                if stream:
                    stream.close()
        if self.errors:
            self.errors.close()
        self.proc = None
        self.reader = None
        self.errors = None
        self.events = queue.Queue()


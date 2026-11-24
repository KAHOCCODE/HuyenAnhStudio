"""Private JSON-lines worker. No API server, GPU packages or per-request network."""
import contextlib
import importlib.metadata
import json
import os
import sys
import threading
import time


def install_download_progress(emit):
    """Observe the SDK's public Hub downloader without changing cache/retry behavior."""
    try:
        import huggingface_hub as hub
        from tqdm.auto import tqdm
    except ImportError:
        return
    original = hub.hf_hub_download

    def download(*args, **kwargs):
        filename = str(kwargs.get('filename') or (args[1] if len(args) > 1 else 'mô hình'))
        filename = filename.replace('\\', '/').rsplit('/', 1)[-1]
        emit({'event': 'phase', 'message': 'Đang kiểm tra tệp mô hình: ' + filename})

        class Progress(tqdm):
            def __init__(self, *a, **kw):
                self._last_report = -10.
                kw.pop('name', None)
                kw['disable'] = False
                super().__init__(*a, **kw)
                self.publish(force=True)

            def display(self, *a, **kw):
                pass

            def publish(self, force=False):
                now = time.monotonic()
                if force or now - self._last_report >= 1:
                    emit({'event': 'download', 'filename': filename,
                          'downloaded': self.n, 'total': self.total})
                    self._last_report = now

            def update(self, n=1):
                result = super().update(n)
                self.publish()
                return result

            def close(self):
                if not getattr(self, 'disable', True) and hasattr(self, 'n'):
                    self.publish(force=True)
                super().close()

        kwargs.setdefault('tqdm_class', Progress)
        result = original(*args, **kwargs)
        emit({'event': 'phase', 'message': 'Đang nạp mô hình CPU · tệp đã sẵn sàng: ' + filename})
        return result

    hub.hf_hub_download = download


def main():
    protocol = sys.stdout
    protocol_lock = threading.Lock()

    def emit(value):
        with protocol_lock:
            protocol.write(json.dumps(value, ensure_ascii=True) + '\n')
            protocol.flush()

    try:
        with contextlib.redirect_stdout(sys.stderr):
            emit({'event': 'phase', 'message': 'Đang mở bộ đọc VieNeu'})
            if importlib.metadata.version('vieneu') != '3.8.5':
                raise RuntimeError('Bộ giọng khác phiên bản 3.8.5. Chạy lại CAI-GIONG-MIEN-PHI.cmd.')
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            import numpy as np
            import soundfile as sf
            install_download_progress(emit)
            from vieneu import Vieneu
            # fp32 works on the user's Skylake CPU; int8 requires newer VNNI CPUs.
            emit({'event': 'phase', 'message': 'Đang nạp mô hình VieNeu trên CPU'})
            tts = Vieneu(mode='v3turbo', backend='onnx', device='cpu', precision='fp32',
                         threads=min(4, max(1, (os.cpu_count() or 4) // 2)))
        emit({'event': 'phase', 'message': 'VieNeu đã sẵn sàng · giữ mô hình trong RAM để đổi giọng nhanh'})
        emit({'event': 'ready'})
    except Exception as error:
        emit({'event': 'error', 'fatal': True, 'message': str(error)})
        return 1
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                with contextlib.redirect_stdout(sys.stderr):
                    audio = tts.infer(request['text'], voice=request['voice'], apply_watermark=False)
                    audio = np.asarray(audio, dtype=np.float32)
                    if audio.ndim != 1 or not audio.size or not np.all(np.isfinite(audio)) or np.max(np.abs(audio)) < 1e-5:
                        raise RuntimeError('Câu không có âm thanh hợp lệ. Thử tạo lại riêng câu này.')
                    sf.write(request['target'], audio, tts.sample_rate, subtype='PCM_16')
                emit({'event': 'done'})
            except Exception as error:
                emit({'event': 'error', 'message': str(error)})
    finally:
        with contextlib.redirect_stdout(sys.stderr):
            tts.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())


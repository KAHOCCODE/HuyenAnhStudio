"""Private JSON-lines worker. No API server, GPU packages or per-request network."""
import contextlib
import importlib.metadata
import json
import os
import sys


def main():
    protocol = sys.stdout

    def emit(value):
        protocol.write(json.dumps(value, ensure_ascii=True) + '\n')
        protocol.flush()

    try:
        with contextlib.redirect_stdout(sys.stderr):
            if importlib.metadata.version('vieneu') != '3.8.5':
                raise RuntimeError('Bộ giọng khác phiên bản 3.8.5. Chạy lại CAI-GIONG-MIEN-PHI.cmd.')
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            import numpy as np
            import soundfile as sf
            from vieneu import Vieneu
            # fp32 works on the user's Skylake CPU; int8 requires newer VNNI CPUs.
            tts = Vieneu(mode='v3turbo', backend='onnx', device='cpu', precision='fp32',
                         threads=min(4, max(1, (os.cpu_count() or 4) // 2)))
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


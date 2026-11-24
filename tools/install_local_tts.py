"""Install the optional, isolated CPU speech SDK; no model inference during setup."""
import importlib.metadata
import importlib.resources
import json
import os
import subprocess
import sys

VERSION = '3.8.5'


def install():
    os.environ.update(HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1', GRADIO_ANALYTICS_ENABLED='False')
    pip = [sys.executable, '-m', 'pip']
    subprocess.run(pip + ['install', '--upgrade', 'pip', 'setuptools', 'wheel'], check=True)
    # Default SDK is torch-free. Keep dependencies separate from the GUI / separator.
    subprocess.run(pip + ['install', 'vieneu==' + VERSION, 'onnxruntime==1.32.0',
                         'sea-g2p==0.9.1', 'kaldi-native-fbank==1.22.3', 'librosa==0.11.0'], check=True)
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    # Import the actual backend without constructing a model / downloading weights.
    from vieneu.v3turbo import V3TurboVieNeuTTS
    if 'CPUExecutionProvider' not in onnxruntime.get_available_providers():
        raise RuntimeError('ONNX Runtime chưa có bộ xử lý CPU.')
    if importlib.metadata.version('vieneu') != VERSION:
        raise RuntimeError('Phiên bản VieNeu không khớp.')
    assets = importlib.resources.files('vieneu').joinpath('assets/voices_v3_turbo.json')
    voices = json.loads(assets.read_text(encoding='utf-8')).get('presets', {})
    if len(voices) != 25:
        raise RuntimeError('Danh sách giọng cài đặt không khớp 25 giọng của bản 3.8.5.')
    print('Đã cài VieNeu ' + VERSION + ' CPU với 25 giọng Việt.')
    print('Lần tạo giọng đầu cần mạng tải mô hình. Sau đó dùng lại trên máy.')


if __name__ == '__main__':
    try:
        install()
    except (subprocess.CalledProcessError, ImportError, RuntimeError, OSError) as error:
        print('Cài bộ giọng chưa hoàn tất: ' + str(error), file=sys.stderr)
        sys.exit(1)

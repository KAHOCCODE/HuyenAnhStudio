"""Install the optional CPU separator in the interpreter selected by the launcher."""
import importlib.metadata
import subprocess
import sys


def install():
    python=[sys.executable,'-m','pip']
    subprocess.run(python+['install','--upgrade','pip','setuptools','wheel'],check=True)
    # Install CPU wheels first so the optional environment does not pull CUDA libraries.
    subprocess.run(python+['install','torch==2.8.0','torchvision==0.23.0','torchaudio==2.8.0',
                          '--index-url','https://download.pytorch.org/whl/cpu'],check=True)
    subprocess.run(python+['install','audio-separator[cpu]==0.47.0','librosa==0.11.0'],check=True)
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from audio_separator.separator import Separator
    if 'CPUExecutionProvider' not in onnxruntime.get_available_providers():
        raise RuntimeError('ONNX Runtime chưa có bộ xử lý CPU.')
    print('Đã cài audio-separator '+importlib.metadata.version('audio-separator'))
    print('Bộ tách giọng nhân vật và giảm nhạc đã sẵn sàng.')


if __name__=='__main__':
    try:install()
    except (subprocess.CalledProcessError,ImportError,RuntimeError,OSError) as error:
        print('Cài bộ tách âm thanh chưa hoàn tất: '+str(error),file=sys.stderr)
        sys.exit(1)

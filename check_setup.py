import sys
from studio.core import binary,run
try:
    from PySide6 import __version__ as qt_version
    import edge_tts,numpy
    print('Python:',sys.version.split()[0],'| PySide6:',qt_version)
    filters=run([binary('ffmpeg'),'-hide_banner','-filters'],capture=True)
    for name in ['subtitles','atempo','boxblur','overlay','amix','alimiter']:
        if name not in filters: raise RuntimeError('FFmpeg thieu bo loc '+name)
    encoders=run([binary('ffmpeg'),'-hide_banner','-encoders'],capture=True)
    if 'libx264' not in encoders:raise RuntimeError('FFmpeg thieu libx264.')
    run([binary('ffprobe'),'-version'])
    print('FFmpeg, FFprobe va cac bo loc: OK')
    print('Giọng Edge TTS can mang khi tao. Video duoc xu ly tren may.')
except Exception as e:
    print('LOI:',e)
    print('Dat ffmpeg.exe va ffprobe.exe vao thu muc tools, hoac them FFmpeg vao PATH.')
    sys.exit(1)

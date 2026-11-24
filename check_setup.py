import sys
from studio.core import binary,run
from studio.tts import edge_client
try:
    from PySide6 import __version__ as qt_version
    import edge_tts,numpy
    print('Python:',sys.version.split()[0],'| PySide6:',qt_version,'| Edge TTS:',edge_client().__version__)
    filters=run([binary('ffmpeg'),'-hide_banner','-filters'],capture=True)
    for name in ['subtitles','atempo','asetrate','aresample','boxblur','overlay','amix','alimiter']:
        if name not in filters: raise RuntimeError('FFmpeg thieu bo loc '+name)
    encoders=run([binary('ffmpeg'),'-hide_banner','-encoders'],capture=True)
    if 'libx264' not in encoders:raise RuntimeError('FFmpeg thieu libx264.')
    if 'libmp3lame' not in encoders:print('Can FFmpeg co libmp3lame neu dung giong VieNeu / doi tong.')
    run([binary('ffprobe'),'-version'])
    print('FFmpeg, FFprobe va cac bo loc: OK')
    print('Edge TTS can mang. 25 giong VieNeu CPU tuy chon: chay CAI-GIONG-MIEN-PHI.cmd.')
except Exception as e:
    print('LOI:',e)
    print('Dat ffmpeg.exe va ffprobe.exe vao thu muc tools, hoac them FFmpeg vao PATH.')
    sys.exit(1)

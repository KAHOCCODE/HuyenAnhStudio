import sys, traceback
from pathlib import Path

def main():
    try:
        from studio.ui import main as launch
        launch()
    except Exception:
        text=traceback.format_exc()
        print(text)
        Path('startup-error.log').write_text(text,encoding='utf-8')
        if sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'Không mở được ứng dụng. Xem startup-error.log hoặc chạy lại install.cmd.','Huyền Ảnh Studio',16)
        raise

if __name__=='__main__':main()

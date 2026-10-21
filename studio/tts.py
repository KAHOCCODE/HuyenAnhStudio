"""One cancellable Edge TTS request budget for the entire generation job."""
import asyncio
from pathlib import Path
import random
import re
import threading
import time

MAX_AUDIO_ATTEMPTS=9
MAX_EMPTY_CUES=5


class TTSServiceError(RuntimeError):
    """Stop the job when sending more cues cannot fix the service failure."""


class TTSRequestError(RuntimeError):
    """A cue remains missing; other cues can still be synthesized."""


def edge_client():
    import edge_tts
    version=getattr(edge_tts,'__version__','0')
    try:parts=tuple(int(n) for n in version.split('.')[:3])
    except ValueError:parts=()
    if parts<(7,3,1):
        raise TTSServiceError(f'Edge TTS {version} đã cũ. Đóng app, chạy install.cmd để cập nhật rồi mở lại. MP3 đã có được giữ nguyên.')
    return edge_tts


class TTSCooldown:
    def __init__(self,capacity=1,spacing=.2):
        self.lock=threading.Lock();self.capacity=max(1,min(6,capacity));self.limit=1
        self.active=0;self.generation=0;self.failures=0;self.until=0.;self.next_start=0.
        self.spacing=spacing;self.error=None
        self.empty_cues=0

    def check(self,cancel):
        if cancel.is_set():raise InterruptedError('Đã hủy tạo giọng; MP3 đã có được giữ lại.')
        with self.lock:error=self.error
        if error:raise TTSServiceError(error)

    def acquire(self,cancel):
        # Start with one real cue. After a failure only one request tests recovery.
        while True:
            self.check(cancel)
            with self.lock:
                now=time.monotonic()
                if not self.error and self.active<self.limit and now>=max(self.until,self.next_start):
                    self.active+=1;self.next_start=now+self.spacing
                    return self.generation
            cancel.wait(.05)

    def release(self):
        with self.lock:self.active-=1

    def success(self,generation):
        with self.lock:
            self.active-=1
            self.empty_cues=0
            if generation==self.generation:
                self.failures=0;self.limit=min(self.capacity,self.limit+1)

    def empty_cue_failed(self):
        with self.lock:
            self.empty_cues+=1
            if self.empty_cues>=MAX_EMPTY_CUES:
                self.error=f'Tạm dừng: {MAX_EMPTY_CUES} câu liên tiếp không có âm thanh dù mỗi câu đã thử {MAX_AUDIO_ATTEMPTS} lần, chưa có câu mới thành công xen giữa. Kiểm tra giọng đọc/mạng rồi chạy tiếp; MP3 đã có được giữ nguyên.'
                raise TTSServiceError(self.error)

    def fail(self,generation,reason,fatal=False,retry_after=0):
        with self.lock:
            self.active-=1
            # Completions from the same failed wave cannot multiply the backoff.
            if self.error:raise TTSServiceError(self.error)
            if fatal:
                self.error=f'Dừng tạo voice: {reason} MP3 đã tạo được giữ lại; chạy tiếp sẽ dùng lại chúng.'
                raise TTSServiceError(self.error)
            if generation!=self.generation:
                if retry_after:self.until=max(self.until,time.monotonic()+retry_after)
                return None
            self.generation+=1;self.limit=1;self.failures+=1
            if self.failures>=3:
                self.error=f'Dừng tạo voice sau 3 lần liên tiếp dịch vụ không phục hồi: {reason} Kiểm tra mạng/dịch vụ rồi chạy lại; MP3 đã có được giữ nguyên.'
                raise TTSServiceError(self.error)
            delay=max(5*2**(self.failures-1),retry_after)
            self.until=time.monotonic()+delay
            return delay


def failure_reason(error):
    """Do not log request URLs, authentication query strings or submitted text."""
    import aiohttp
    from edge_tts.exceptions import EdgeTTSException,NoAudioReceived
    status=getattr(error,'status',None)
    if status:
        reason=f'Edge TTS trả HTTP {status}.'
        if status in (401,403):
            return reason+' Dịch vụ từ chối kết nối. Cập nhật bằng install.cmd; nếu vẫn lỗi, kiểm tra ngày giờ Windows và kết nối mạng.',True,0
        if status in (400,404):return reason+' Kiểm tra giọng đọc và cập nhật bằng install.cmd.',True,0
        retry_after=0
        try:retry_after=max(0,float((getattr(error,'headers',None) or {}).get('Retry-After',0)))
        except (TypeError,ValueError):pass
        # Ignore malformed infinite/NaN delays supplied by a failed response.
        import math
        if not math.isfinite(retry_after):retry_after=0
        return reason,False,retry_after
    if isinstance(error,NoAudioReceived):return 'Edge TTS không trả âm thanh (NoAudioReceived).',False,0
    if isinstance(error,TimeoutError):return 'Hết thời gian chờ Edge TTS (TimeoutError).',False,0
    if isinstance(error,aiohttp.ClientError):return f'Lỗi kết nối Edge TTS ({type(error).__name__}).',False,0
    if isinstance(error,EdgeTTSException):return f'Lỗi phản hồi Edge TTS ({type(error).__name__}).',False,0
    # Local file/parameter errors should not put every other cue into cooldown.
    raise error


context=threading.local()


async def wait_retry(delay,cancel,gate):
    end=time.monotonic()+delay
    while True:
        gate.check(cancel)
        remaining=end-time.monotonic()
        if remaining<=0:return
        await asyncio.sleep(min(.1,remaining))


async def save_attempt(client,text,voice,rate,path,cancel,gate):
    from edge_tts.exceptions import NoAudioReceived
    task=asyncio.create_task(client.Communicate(text,voice,rate=f'{rate:+d}%').save(str(path)))
    complete=False
    try:
        began=time.monotonic()
        while not task.done():
            gate.check(cancel)
            if time.monotonic()-began>90:raise TimeoutError()
            await asyncio.sleep(.05)
        await task
        gate.check(cancel)
        if not path.is_file() or path.stat().st_size==0:raise NoAudioReceived('Empty audio file')
        complete=True
    finally:
        if not task.done():task.cancel()
        try:await task
        except (Exception,asyncio.CancelledError):pass
        if not complete:path.unlink(missing_ok=True)


async def fetch_voice(text,voice,rate,path,cancel):
    from edge_tts.exceptions import NoAudioReceived
    client=edge_client();gate=getattr(context,'gate',None) or TTSCooldown()
    # Clean only characters the speech protocol cannot read; keep the SRT unchanged.
    text=' '.join(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',text).split())
    if not any(c.isalnum() for c in text):raise TTSRequestError('Câu không có chữ hoặc số để đọc; giữ nguyên phụ đề để rà soát.')
    path=Path(path);service_failures=0
    reason='Không nhận được âm thanh.'
    for attempt in range(MAX_AUDIO_ATTEMPTS):
        generation=gate.acquire(cancel)
        try:
            await save_attempt(client,text,voice,rate,path,cancel,gate)
        except (InterruptedError,TTSServiceError,asyncio.CancelledError):
            gate.release();raise
        except NoAudioReceived:
            # An empty response for one cue is not evidence that every cue failed.
            gate.release()
            if attempt+1==MAX_AUDIO_ATTEMPTS:
                gate.empty_cue_failed()
                raise TTSRequestError(f'Câu vẫn không có âm thanh (NoAudioReceived) sau {MAX_AUDIO_ATTEMPTS} lần thử. Các câu khác tiếp tục; có thể thử lại câu thiếu.')
            delay=1.5*(attempt+1)+random.random()
            report=getattr(context,'report',None)
            if report:report(f'NoAudioReceived · thử lại riêng câu này sau {delay:.1f}s ({attempt+2}/{MAX_AUDIO_ATTEMPTS}); các câu khác tiếp tục.')
            await wait_retry(delay,cancel,gate)
        except Exception as error:
            try:reason,fatal,retry_after=failure_reason(error)
            except Exception:
                gate.release();raise
            delay=gate.fail(generation,reason,fatal,retry_after)
            service_failures+=1
            if service_failures>=3 or attempt+1==MAX_AUDIO_ATTEMPTS:
                raise TTSRequestError(f'Không tạo được câu: {reason}')
            report=getattr(context,'report',None)
            if report and delay is not None:
                report(f'{reason} Chờ chung {delay:g}s, sau đó thử phục hồi dịch vụ bằng 1 câu ({service_failures+1}/3).')
        else:
            gate.success(generation);return

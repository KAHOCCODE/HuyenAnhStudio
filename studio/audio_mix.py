"""Reuse PCM blocks and update a long review WAV with a recoverable write journal."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import uuid
import wave

RATE = 24000
BLOCK = 30 * RATE


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as target:
        json.dump(value, target, ensure_ascii=False)
        target.flush()
        os.fsync(target.fileno())
    temp.replace(path)


def stamp(path):
    stat = Path(path).stat()
    return [stat.st_size, stat.st_mtime_ns]


def header(frames):
    return struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + frames * 2,
                       b'WAVE', b'fmt ', 16, 1, 1, RATE, RATE * 2, 2, 16,
                       b'data', frames * 2)


def canonical_track(path, frames):
    try:
        with Path(path).open('rb') as source:
            return source.read(44) == header(frames) and source.seek(0, 2) == 44 + frames * 2
    except OSError:
        return False


def plan(entries, total, cancel, file_stats=None):
    buckets = [[] for _ in range(math.ceil(total / BLOCK))]
    stats = {}
    for entry in entries:
        if cancel.is_set():
            raise InterruptedError('Đã hủy đối chiếu âm thanh.')
        start, end = round(entry['start'] * RATE), round(entry['end'] * RATE)
        path = str(entry['path'])
        if path not in stats:
            stats[path] = file_stats[path] if file_stats is not None and path in file_stats else stamp(path)
        for index in range(max(0, start // BLOCK), min(len(buckets), math.ceil(end / BLOCK))):
            buckets[index].append((entry, start, end, stats[path]))
    keys, shifted = [], []
    for index, rows in enumerate(buckets):
        pos = index * BLOCK
        count = min(BLOCK, total - pos)
        rows.sort(key=lambda r: (r[1], str(r[0]['path']), r[2]))
        fingerprint = [count, [(str(r['path']), a - pos, b - pos, stat) for r, a, b, stat in rows]]
        keys.append(hashlib.sha256(json.dumps(fingerprint).encode()).hexdigest()[:32])
        shifted.append([dict(r, start=(a - pos) / RATE, end=(b - pos) / RATE) for r, a, b, _ in rows])
    return keys, shifted


def recover(cache):
    """Only the mixer recovers writes; readers refuse an unfinished transaction."""
    cache = Path(cache)
    journal = cache / 'mix-transaction'
    transaction = read_json(journal / 'journal.json')
    if not transaction:
        if (journal / 'journal.json').is_file():
            raise ValueError('Không đọc được nhật ký cập nhật voice. Bản sao phục hồi được giữ nguyên.')
        if journal.exists():
            shutil.rmtree(journal)  # Backups were not published; no writes started.
        return
    state = read_json(cache / 'mix-state.json')
    if state.get('transaction') != transaction['id']:
        track = Path(transaction['track'])
        with track.open('r+b') as target:
            for item in transaction['backups']:
                target.seek(item['offset'])
                with (journal / item['file']).open('rb') as source:
                    shutil.copyfileobj(source, target, 1024 * 1024)
            target.seek(0)
            target.write(bytes.fromhex(transaction['header']))
            target.truncate(transaction['size'])
            target.flush()
            os.fsync(target.fileno())
        old = transaction.get('state')
        if old:
            # Restoring the bytes also changes mtime. Keep the old revision usable.
            old['stat'] = stamp(track)
            write_json(cache / 'mix-state.json', old)
        else:
            (cache / 'mix-state.json').unlink(missing_ok=True)
    shutil.rmtree(journal)


def ready(cache, track, token=None):
    cache, track = Path(cache), Path(track)
    if (cache / 'mix-transaction' / 'journal.json').is_file():
        return False
    state = read_json(cache / 'mix-state.json')
    if state.get('track') != str(track):
        return token is None  # Legacy WAVs remain usable until their first update.
    try:
        return token == state.get('token') and stamp(track) == state.get('stat')
    except OSError:
        return False


def update_mix(entries, duration, out, cache, cancel, render, progress=lambda n: None, previous=None, file_stats=None):
    cache, out = Path(cache), Path(out)
    cache.mkdir(parents=True, exist_ok=True)
    recover(cache)
    if cancel.is_set():
        raise InterruptedError('Đã hủy cập nhật voice.')
    total = round(duration * RATE)
    if total * 2 > 4_200_000_000:
        raise ValueError('Voice vượt giới hạn WAV 4 GB.')
    keys, shifted = plan(entries, total, cancel, file_stats)
    blocks = cache / 'mix-blocks'
    blocks.mkdir(exist_ok=True)
    state_path = cache / 'mix-state.json'
    old = read_json(state_path)
    valid = False
    if old.get('track') and isinstance(old.get('frames'), int):
        try:
            valid = stamp(old['track']) == old.get('stat') and canonical_track(old['track'], old['frames'])
        except OSError:
            pass
    if not valid and not state_path.is_file() and previous and previous.get('track'):
        frames = round(previous['duration'] * RATE)
        if canonical_track(previous['track'], frames):
            try:
                old_keys, _ = plan(previous['rows'], frames, cancel, file_stats)
                old = dict(track=str(previous['track']), frames=frames, blocks=old_keys,
                           stat=stamp(previous['track']))
                valid = True
            except OSError:
                pass
    old_keys = old.get('blocks', []) if valid else []
    changed = [i for i, key in enumerate(keys) if i >= len(old_keys) or old_keys[i] != key]
    token = hashlib.sha256(json.dumps([total, keys]).encode()).hexdigest()
    stats = dict(total_blocks=len(keys), changed_blocks=len(changed), reused_blocks=len(keys)-len(changed),
                 rendered_blocks=0, written_frames=0)
    if valid and not changed and old['frames'] == total:
        state = dict(schema=1, track=old['track'], frames=total, blocks=keys, token=token, stat=stamp(old['track']))
        if old.get('token') != token:
            write_json(state_path, state)
        progress(100)
        return dict(stats, track=old['track'], token=token)

    # Render only new blocks. Untouched blocks need no cache-file or PCM reads.
    for done, index in enumerate(changed):
        if cancel.is_set():
            raise InterruptedError('Đã hủy; các đoạn âm thanh đã có được giữ.')
        count = min(BLOCK, total-index*BLOCK)
        block = blocks / (keys[index] + '.wav')
        if not canonical_track(block, count):
            render(shifted[index], count/RATE, block, cancel)
            stats['rendered_blocks'] += 1
        progress(60*(done+1)/max(1,len(changed)))

    # A small edit writes only its affected regions. Large timing shifts use the
    # atomic full writer; keeping a rollback copy would cost more than that pass.
    bytes_changed = sum(min(BLOCK, total-i*BLOCK)*2 for i in changed)
    patch = valid and bytes_changed + max(0, old['frames']-total)*2 < max(total, old['frames'])*1.0
    track = Path(old['track']) if patch else out
    state = dict(schema=1, track=str(track), frames=total, blocks=keys, token=token)
    if patch:
        journal = cache / 'mix-transaction'
        journal.mkdir()
        transaction = dict(id=uuid.uuid4().hex, track=str(track), size=track.stat().st_size,
                           state=read_json(state_path), backups=[])
        try:
            with track.open('rb') as source:
                transaction['header'] = source.read(44).hex()
                ranges = [(i*BLOCK*2, min(BLOCK,total-i*BLOCK)*2) for i in changed]
                if total < old['frames']:
                    ranges.append((total*2, (old['frames']-total)*2))
                for index, (pos, count) in enumerate(ranges):
                    if cancel.is_set():
                        raise InterruptedError('Đã hủy cập nhật voice.')
                    count = min(count, max(0, old['frames']*2-pos))
                    if not count:
                        continue
                    name = f'{index}.pcm'
                    source.seek(44+pos)
                    with (journal/name).open('wb') as backup:
                        remaining = count
                        while remaining:
                            data = source.read(min(1024*1024,remaining))
                            if not data:
                                raise OSError('Tệp voice cũ bị thiếu dữ liệu.')
                            backup.write(data)
                            remaining -= len(data)
                        backup.flush()
                        os.fsync(backup.fileno())
                    transaction['backups'].append(dict(offset=44+pos,file=name))
            write_json(journal/'journal.json',transaction)
            with track.open('r+b') as target:
                for done, index in enumerate(changed):
                    if cancel.is_set():
                        raise InterruptedError('Đã hủy cập nhật voice.')
                    target.seek(44+index*BLOCK*2)
                    with wave.open(str(blocks/(keys[index]+'.wav')),'rb') as source:
                        target.write(source.readframes(BLOCK))
                    stats['written_frames'] += min(BLOCK,total-index*BLOCK)
                    progress(60+40*(done+1)/max(1,len(changed)))
                if cancel.is_set():
                    raise InterruptedError('Đã hủy cập nhật voice.')
                target.seek(0)
                target.write(header(total))
                target.truncate(44+total*2)
                target.flush()
                os.fsync(target.fileno())
            state.update(stat=stamp(track),transaction=transaction['id'])
            write_json(state_path,state)
        except BaseException:
            recover(cache)
            raise
        shutil.rmtree(journal)
    else:
        temp = out.with_suffix('.partial.wav')
        try:
            with wave.open(str(temp),'wb') as target:
                target.setparams((1,2,RATE,0,'NONE','not compressed'))
                for index, key in enumerate(keys):
                    if cancel.is_set():
                        raise InterruptedError('Đã hủy ghép voice; bản trước được giữ.')
                    count = min(BLOCK,total-index*BLOCK)
                    block = blocks/(key+'.wav')
                    if not canonical_track(block,count):
                        render(shifted[index],count/RATE,block,cancel)
                        stats['rendered_blocks'] += 1
                    with wave.open(str(block),'rb') as source:
                        target.writeframesraw(source.readframes(BLOCK))
                    stats['written_frames'] += count
                    progress(60+40*(index+1)/max(1,len(keys)))
            if cancel.is_set():
                raise InterruptedError('Đã hủy ghép voice; bản trước được giữ.')
            temp.replace(out)
            state['stat'] = stamp(out)
            write_json(state_path,state)
        finally:
            temp.unlink(missing_ok=True)
    return dict(stats, track=str(track), token=token)

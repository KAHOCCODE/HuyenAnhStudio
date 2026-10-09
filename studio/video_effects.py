"""Validated, non-destructive picture transforms for FFmpeg exports."""
import math
import re

DEFAULTS = dict(enabled=False, size='source', width=1920, height=1080,
                layout='crop', zoom=1.0, x=50.0, y=50.0, flip=False,
                inset=8.0, blur=20.0, background='#171717', border='#80D8FF',
                saturation=1.0, contrast=1.0, brightness=0.0, temperature=0.0,
                effect='none', opacity=0.08)
SIZES = {'landscape': (1920, 1080), 'portrait': (1080, 1920),
         'square': (1080, 1080), 'classic': (1440, 1080)}


def settings(value):
    if not isinstance(value, dict):
        raise ValueError('Thiết lập khung hình phải là một đối tượng.')
    if set(value) - set(DEFAULTS):
        raise ValueError('Thiết lập khung hình chứa mục không được hỗ trợ.')
    v = dict(DEFAULTS, **value)
    for key in ('enabled', 'flip'):
        if not isinstance(v[key], bool):
            raise ValueError('Trạng thái khung hình không hợp lệ.')
    for key, choices in [('size', ('source', 'custom', *SIZES)),
                         ('layout', ('crop', 'fit', 'blur', 'frame')),
                         ('effect', ('none', 'haze', 'dust', 'light'))]:
        if v[key] not in choices:
            raise ValueError('Lựa chọn khung hình không hợp lệ: ' + key)
    for key, low, high in [('width', 64, 7680), ('height', 64, 7680),
                           ('zoom', 1, 3), ('x', 0, 100), ('y', 0, 100),
                           ('inset', 0, 30), ('blur', 1, 60),
                           ('saturation', 0, 2), ('contrast', .5, 1.5),
                           ('brightness', -.2, .2), ('temperature', -1, 1),
                           ('opacity', 0, .3)]:
        n = v[key]
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not low <= n <= high:
            raise ValueError(f'Thiết lập {key} phải trong khoảng {low}–{high}.')
    for key in ('width', 'height'):
        if v[key] != int(v[key]) or int(v[key]) % 2:
            raise ValueError('Chiều rộng và chiều cao phải là số nguyên chẵn.')
    for key in ('background', 'border'):
        if not isinstance(v[key], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', v[key]):
            raise ValueError('Màu khung hình phải có dạng #RRGGBB.')
    return v


def output_size(p):
    v = settings(p.video_effects)
    if not v['enabled'] or v['size'] == 'source':
        return math.ceil(p.width / 2) * 2, math.ceil(p.height / 2) * 2
    if v['size'] == 'custom':
        return int(v['width']), int(v['height'])
    return SIZES[v['size']]


def picture_filter(p, source, target='[picture]'):
    """Flip is applied by the caller before source-space replacement text."""
    v = settings(p.video_effects)
    w, h = output_size(p)
    z, x, y = v['zoom'], v['x'] / 100, v['y'] / 100
    parts = []
    chain = []
    if z != 1:
        chain.append(f"crop=w='max(2,trunc(iw/{z}/2)*2)':h='max(2,trunc(ih/{z}/2)*2)':x='(iw-ow)*{x}':y='(ih-oh)*{y}'")
    t = v['temperature'] * .12
    chain += [f"eq=saturation={v['saturation']}:contrast={v['contrast']}:brightness={v['brightness']}",
              f'colorbalance=rs={t}:bs={-t}:rm={t/2}:bm={-t/2}', 'setsar=1']
    parts.append(source + ','.join(chain) + '[graded]')
    layout = v['layout']
    if layout == 'crop':
        parts.append(f"[graded]scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={w}:{h}:(iw-ow)*{x}:(ih-oh)*{y}[canvas]")
    elif layout == 'fit':
        parts.append(f"[graded]scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)*{x}:(oh-ih)*{y}:color={v['background']}[canvas]")
    else:
        fw = max(2, int(w * (1 - 2*v['inset']/100)) // 2 * 2)
        fh = max(2, int(h * (1 - 2*v['inset']/100)) // 2 * 2)
        parts.append('[graded]split[bgsrc][fgsrc]')
        parts.append(f"[bgsrc]scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={w}:{h},gblur=sigma={v['blur']},eq=brightness=-0.12[bg]")
        parts.append(f'[fgsrc]scale={fw}:{fh}:force_original_aspect_ratio=decrease:force_divisible_by=2[fg]')
        parts.append(f'[bg][fg]overlay=x=(W-w)*{x}:y=(H-h)*{y}[composed]')
        if layout == 'frame':
            # Animated border around the output canvas, scaled with resolution.
            thickness = max(2, round(min(w,h)/180))
            parts.append(f"[composed]drawbox=x=0:y=0:w=iw:h=ih:t={thickness}:color={v['border']}@0.65,drawbox=x=0:y=0:w=iw:h=ih:t={thickness}:color=white@0.3:enable='lt(mod(t,4),1)'[canvas]")
        else:
            parts.append('[composed]null[canvas]')
    effect, a = v['effect'], v['opacity']
    if effect == 'haze':
        parts.append(f'[canvas]drawbox=x=0:y=0:w=iw:h=ih:color=white@{a}:t=fill{target}')
    elif effect in ('dust', 'light') and a:
        # Tiny procedural textures avoid external assets, paths and extra inputs.
        size = 128
        if effect == 'dust':
            expr = "if(gt(mod(X*13+Y*7,113),111)*gt(mod(Y*17+X,97),95),255,0)"
        else:
            expr = '255*max(0,1-hypot(X-64,Y-64)/64)'
        parts.append('[canvas]split[clean][texture_source]')
        parts.append(f"[texture_source]scale={size}:{size},geq=lum='{expr}':cb=128:cr=128,format=yuv420p,scroll=horizontal=0.013:vertical=0.007,scale={w}:{h}[texture]")
        parts.append(f"[clean][texture]blend=c0_expr='min(255,A+B*{a})':c1_expr=A:c2_expr=A:shortest=1{target}")
    else:
        parts.append('[canvas]null' + target)
    # Scaling to even dimensions may introduce a non-square sample aspect ratio.
    parts = [part.replace(target, '[effect_output]') for part in parts]
    parts.append('[effect_output]setsar=1' + target)
    return ';'.join(parts)

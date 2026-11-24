"""Voice IDs are stable project data; local presets come from vieneu 3.8.5."""
import math

VIENEU_VERSION = "3.8.5"
VIENEU_PREFIX = "vieneu:turbo:"
LOCAL_CACHE_VERSION = "vieneu-3.8.5-turbo-fp32-v1"
EDGE_VOICES = {"Nam Minh · Nam · Edge": "vi-VN-NamMinhNeural",
               "Hoài My · Nữ · Edge": "vi-VN-HoaiMyNeural"}
# Preset metadata only. The model and embeddings are downloaded by the upstream SDK.
# https://github.com/pnnbao97/VieNeu-TTS (Apache-2.0), SDK 3.8.5.
LOCAL_PRESETS = [
    [
        "Adam bựa",
        "Nam · Bắc · Phong cách tự nhiên"
    ],
    [
        "Trúc Ly",
        "Nữ · Bắc · Phong cách tự nhiên"
    ],
    [
        "Thiện Minh",
        "Nam · Bắc · Phong cách kể chuyện"
    ],
    [
        "Mai Anh",
        "Nữ · Bắc · Phong cách tin tức"
    ],
    [
        "Hải Đăng",
        "Nam · Bắc · Phong cách tự nhiên"
    ],
    [
        "Thùy Dung",
        "Nữ · Nam · Phong cách tin tức"
    ],
    [
        "Thiền Tâm Đức",
        "Nam · Bắc · Phong cách kể chuyện"
    ],
    [
        "Ngọc Huyền",
        "Nữ · Bắc · Giọng đọc tự nhiên"
    ],
    [
        "Quang Sơn",
        "Nam · Trung · Phong cách tự nhiên"
    ],
    [
        "Ngọc Trân",
        "Nữ · Trung · Phong cách tự nhiên"
    ],
    [
        "Minh Đức",
        "Nam · Bắc · Phong cách tin tức"
    ],
    [
        "Phạm Tuyên",
        "Nam · Bắc · Phong cách tự nhiên"
    ],
    [
        "Thái Sơn",
        "Nam · Nam · Phong cách kể chuyện"
    ],
    [
        "Xuân Vĩnh",
        "Nam · Bắc · Phong cách tự nhiên"
    ],
    [
        "Thanh Bình",
        "Nam · Bắc · Phong cách kể chuyện"
    ],
    [
        "Ngọc Linh",
        "Nữ · Bắc · Phong cách kể chuyện"
    ],
    [
        "Đoan Trang",
        "Nữ · Bắc · Phong cách tự nhiên"
    ],
    [
        "Thục Đoan",
        "Nữ · Nam · Phong cách kể chuyện"
    ],
    [
        "Minh Triết",
        "Nam · Nam · Phong cách tin tức"
    ],
    [
        "Mỹ Duyên",
        "Nữ · Nam · Phong cách đọc truyện"
    ],
    [
        "Quỳnh Anh",
        "Nữ · Bắc · Phong cách đọc truyện"
    ],
    [
        "Đức Trí",
        "Nam · Nam · Phong cách đọc truyện"
    ],
    [
        "Kim Thanh",
        "Nữ · Nam · Phong cách đọc truyện"
    ],
    [
        "Adam",
        "Nam · Nam · Giọng đọc tự nhiên"
    ],
    [
        "Quốc Tuấn",
        "Nam · Bắc · Phong cách tự nhiên"
    ]
]
VOICES = dict(EDGE_VOICES)
VOICES.update({f"{name} · VieNeu · {description}": VIENEU_PREFIX + name
               for name, description in LOCAL_PRESETS})
PITCH_PRESETS = [("Tự nhiên", 0.0), ("Cao nhẹ · dễ thương", 2.5),
                 ("Cao sáng", 1.5), ("Trầm ấm", -2.0)]


def is_local_voice(voice):
    return isinstance(voice, str) and voice.startswith("vieneu:")


def local_voice_name(voice):
    if voice not in VOICES.values() or not voice.startswith(VIENEU_PREFIX):
        raise ValueError("Giọng VieNeu không hợp lệ. Chọn lại giọng trong danh sách.")
    return voice[len(VIENEU_PREFIX):]


def validate_pitch(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -6 <= value <= 6:
        raise ValueError("Tông giọng phải từ -6 đến +6 bán âm.")
    return float(value)

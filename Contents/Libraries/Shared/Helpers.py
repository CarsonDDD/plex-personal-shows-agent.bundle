import os, re
from datetime import datetime

def clear_posters(metadata):
    metadata.posters._items.clear()


FILENAME_RE = re.compile(r'^[Ss](\d+)[Ee](\d+)\s*-\s*(.+)$')  # "S1E20 - Spinoza's Ethics"

def episode_fields_from_filename(path):
    # "S1E20 - Spinoza's Ethics" Parses file to get info
    # Expand later to read the mp4 for embeded data
    s = os.path.splitext(os.path.basename(path))[0]
    m = FILENAME_RE.match(s)
    if m:
        ss, ee, title = m.groups()
        title = title.strip()
        return int(ss), int(ee), title if title else s

    return None, None, s

def parse_available_at(meta):
    # YYYY-MM-DD and any less accurate version of that
    if not meta or 'available_at' not in meta:
        return None
    val = str(meta.get('available_at')).strip()
    if not val:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
        try:
            dt = datetime.strptime(val, fmt)
            return dt.date()
        except ValueError:
            continue
    Log.Warn("available_at isnt formatted: %r" % val)
    return None

def episode_poster_image_path(video_path):
    base, _ = os.path.splitext(video_path)
    exts = ('.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP')
    for ext in exts:
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None
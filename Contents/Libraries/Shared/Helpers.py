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
    """
    Accept either 'originally_available_at' (preferred) or legacy 'available_at'.
    Supports YYYY[-MM[-DD]].
    """
    if not meta:
        return None
    key = 'originally_available_at' if 'originally_available_at' in meta else (
          'available_at' if 'available_at' in meta else None)
    if not key:
        return None
    val = str(meta.get(key)).strip()
    if not val:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
        try:
            dt = datetime.strptime(val, fmt)
            return dt.date()
        except ValueError:
            continue
    Log.Warn("%s isnt formatted: %r" % (key, val))
    return None

def episode_poster_image_path(video_path):
    base, _ = os.path.splitext(video_path)
    exts = ('.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP')
    for ext in exts:
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None



def load_json_if_exists(path):
    try:
        if path and os.path.exists(path):
            return json.loads(Core.storage.load(path))
    except Exception as ex:
        Log.Warn('Failed to parse JSON at %s: %s' % (path, ex))
    return None


def find_episode_meta_path(ep_path):
    base, _ = os.path.splitext(ep_path)
    for suf in ('.meta.json', '.json', '.meta'):  # supports your .meta files
        p = base + suf
        if os.path.exists(p):
            return p
    return None

def load_episode_meta(ep_path):
    p = find_episode_meta_path(ep_path)
    if not p:
        return None
    try:
        return json.loads(Core.storage.load(p))
    except Exception as ex:
        Log.Warn('Failed to parse episode JSON at %s: %s' % (p, ex))
        return None


def apply_roles(md_roles, meta):
    try:
        md_roles.clear()
    except Exception:
        pass

    def add_entries(entries, default_role):
        for a in entries or []:
            r = md_roles.new()
            r.name  = a.get('name', '')
            r.role  = a.get('role', default_role) or default_role
            r.photo = a.get('photo', '')

    add_entries(meta.get('actors'),  'Actor')
    add_entries(meta.get('writers'), 'Writer')



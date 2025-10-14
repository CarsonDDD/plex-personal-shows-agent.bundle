# -*- coding: utf-8 -*-
import os, re, json, sys, unicodedata
from datetime import datetime


def get_logger():
    try:
        return Log  # First call will cause an error from the logger starting up after the plugin
    except NameError:
        class _Null(object):
            def Info(self, *a, **k): pass
            def Warn(self, *a, **k): pass
            def Error(self, *a, **k): pass
        return _Null()

def load_bytes(path):
    """
    Prefer Plex Core.storage.load; fall back to direct file read.
    """
    logger = get_logger()
    try:
        core = globals().get('Core', None)
        if core:
            return core.storage.load(path)
    except Exception as ex:
        logger.Warn('Core.storage.load failed for %s: %s' % (path, ex))
    with open(path, 'rb') as f:
        return f.read()


def clear_posters(metadata):
    # Try public clear(); fall back to private structure
    try:
        metadata.posters.clear()
    except Exception:
        try:
            metadata.posters._items.clear()
        except Exception:
            pass


FILENAME_RE = re.compile(r'^[Ss](\d+)[Ee](\d+)\s*-\s*(.+)$')  # "S1E20 - Title"

def episode_fields_from_filename(path):
    """
    Parse: S<season>E<episode> - <Title>.<ext>
    Returns (int season, int episode, str title_or_basename)
    """
    s = os.path.splitext(os.path.basename(path))[0]
    m = FILENAME_RE.match(s)
    if m:
        ss, ee, title = m.groups()
        title = title.strip()
        return int(ss), int(ee), title if title else s
    return None, None, s


def parse_available_at(meta):
    """
    Accept 'originally_available_at' (preferred) or legacy 'available_at'.
    Supports YYYY, YYYY-MM, YYYY-MM-DD. Returns datetime.date or None.
    """
    logger = get_logger()
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
    logger.Warn("%s isn't formatted: %r" % (key, val))
    return None


# Precompiled, Unicode-aware regexes
_UCLASS_RE = re.compile(r'[^0-9a-z\s]+', re.UNICODE)
_SPACE_RE  = re.compile(r'\s+', re.UNICODE)

if sys.version_info[0] == 2:
    text_type  = unicode   # noqa: F821 (Py2 only)
    bytes_type = str
else:
    text_type  = str
    bytes_type = (bytes, bytearray)

def to_text(s):
    """Return unicode text (works in Py2/3)."""
    if isinstance(s, text_type):
        return s
    if isinstance(s, bytes_type):
        try:
            return s.decode('utf-8', 'strict')
        except Exception:
            return s.decode('latin-1', 'ignore')
    return text_type(s)

def norm_stem(s):
    """
    Normalize stems so fullwidth punctuation (e.g., '？') matches ASCII ('?'):
    unicode->NFKC->lower, strip punctuation (keep letters/digits/spaces), collapse spaces.
    """
    s = to_text(s)
    s = unicodedata.normalize('NFKC', s).lower()
    s = _UCLASS_RE.sub(' ', s)
    s = _SPACE_RE.sub(' ', s).strip()
    return s

def find_sidecar_relaxed(video_path, exts):
    """
    Find a sidecar whose normalized stem matches the video stem,
    ignoring width/punctuation differences (e.g., '?' vs '？').
    """
    d = os.path.dirname(video_path)
    v_stem = os.path.splitext(os.path.basename(video_path))[0]
    v_norm = norm_stem(v_stem)

    # 1) exact fast path
    for ext in exts:
        p = os.path.join(d, v_stem + ext)
        if os.path.exists(p):
            return p

    # 2) relaxed scan
    try:
        names = os.listdir(d)
    except Exception:
        return None

    targets = [n for n in names for ext in exts if n.lower().endswith(ext.lower())]
    for n in targets:
        stem = os.path.splitext(n)[0]
        if norm_stem(stem) == v_norm:
            return os.path.join(d, n)
    return None


def episode_poster_image_path(video_path):
    exts = ('.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP')
    return find_sidecar_relaxed(video_path, exts)

def find_episode_meta_path(ep_path):
    exts = ('.meta.json', '.json', '.meta', '.META.JSON', '.JSON', '.META')
    return find_sidecar_relaxed(ep_path, exts)


def load_json_if_exists(path):
    logger = get_logger()
    try:
        if path and os.path.exists(path):
            return json.loads(load_bytes(path))
    except Exception as ex:
        logger.Warn('Failed to parse JSON at %s: %s' % (path, ex))
    return None

def load_episode_meta(ep_path):
    logger = get_logger()
    p = find_episode_meta_path(ep_path)
    if not p:
        return None
    try:
        return json.loads(load_bytes(p))
    except Exception as ex:
        logger.Warn('Failed to parse episode JSON at %s: %s' % (p, ex))
        return None

def apply_roles(md_roles, meta):
    """
    SHOW-LEVEL ONLY: map actors/writers into roles container.
    """
    if not meta:
        return
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

def apply_episode_credits(ep_md, meta):
    """
    EPISODE-LEVEL: writers, (optional) directors, and actors -> guest_stars.
    """
    if not meta:
        return

    # Writers
    if 'writers' in meta:
        try: ep_md.writers.clear()
        except Exception: pass
        for w in meta.get('writers') or []:
            obj = ep_md.writers.new()
            obj.name = w.get('name', '')

    # Directors
    if 'directors' in meta:
        try: ep_md.directors.clear()
        except Exception: pass
        for d in meta.get('directors') or []:
            obj = ep_md.directors.new()
            obj.name = d.get('name', '')

    # Actors are guest_stars
    if 'actors' in meta:
        try: ep_md.guest_stars.clear()
        except Exception: pass
        for a in meta.get('actors') or []:
            obj = ep_md.guest_stars.new()
            obj.name = a.get('name', '')
            obj.role = a.get('role', '')

def coerce_rating(v):
    try:
        f = float(v)
        return max(0.0, min(10.0, f))  # Plex uses 0–10, for their 5 star system....
    except Exception:
        return None

# -*- coding: utf-8 -*-
import os, json
import urllib
import hashlib
from Helpers import (
    clear_posters,
    parse_available_at,
    episode_fields_from_filename,
    episode_poster_image_path,
    load_json_if_exists,
    load_episode_meta,
    coerce_rating,
    apply_episode_credits,
    apply_roles,
)

class PersonalShowsAgent(Agent.TV_Shows):
    name = 'Personal Shows'
    languages = [Locale.Language.NoLanguage]
    primary_provider = True
    persist_stored_files = False

    def search(self, results, media, lang):
        results.Append(MetadataSearchResult(id = media.filename, score = 100, name = media.filename, lang = Locale.Language.NoLanguage))

    def update_season(self, season_id, summary):
        ip_address = Prefs['ip_address']
        port = Prefs['port']
        username = Prefs['username']
        password = Prefs['password']

        if not ip_address or not port or not username or not password:
            Log.Info('Missing Preferences, Skipping Summary Update')
            return

        host = '%s:%s' % (ip_address, port)
        HTTP.SetPassword(host, username, password)

        # get section id
        metadata_json = json.loads(HTTP.Request(url=('http://%s/library/metadata/%s' % (host, season_id)), immediate=True, headers={'Accept': 'application/json'}).content)
        section_id = metadata_json['MediaContainer']['librarySectionID']

        # update summary
        request = HTTP.Request(url=('http://%s/library/sections/%s/all?summary.value=%s&type=3&id=%s' % (host, section_id, urllib.quote(summary), season_id)), method='PUT')
        request.load()

    def update_poster(self, metadata, link, base_path=None):
        try:
            Log.Info('Updating poster link: %s base: %s' % (link, base_path))
            if not link or not metadata:
                Log.Info('Skipping poster update. Link or metadata missing')
                return

            if link.startswith('http://') or link.startswith('https://'):
                metadata.posters[link] = Proxy.Preview(None)
                return

            if not link.startswith('/') and not base_path:
                Log.Info('Skipping poster update, link is relative and base path is missing')
                return

            if link.startswith('/'):
                poster_path = link
            else:
                poster_path = os.path.normpath(os.path.join(base_path, link))
                if not os.path.exists(poster_path):
                    poster_path = os.path.normpath(os.path.join(base_path, '../', link))

            Log.Info('Poster path %s' % poster_path)
            data = Core.storage.load(poster_path)
            media_hash = hashlib.md5(data).hexdigest()
            metadata.posters[media_hash] = Proxy.Media(data)
        except Exception as e:
            Log.Error('Error updating poster %s' % getattr(e, 'message', e))

    def update(self, metadata, media, lang):
        Log.Info('Updating Metadata UPDATED VERSION 2025!!!! update()')

        # ---- locate show root and meta.json
        first_episode_path = None

        # assumed S1E1 exists
        try:
            first_episode_path = media.seasons['1'].episodes['1'].items[0].parts[0].file
        except Exception:
            pass

        # Fallback: find the first playable file anywhere
        if not first_episode_path:
            for s in media.seasons.values():
                for e in s.episodes.values():
                    if e.items and e.items[0].parts:
                        first_episode_path = e.items[0].parts[0].file
                        break
                if first_episode_path:
                    break

        if not first_episode_path:
            Log.Warn('No playable media parts found; skipping update()')
            return

        season_path = os.path.normpath(os.path.join(first_episode_path, '..'))
        show_path   = os.path.normpath(os.path.join(season_path, '..'))
        meta_path   = os.path.join(show_path, 'meta.json')
        if not os.path.exists(meta_path):
            show_path = os.path.normpath(os.path.join(show_path, '..'))
            meta_path = os.path.join(show_path, 'meta.json')

        meta_json = None
        if meta_path and os.path.exists(meta_path):
            try:
                meta_json = json.loads(Core.storage.load(meta_path))
            except Exception as ex:
                Log.Error('meta.json parse error at %s: %s' % (meta_path, ex))

        # ---- show-level fields
        if show_path:
            metadata.title = os.path.basename(show_path)

        if meta_json:
            Log.Info('Loaded meta.json: %s' % meta_json)

            metadata.summary = meta_json.get('summary') or meta_json.get('description', '')
            metadata.studio = meta_json.get('studio') or meta_json.get('publisher', '')

            show_date = parse_available_at(meta_json)
            if show_date:
                metadata.originally_available_at = show_date
                Log.Info('Set show originally_available_at = %s' % show_date)

            metadata.collections.clear()
            for collections in meta_json.get('collections', []):
                metadata.collections.add(collections)

            metadata.genres.clear()
            for g in (meta_json.get('genres') or meta_json.get('tags', [])):
                metadata.genres.add(g)

            # PEOPLE (show-level): use helper so writers/actors land in roles
            metadata.roles.clear()
            apply_roles(metadata.roles, meta_json)

            clear_posters(metadata)
            poster_name = meta_json.get('show_thumbnail') or 'cover.jpg'
            self.update_poster(metadata, poster_name, show_path)

        # ---- seasons / episodes
        for season_index, season_object in media.seasons.items():
            season_metadata = metadata.seasons[season_index]

            # pick the first playable episode in this season to locate the folder
            episode_keys = sorted(season_object.episodes.keys(), key=lambda k: int(k))
            first_episode_path = season_object.episodes[episode_keys[0]].items[0].parts[0].file
            season_path = os.path.normpath(os.path.join(first_episode_path, '..'))
            season_name = os.path.basename(season_path)

            # season poster + summary
            season_summary = season_name  # default
            season_file_meta = load_json_if_exists(os.path.join(season_path, 'meta.json'))

            clear_posters(season_metadata)
            self.update_poster(season_metadata, 'cover.jpg', season_path)

            if season_file_meta and season_file_meta.get('summary'):
                season_summary = ('%s\n%s' % (season_name, season_file_meta['summary'])).strip()
            elif meta_json and 'seasons' in meta_json and season_index in meta_json['seasons']:
                season_meta_json = meta_json['seasons'][season_index]
                season_summary = ('%s\n%s' % (season_name, season_meta_json.get('summary', ''))).strip()

            season_metadata.summary = season_summary

            # Season dates and ratings, which need to be handled as I generated them still
            if season_file_meta:
                s_date = parse_available_at(season_file_meta)
                if s_date:
                    Log.Info('Season date present (%s) but ignored; seasons have no originally_available_at.' % s_date)

                s_rating = coerce_rating(season_file_meta.get('rating'))
                if s_rating is not None:
                    try:
                        season_metadata.rating = s_rating
                    except Exception as ex:
                        Log.Warn('Failed setting season rating: %s' % ex)

            # Update Season attempt
            try:
                self.update_season(season_object.id, season_summary)
            except Exception as ex:
                Log.Warn('update_season failed for season %s: %s' % (season_index, ex))

            # ------------- episodes ----------------
            for episode_index, episode_object in season_object.episodes.items():
                episode_metadata = season_metadata.episodes[episode_index]
                if not (episode_object.items and episode_object.items[0].parts):
                    continue

                episode_path = episode_object.items[0].parts[0].file
                ep_meta = load_episode_meta(episode_path)
                if ep_meta is None:
                    Log.Info('No episode meta for: %s' % episode_path)
                else:
                    Log.Info('Episode meta keys for %s: %s' % (episode_path, sorted(ep_meta.keys())))

                # Title
                _, _, title = episode_fields_from_filename(episode_path)
                episode_metadata.title = ep_meta.get('title') if (ep_meta and ep_meta.get('title')) else title

                # Summary
                if ep_meta and (ep_meta.get('summary') or ep_meta.get('description')):
                    episode_metadata.summary = ep_meta.get('summary') or ep_meta.get('description')

                # Date
                ep_date = parse_available_at(ep_meta) if ep_meta else None
                if ep_date:
                    episode_metadata.originally_available_at = ep_date

                # Rating
                if ep_meta and ('rating' in ep_meta):
                    r = coerce_rating(ep_meta.get('rating'))
                    if r is not None:
                        episode_metadata.rating = r
                    else:
                        Log.Warn('Invalid rating in %s: %r' % (episode_path, ep_meta.get('rating')))

                # Credits (writers, directors, actors)
                if ep_meta and (ep_meta.get('writers') or ep_meta.get('actors') or ep_meta.get('directors')):
                    apply_episode_credits(episode_metadata, ep_meta)

                # Episode thumb
                poster_path = episode_poster_image_path(episode_path)
                try:
                    if poster_path:
                        data = Core.storage.load(poster_path)
                        image_hash = hashlib.md5(data).hexdigest()

                        try: episode_metadata.thumbs.clear()
                        except Exception: pass
                        try: episode_metadata.posters.clear()
                        except Exception: pass

                        episode_metadata.thumbs[image_hash] = Proxy.Media(data)
                        Log.Info('Episode art set from %s' % poster_path)
                    else:
                        Log.Info('No art for episode: %s' % episode_path)
                except Exception as ex:
                    Log.Warn('Failed to set episode art for %s: %s' % (episode_path, ex))

# Mute that missing Start() warning in logs
def Start():
    pass

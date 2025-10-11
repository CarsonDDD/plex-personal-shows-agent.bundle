import os, json
import urllib
import hashlib
from Helpers import (
    clear_posters,
    parse_available_at,
    episode_fields_from_filename,
    episode_poster_image_path,
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

        # Fast path: assume S1E1 exists
        try:
            first_episode_path = media.seasons['1'].episodes['1'].items[0].parts[0].file
        except Exception:
            pass

        # Fallback: find the first playable file anywhere
        if not first_episode_path:
            for season_obj in media.seasons.items():
                for episode_obj in season_obj.episodes.items():
                    if episode_obj.items and episode_obj.items[0].parts:
                        first_episode_path = episode_obj.items[0].parts[0].file
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
            metadata.summary = meta_json.get('summary', '')
            metadata.studio = meta_json.get('publisher', '')

            # Only set the date if valid
            show_date = parse_available_at(meta_json)
            if show_date:
                metadata.originally_available_at = show_date
                Log.Info('Set show originally_available_at = %s' % show_date)

            metadata.collections.clear()
            for collections in meta_json.get('collections', []):
                metadata.collections.add(collections)

            metadata.genres.clear()
            for genre in meta_json.get('tags', []):
                metadata.genres.add(genre)

            metadata.roles.clear()
            for actor in meta_json.get('actors', []):
                role = metadata.roles.new()
                role.role = actor.get('role', '')
                role.name = actor.get('name', '')
                role.photo = actor.get('photo', '')


            clear_posters(metadata)
            self.update_poster(metadata, meta_json.get('show_thumbnail', 'cover.jpg'), show_path)

        # ---- seasons / episodes
        for season_index, season_object in media.seasons.items():
            season_metadata = metadata.seasons[season_index]
            episode_keys = season_object.episodes.keys() # removed list wrap/sort meme (my own stuff) todo: test that change
            first_episode_path = season_object.episodes[episode_keys[0]].items[0].parts[0].file
            season_path = os.path.normpath(os.path.join(first_episode_path, '..')) # Episodes are not folders ...... TODO: IF EPISODES EVER BECOME FOLDERS, THE CHANGES NEED TO BE MADE HERE.
            season_name = os.path.basename(season_path)

            # season poster + summary
            season_summary = season_name # default value

            clear_posters(season_metadata)
            if meta_json and 'seasons' in meta_json and season_index in meta_json['seasons']:
                season_meta_json = meta_json['seasons'][season_index]

                self.update_poster(season_metadata, season_meta_json.get('poster', 'cover.jpg'), season_path)
                season_summary = ('%s\n%s' % (season_name, season_meta_json.get('summary', ''))).strip()
            else:
                self.update_poster(season_metadata, 'cover.jpg', season_path)


            season_metadata.summary = season_summary

            # here is the big change. We no longer crash when the api fails!!!!
            try:
                self.update_season(season_object.id, season_summary)
            except Exception as ex:
                Log.Warn('update_season failed for season %s: %s' % (season_index, ex))

            # episodes
            for episode_index, episode_object in season_object.episodes.items():
                episode_metadata = season_metadata.episodes[episode_index]

                if not (episode_object.items and episode_object.items[0].parts):
                    continue

                episode_path = episode_object.items[0].parts[0].file

                # Title from filename
                _, _, title = episode_fields_from_filename(episode_path)
                episode_metadata.title = title

                # Episode poster/thumbnail (new feature, but needed!). poster is just the video, but with image extension
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
                        #episode_metadata.posters[image_hash] = Proxy.Media(data)
                        Log.Info('Episode art set from %s' % poster_path)
                    else:
                        Log.Info('No art for episode: %s' % episode_path)
                except Exception as ex:
                    Log.Warn('Failed to set episode art for %s: %s' % (episode_path, ex))

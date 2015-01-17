#!/usr/bin/env python3.4
# -*- coding: utf-8 -*-

import argparse
import glob
import json
import os
import shelve
import shutil
import time
import urllib.request
import webbrowser
from concurrent import futures
from html import unescape
from urllib.parse import urlparse, parse_qs

from mutagenx.id3 import ID3NoHeaderError
from mutagenx.id3 import ID3, TALB, TIT2, TPE1, TPE2


APP_ID = '3889070'
APP_SCOPE = 'audio,offline'
AUTH_FILE = '.auth_data'
OUTPUT_FOLDER = 'vk_music'
ALBUM = 'vkMusic'


class APIException(Exception):
    pass


class Authorization():
    def __init__(self, app_id, app_scope):
        self.app_id = app_id
        self.app_scope = app_scope

        self.redirected_url = None
        self.access_token = None
        self.uid = None
        self.expires_in = None

        with shelve.open(AUTH_FILE) as db:
            try:
                self.access_token = db['access_token']
                self.uid = db['uid']
                self.expires_in = db['expires_in']
            except KeyError:
                self._open_auth_dialog()
                self._parse_redirect_url()
                db['access_token'] = self.access_token
                db['uid'] = self.uid
                db['expires_in'] = self.expires_in

    def _open_auth_dialog(self):
        url = (
            "https://oauth.vk.com/authorize?"
            "client_id={app_id}&"
            "scope={scope}&"
            "redirect_uri=http://oauth.vk.com/blank.html&"
            "display=page&"
            "response_type=token"
        ).format(app_id=self.app_id, scope=self.app_scope)
        webbrowser.open_new_tab(url)
        redirected_url = input("Enter redirected URL: ")
        self.redirected_url = redirected_url

    def _parse_redirect_url(self):
        parsed_url = urlparse(self.redirected_url)
        fragment = parsed_url.fragment
        parsed_fragment = parse_qs(fragment)
        if 'error' in parsed_fragment and 'error_description' in parsed_fragment:
            raise APIException('{0}: {1}'.format(parsed_fragment['error'], parsed_fragment['error_description']))
        self.access_token = parsed_fragment.get('access_token')[0]
        self.uid = parsed_fragment.get('user_id')[0]
        self.expires_in = parsed_fragment.get('expires_in')[0]


class UserMusic(object):
    def __init__(self, uid, access_token, output_folder, album):
        self.uid = uid
        self.access_token = access_token
        self.output_folder = output_folder
        self.album = album
        self.cpu_count = os.cpu_count()

        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        # '{04}_{}.mp3
        self.folder_aids = {x[5:-4] for x in os.listdir(self.output_folder)}

        url = (
            "https://api.vkontakte.ru/method/audio.get.json?"
            "uid={uid}&access_token={access_token}"
        ).format(uid=self.uid, access_token=self.access_token)
        response = urllib.request.urlopen(url)
        content = response.read()
        self._content = json.loads(content.decode('utf-8'))
        self.music_list = self._content['response']

        self.tracks_map = {}
        for ind, track in enumerate(reversed(self.music_list)):
            self.tracks_map[str(track['aid'])] = {
                'index': ind,
                'artist': unescape(track['artist']),
                'title': unescape(track['title']),
                'url': track['url'],
                'output_path': os.path.join(output_folder, '{}_{}.mp3'.format(format(ind, '04'), track['aid'])),
            }

    def __call__(self):
        # remove deleted songs from vk
        drop_aids = self.folder_aids.difference(self.tracks_map.keys())
        if drop_aids:
            self.pprint('Removing Deleted Songs')

            for drop_aid in drop_aids:
                pattern = os.path.join(self.output_folder, '*_{}.mp3'.format(drop_aid))
                paths = glob.glob(pattern)
                for pth in paths:
                    os.remove(pth)
                    print('\u2718', pth)
                    self.folder_aids.remove(drop_aid)

        # which tracks to process
        for aid in self.folder_aids:
            del self.tracks_map[aid]

        if self.tracks_map:
            t = time.time()
            self.pprint('Downloading New Songs from Your vk Music Collection.')
            self.download()

            self.pprint('Updating Songs Tags')
            self.update_tags()
            self.pprint('Processing Time: {} seconds'.format(time.time() - t), symbol='#')
        else:
            self.pprint('Music collection is up to date')

    def download(self):
        with futures.ProcessPoolExecutor(max_workers=self.cpu_count) as executor:
            executor.map(self._get_track, self.tracks_map.values())

    def _get_track(self, track):
        track_name = '{artist} - {title}'.format(**track)

        with urllib.request.urlopen(track['url']) as track_resp,\
                open(track['output_path'], 'wb') as out_file:
            shutil.copyfileobj(track_resp, out_file)

        print('\u2705', track_name, '-->', out_file.name)

    def update_tags(self):
        with futures.ProcessPoolExecutor(max_workers=self.cpu_count) as executor:
            executor.map(self._update_track_tags, self.tracks_map.values())

    def _update_track_tags(self, track):
        fname = track['output_path']
        artist = track['artist']
        title = track['title']

        # http://stackoverflow.com/a/14040318/1886653
        try:
            tags = ID3(fname)
            tags.delete()
        except ID3NoHeaderError:
            tags = ID3()

        tags["TALB"] = TALB(encoding=3, text=self.album)
        tags["TIT2"] = TIT2(encoding=3, text=artist)
        tags["TPE1"] = TPE1(encoding=3, text=title)
        tags["TPE2"] = TPE2(encoding=3, text=self.album)
        tags.save(fname)

        print('\u2705', fname, '-->', '{} - {} - {}'.format(self.album, artist, title))

    @staticmethod
    def pprint(s, symbol='*', count=80):
        print(symbol * count, s, symbol * count, sep='\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--destination', action='store', dest='output_folder',
                        default=OUTPUT_FOLDER, help='Output folder')
    parser.add_argument('-a', '--album', action='store', dest='album',
                        default=ALBUM, help='Album title')
    cli_args = parser.parse_args()

    auth = Authorization(APP_ID, APP_SCOPE)
    music = UserMusic(auth.uid, auth.access_token, output_folder=cli_args.output_folder, album=cli_args.album)()

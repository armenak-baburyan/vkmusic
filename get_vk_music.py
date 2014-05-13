#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import shelve
import shutil
import time
import urllib.request
import webbrowser
from concurrent import futures
from urllib.parse import urlparse, parse_qs


APP_ID = '3889070'
APP_SCOPE = 'audio,offline'
AUTH_FILE = '.auth_data'
OUTPUT_FOLDER = 'vk_music'


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
    def __init__(self, uid, access_token, output_folder):
        self.uid = uid
        self.access_token = access_token

        self.output_folder = output_folder
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        self.aids = {x[:-4] for x in os.listdir(self.output_folder)}

        url = (
            "https://api.vkontakte.ru/method/audio.get.json?"
            "uid={uid}&access_token={access_token}"
        ).format(uid=self.uid, access_token=self.access_token)
        response = urllib.request.urlopen(url)
        content = response.read()
        self._content = json.loads(content.decode('utf-8'))
        self.music_list = self._content['response']

    def download(self):
        with futures.ProcessPoolExecutor(max_workers=4) as executor:
            executor.map(self.get_track, reversed(self.music_list))

    def get_track(self, track):
        track_name = '{artist} - {title}'.format(**track)
        if str(track['aid']) in self.aids:
            print('skipped: ', track_name)
            return

        with urllib.request.urlopen(track['url']) as track_resp,\
                open(os.path.join(self.output_folder, '{}.mp3'.format(track['aid'])), 'wb') as out_file:
            shutil.copyfileobj(track_resp, out_file)
        self.aids.add(track['aid'])
        print(track_name, '-->', out_file.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--destination', action='store', dest='output_folder',
                        default=OUTPUT_FOLDER, help='Output folder')
    cli_args = parser.parse_args()

    auth = Authorization(APP_ID, APP_SCOPE)

    music = UserMusic(auth.uid, auth.access_token, output_folder=cli_args.output_folder)
    print('Downloading Your vk Music Collection.')
    t = time.time()
    music.download()
    print('Download Complete')
    print('Processing Time: {} seconds'.format(time.time() - t))


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import webbrowser
import shelve
import shutil
import json
import urllib.request
import os
import hashlib
from urllib.parse import urlparse, parse_qs


APP_ID = '3889070'
APP_SCOPE = 'audio,offline'
AUTH_FILE = '.auth_data'


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

        db = shelve.open(AUTH_FILE)

        if 'access_token' not in db or 'uid' not in db or 'expires_in' not in db:
            self._open_auth_dialog()
            self._parse_redirect_url()
            db['access_token'] = self.access_token
            db['uid'] = self.uid
            db['expires_in'] = self.expires_in
        else:
            self.access_token = db['access_token']
            self.uid = db['uid']
            self.expires_in = db['expires_in']

        db.close()

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
    def __init__(self, uid, access_token):
        self.uid = uid
        self.access_token = access_token

        #url = 'https://api.vk.com/method/audio.get.json'
        #payloads = {'uid': self.uid, 'access_token': self.access_token}
        #self.response = requests.get(url, params=payloads).json()
        #self.music_list = self.response['response']
        url = (
            "https://api.vkontakte.ru/method/audio.get.json?"
            "uid={uid}&access_token={access_token}"
        ).format(uid=self.uid, access_token=self.access_token)
        response = urllib.request.urlopen(url)
        content = response.read()
        self._content = json.loads(content.decode('utf-8'))
        self.music_list = self._content['response']

    def download(self, title=None, dest='music collection'):
        if not os.path.exists(dest):
            os.makedirs(dest)
        if title is None:
            for counter, track in enumerate(reversed(self.music_list)):
                with urllib.request.urlopen(track['url']) as track_resp,\
                    open(os.path.join(dest, '{0:04d}.mp3'.format(counter)), 'wb') as out_file:
                    shutil.copyfileobj(track_resp, out_file)
        else:
            for counter, track in enumerate(self.music_list):
                if '{0} – {1}'.format(track['artist'], track['title']) == title:
                    break
                with urllib.request.urlopen(track['url']) as track_resp,\
                    open(os.path.join(dest, '{0:04d}.mp3'.format(counter)), 'wb') as out_file:
                    shutil.copyfileobj(track_resp, out_file)


def hash_file(file, chunk_size=8192):
    md5 = hashlib.md5()

    with open(file, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            md5.update(chunk)

    return md5.hexdigest()


if __name__ == '__main__':
    auth = Authorization(APP_ID, APP_SCOPE)

    music = UserMusic(auth.uid, auth.access_token)
    #print(json.dumps(music.music_list, indent=4))
    music.download('Snow Patrol – Called Out In The Dark')

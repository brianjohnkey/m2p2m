#!/usr/bin/env python3

import sys
import signal
import os
import json
import re
import argparse
import configparser
import pathlib
import unicodedata
from plexapi.myplex import MyPlexAccount
from plexapi.library import Library
from pprint import pprint
import hashlib

BLOCK_SIZE = 65536
script_dir = pathlib.Path(__file__).resolve().parent

def signal_handler(signal_caught, frame):
    print('\nOperations interupted. Exiting.')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def PreparePlexAccess():
    global plex, plex_music_library, plex_playlists, plex_playlist_library
    print("Establishing a connection to the Plex Server")
    print("Please wait.....")
    config = configparser.ConfigParser()
    config.read('plex_account.ini')
    login = config['PLEX']['login']
    password = config['PLEX']['password']
    server = config['PLEX']['server']
    account = MyPlexAccount(login, password)
    plex = account.resource(server).connect()  # returns a PlexServer instance
    # for brute force searching
    print("Building a library of all tracks for brute force searching")
    print("Please wait.....")
    plex_music_library = plex.library.section('Music').all(libtype='track')
    plex_playlist_library = plex.playlists(playlistType='audio')
    # load all playlist names from Plex
    plex_playlists = []
    for playlist in plex_playlist_library:
        plex_playlists.append(playlist.title)

def DeletePlaylist(playlist_to_delete):
    for playlist in plex_playlist_library:
        if playlist.title == playlist_to_delete:
            print(f"Deleting Plex playlist: {playlist.title}")
            playlist.delete()


def get_fingerprint(filepath):
    hash_method = hashlib.md5()
    with open(filepath, 'rb') as input_file:
        buf = input_file.read(BLOCK_SIZE)
        while len(buf) > 0:
            hash_method.update(buf)
            buf = input_file.read(BLOCK_SIZE)
    
    return hash_method.hexdigest()

def has_changed(filepath, key_path):
    update_json=True
    json_path = script_dir / "status_db"
    fingerprint = get_fingerprint(filepath)
    json_dict = None
    if not os.path.exists(json_path):
        if update_json:
            json_dict = {key_path: fingerprint}
            _update_json_file(json_dict=json_dict, json_path=json_path)
            return True
    else:
        with open(json_path, 'r') as json_file: 
            json_dict = json.loads(json_file.read())
            
    if key_path not in json_dict:
        if update_json:
            json_dict[key_path] = fingerprint
            _update_json_file(json_dict=json_dict, json_path=json_path)
        return True
        
    if not json_dict[key_path] == fingerprint:
        if update_json:
            json_dict[key_path] = fingerprint
            _update_json_file(json_dict=json_dict, json_path=json_path)
        return True
    
    return False

        
def _update_json_file(json_dict, json_path):
    with open(json_path, 'w') as json_file:
        json_file.write(json.dumps(json_dict, sort_keys=True, indent=4))


def Process_m3u(infile):
    try:
        assert(type(infile) == '_io.TextIOWrapper')
    except AssertionError:
        m3ufile = open(infile, 'r', encoding='latin-1')
    lines = m3ufile.readlines()

    tracks_in_m3u = []
    tracks_found = []
    print(f"\nProcessing tracks in m3u playlist: {infile}")
    if CLI.verbose: print("# means brute force was required")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith('#EXTINF:'):
            # Extended m3u format
            length, title = line.split('#EXTINF:')[1].split(',', 1)
            path = lines[i + 1].strip()
            path = path.encode('latin-1').decode('utf-8')
            i += 2
            tracks_in_m3u.append(path)
            try:
                print('.', end='', flush=True)
                artist, title = title.split(' - ', 1)
                track = PlexTitleSearch(title, artist, path)
                if track:
                    tracks_found.append(track)
            except ValueError:
                print(f"\nSkipping track: '{title}'")

        elif line and not line.startswith('#'):
            # Bare m3u format - path only, extract artist/title from filename
            path = line
        elif line and not line.startswith('#'):
            # Bare m3u format - path only, extract artist/title from filename
            path = line
            path = path.encode('latin-1').decode('utf-8')  # fix mojibake for special chars
            i += 1            
            tracks_in_m3u.append(path)
            try:
                print('.', end='', flush=True)
                filename = pathlib.Path(path).stem  # e.g. "01 - Madonna - Nothing Really Matters"
                parts = filename.split(' - ', 2)
                if len(parts) >= 3:
                    artist = parts[1].strip()
                    title = parts[2].strip()
                elif len(parts) == 2:
                    artist = parts[0].strip()
                    title = parts[1].strip()
                else:
                    artist = ""
                    title = filename
                track = PlexTitleSearch(title, artist, path)
                if track:
                    tracks_found.append(track)
            except ValueError:
                print(f"\nSkipping track: '{path}'")
        else:
            i += 1

    if CLI.verbose:
        print(f"\nMatched {len(tracks_found)} Plex tracks from {len(tracks_in_m3u)} tracks in {m3ufile.name}")

    return tracks_found

def CreatePlaylist(playlist_name, tracks):
    music_lib_section = 'Music'
    # Just in case we have an empty playlist
    if len(tracks) > 0:
        plex.createPlaylist(title=playlist_name, section=music_lib_section, items=tracks)
        print(f"{playlist_name} created in Plex")
    else:
        print(f"{playlist_name} is empty and not created")

def PlexTitleSearch(m3uTitle, m3uArtist, m3uPath):
    # don't worry about ~@~ chars below. View in VSCode or Notepad
    # to see that they are curly quotes. Vim does not like them ;^)
    normalized_paths = [
        m3uPath.lower(),
        m3uPath.lower().replace("ΓÇÖ", "'"),
        m3uPath.lower().replace("'", "ΓÇÖ"),
        m3uPath.lower().replace("ΓÇ£", '"'),
        m3uPath.lower().replace('"', "ΓÇ£"),
        m3uPath.lower().replace("&", "and"),
        m3uPath.lower().replace("and", "&")
    ]
    # for brute force comparison if needed - fixed trailing comma bug from original
    m3uStripped = re.sub(r'\W+', '', m3uPath.lower())

    # this is a "contains" string search of the track title
    # So we are getting a list of all tracks that match
    tracks = plex.library.search(title=m3uTitle, libtype="track")
    for track in tracks:
        # extract the path to the file on the system that Plex has stored
        PlexPath = track.media[0].parts[0].file
        if CLI.debug:
            if 'Ziq' in m3uPath or 'j' in m3uPath:  # adjust to match your failing artists
                print(f"\n  m3u : {repr(m3uPath)}")
                print(f"  plex: {repr(PlexPath)}")
        # If the path in Plex matches the path from the m3u file we are good
        if unicodedata.normalize('NFC', PlexPath) == unicodedata.normalize('NFC', m3uPath):
            return track

        # Now try some brute force matching
        if PlexPath.lower() in normalized_paths:
            return track

        PlexStripped = re.sub(r'\W+', '', PlexPath.lower())
        if PlexStripped == m3uStripped:
            if CLI.verbose: print(m3uStripped," == ",PlexStripped)
            return track

        if track.title.lower() == m3uTitle.lower():
            if track.originalTitle and (track.originalTitle.lower() == m3uArtist.lower()):
                return track
            elif track.grandparentTitle.lower() == m3uArtist.lower():
                return track

    # Now for the really hard core 
    print('#', end='', flush=True)
    track = BruteForceMatch(m3uPath)
    if track:
        return track
    else:
        print(f"No match for {m3uPath}")

    return None
            
# Plex definitely has bugs because many of the missing can be found by artist search
# but not by song title. Even via tha UI
def BruteForceMatch(m3uPath):
    m3uStripped = re.sub(r'\W+', '', m3uPath.lower())
    for track in plex_music_library:
        PlexPath = track.media[0].parts[0].file
        PlexStripped = re.sub(r'\W+', '', PlexPath.lower())
        if m3uStripped == PlexStripped:
            if CLI.verbose: print(f"\nFound by brute force:\n\t{PlexPath}")
            return track

    return None

def FindAllm3uFiles(path):
    FileList = []
    for filename in os.scandir(path):
        if filename.is_file():
            extension = pathlib.Path(filename).suffix
            if extension == '.m3u':
                if CLI.verbose: print(filename.path)
                FileList.append(filename.path)
    return FileList

def cli_parser():
    """Parse command line options"""
    global CLI
    parser = argparse.ArgumentParser(description='Convert m3u playlists to Plex playlists')
    # argparse automatically uses the --long option as the dest name. cool.
    # https://docs.python.org/3/library/argparse.html#dest
    parser.add_argument('-d', '--debug', action='store_true', help='Debugging output')
    parser.add_argument('-v', '--verbose', action='store_true', help='Let it spew!')
    parser.add_argument('-r', '--replace', action='store_true', help='If m3u is changed Plex playlist is deleted and recreated')
    parser.add_argument('-p', '--pretend', action='store_false', dest='create_playlists', default=True, help='Do not create playlists')
    parser.add_argument('path_to_m3u_files', default=None, type=pathlib.Path,
        metavar="/path/to/m3u/playlists[/playslist.m3u]", help="Single m3u file or directory containing m3u files")

    CLI = parser.parse_args()
    if CLI.debug: print("cli_arg contains:\n", CLI)
    return CLI

def main():
    cli_parser()

    # Handle the case where a single m3u file is specified
    if os.path.isfile(CLI.path_to_m3u_files):
        file_path = pathlib.Path(CLI.path_to_m3u_files)
        PlaylistName = file_path.stem
        PreparePlexAccess()
        if not has_changed(file_path, PlaylistName) and PlaylistName in plex_playlists:
            print(f"Skipping playlist: \"{PlaylistName}\" is unchanged")
        else:
            tracks_found = Process_m3u(file_path)
            if CLI.create_playlists: CreatePlaylist(PlaylistName, tracks_found)
        exit()
        
    if not os.path.isdir(CLI.path_to_m3u_files):
        print(f"{CLI.path_to_m3u_files} is not a directory or file")
        exit()

    m3uPlaylists = FindAllm3uFiles(CLI.path_to_m3u_files)
    if len(m3uPlaylists) > 0:
        PreparePlexAccess()
    else:
        print(f"Did not find any m3u files in {CLI.path_to_m3u_files}!")
        exit()

    for playlist_file in m3uPlaylists:
        file_path = pathlib.Path(playlist_file)
        PlaylistName = file_path.stem
        if not has_changed(playlist_file, PlaylistName) and PlaylistName in plex_playlists:
            print(f"Skipping playlist: \"{PlaylistName}\" is unchanged")
            continue
        if PlaylistName in plex_playlists:
            if CLI.replace:
                DeletePlaylist(PlaylistName)
            else:
                print(f"Skipping playlist: \"{PlaylistName}\" already in Plex")
                continue
        tracks_found = Process_m3u(playlist_file)
        if CLI.create_playlists: CreatePlaylist(PlaylistName, tracks_found)

if __name__ == '__main__':
    main()
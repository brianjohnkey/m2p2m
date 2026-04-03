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
    print('\nOperations interrupted. Exiting.', flush=True)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def PreparePlexAccess():
    global plex, plex_music_library, plex_playlists, plex_playlist_library
    print("Establishing a connection to the Plex Server...", flush=True)
    config = configparser.ConfigParser()
    config.read('plex_account.ini')
    
    try:
        login = config['PLEX']['login']
        password = config['PLEX']['password']
        server = config['PLEX']['server']
    except KeyError as e:
        print(f"Error: Missing configuration key {e} in plex_account.ini")
        sys.exit(1)

    account = MyPlexAccount(login, password)
    plex = account.resource(server).connect()
    
    print("Building a library of all tracks for brute force searching (This may take a minute)...", flush=True)
    plex_music_library = plex.library.section('Music').all(libtype='track')
    plex_playlist_library = plex.playlists(playlistType='audio')
    
    plex_playlists = [playlist.title for playlist in plex_playlist_library]
    print(f"Connection established. Found {len(plex_music_library)} tracks in library.", flush=True)

def DeletePlaylist(playlist_to_delete):
    for playlist in plex_playlist_library:
        if playlist.title == playlist_to_delete:
            print(f"Deleting Plex playlist: {playlist.title}", flush=True)
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
    update_json = True
    json_path = script_dir / "status_db"
    fingerprint = get_fingerprint(filepath)
    
    if not os.path.exists(json_path):
        json_dict = {key_path: fingerprint}
        _update_json_file(json_dict, json_path)
        return True
    
    with open(json_path, 'r') as json_file:
        try:
            json_dict = json.load(json_file)
        except json.JSONDecodeError:
            json_dict = {}

    if key_path not in json_dict or json_dict[key_path] != fingerprint:
        if update_json:
            json_dict[key_path] = fingerprint
            _update_json_file(json_dict, json_path)
        return True
    
    return False

def _update_json_file(json_dict, json_path):
    with open(json_path, 'w') as json_file:
        json.dump(json_dict, json_file, sort_keys=True, indent=4)

def Process_m3u(infile):
    m3ufile_path = pathlib.Path(infile)
    # Open with latin-1 to handle common m3u encoding issues
    with open(m3ufile_path, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    tracks_found = []
    print(f"\nProcessing: {m3ufile_path.name}", flush=True)
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith('#EXTM3U'):
            i += 1
            continue

        artist, title, path = "", "", ""

        if line.startswith('#EXTINF:'):
            # Extended format: metadata on this line, path on next
            try:
                metadata = line.split('#EXTINF:')[1]
                length, info = metadata.split(',', 1)
                if ' - ' in info:
                    artist, title = info.split(' - ', 1)
                else:
                    title = info
                
                path = lines[i + 1].strip()
                # Attempt to fix encoding
                path = path.encode('latin-1').decode('utf-8', errors='ignore')
                i += 2
            except (IndexError, ValueError):
                i += 1
                continue
        else:
            # Simple format: path only
            path = line.encode('latin-1').decode('utf-8', errors='ignore')
            filename = pathlib.Path(path).stem
            parts = filename.split(' - ', 2)
            if len(parts) >= 3:
                artist, title = parts[1].strip(), parts[2].strip()
            elif len(parts) == 2:
                artist, title = parts[0].strip(), parts[1].strip()
            else:
                title = filename
            i += 1

        if title:
            print(f"  > Searching: {title}...", end='', flush=True)
            track = PlexTitleSearch(title, artist, path)
            if track:
                tracks_found.append(track)
                print(" Found.", flush=True)
            else:
                print(" Not Found.", flush=True)

    return tracks_found

def CreatePlaylist(playlist_name, tracks):
    if len(tracks) > 0:
        # 1. Create the playlist with only the first track to avoid URL length issues
        new_playlist = plex.createPlaylist(title=playlist_name, items=tracks[0])
        print(f"Created playlist '{playlist_name}'. Adding remaining tracks...", flush=True)
        
        # 2. Add the rest of the tracks in batches of 100
        batch_size = 100
        remaining_tracks = tracks[1:]
        
        for i in range(0, len(remaining_tracks), batch_size):
            chunk = remaining_tracks[i:i + batch_size]
            new_playlist.addItems(chunk)
            print(f"  > Added tracks {i+2} to {min(i+batch_size+1, len(tracks))}...", flush=True)
            
        print(f"Success: '{playlist_name}' finalized with {len(tracks)} tracks.", flush=True)
    else:
        print(f"Skipped: '{playlist_name}' had no matched tracks.", flush=True)

def PlexTitleSearch(m3uTitle, m3uArtist, m3uPath):
    normalized_paths = [
        m3uPath.lower(),
        m3uPath.lower().replace("’", "'").replace("‘", "'"),
        m3uPath.lower().replace("&", "and"),
        m3uPath.lower().replace("and", "&")
    ]
    m3uStripped = re.sub(r'\W+', '', m3uPath.lower())

    # 1. Direct Title Search
    try:
        tracks = plex.library.search(title=m3uTitle, libtype="track")
    except Exception:
        tracks = []

    for track in tracks:
        PlexPath = track.media[0].parts[0].file
        
        # Exact Path Match
        if unicodedata.normalize('NFC', PlexPath) == unicodedata.normalize('NFC', m3uPath):
            return track

        # Fuzzy Path Match
        if PlexPath.lower() in normalized_paths:
            return track

        # Stripped Match
        PlexStripped = re.sub(r'\W+', '', PlexPath.lower())
        if PlexStripped == m3uStripped:
            return track

        # Metadata Match
        if track.title.lower() == m3uTitle.lower():
            if m3uArtist and (
                (track.originalTitle and track.originalTitle.lower() == m3uArtist.lower()) or 
                (track.grandparentTitle.lower() == m3uArtist.lower())
            ):
                return track

    # 2. Brute Force Match
    return BruteForceMatch(m3uPath)
            
def BruteForceMatch(m3uPath):
    m3uStripped = re.sub(r'\W+', '', m3uPath.lower())
    for track in plex_music_library:
        PlexPath = track.media[0].parts[0].file
        PlexStripped = re.sub(r'\W+', '', PlexPath.lower())
        if m3uStripped == PlexStripped:
            return track
    return None

def FindAllm3uFiles(path):
    return [f.path for f in os.scandir(path) if f.is_file() and f.name.endswith('.m3u')]

def cli_parser():
    global CLI
    parser = argparse.ArgumentParser(description='Convert m3u playlists to Plex playlists')
    parser.add_argument('-d', '--debug', action='store_true', help='Debugging output')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-r', '--replace', action='store_true', help='Recreate existing playlists')
    parser.add_argument('-p', '--pretend', action='store_false', dest='create_playlists', default=True, help='Dry run')
    parser.add_argument('path_to_m3u_files', type=pathlib.Path, help="M3U file or directory")
    CLI = parser.parse_args()
    return CLI

def main():
    cli_parser()
    target = CLI.path_to_m3u_files

    if os.path.isfile(target):
        m3u_list = [target]
    elif os.path.isdir(target):
        m3u_list = FindAllm3uFiles(target)
    else:
        print(f"Error: {target} is not a valid file or directory.")
        return

    if not m3u_list:
        print("No M3U files found.")
        return

    PreparePlexAccess()

    for playlist_file in m3u_list:
        file_path = pathlib.Path(playlist_file)
        playlist_name = file_path.stem
        
        changed = has_changed(playlist_file, playlist_name)
        exists_in_plex = playlist_name in [p.title for p in plex_playlist_library]

        if not changed and exists_in_plex:
            print(f"Skipping: '{playlist_name}' (No changes detected).", flush=True)
            continue
        
        if exists_in_plex:
            if CLI.replace:
                DeletePlaylist(playlist_name)
            else:
                print(f"Skipping: '{playlist_name}' already exists in Plex. Use -r to overwrite.", flush=True)
                continue

        tracks_found = Process_m3u(playlist_file)
        if CLI.create_playlists:
            CreatePlaylist(playlist_name, tracks_found)

if __name__ == '__main__':
    main()
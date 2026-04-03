#!/usr/bin/env python3

import argparse
import configparser
import pathlib
from plexapi.myplex import MyPlexAccount

def cli_parser():
    global CLI
    parser = argparse.ArgumentParser(description='Export Plex playlists to m3u files')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-l', '--list', action='store_true', help='List all Plex playlists and exit')
    parser.add_argument('-o', '--output', type=pathlib.Path, default=pathlib.Path('.'),
        help='Output directory for m3u files (default: current directory)')
    parser.add_argument('playlist_name', nargs='?', default=None,
        help='Name of Plex playlist to export, or omit to export all')
    CLI = parser.parse_args()
    return CLI

def connect():
    config = configparser.ConfigParser()
    config.read('plex_account.ini')
    account = MyPlexAccount(config['PLEX']['login'], config['PLEX']['password'])
    return account.resource(config['PLEX']['server']).connect()

def export_playlist(plex, playlist, output_dir):
    filename = output_dir / f"{playlist.title}.m3u"
    tracks = playlist.items()
    if len(tracks) == 0:
        print(f"Skipping '{playlist.title}' — empty playlist")
        return
    with open(filename, 'w', encoding='utf-8') as f:
        for track in tracks:
            path = track.media[0].parts[0].file
            f.write(path + '\n')
    print(f"Exported '{playlist.title}' — {len(tracks)} tracks → {filename}")

def main():
    cli_parser()
    plex = connect()

    audio_playlists = plex.playlists(playlistType='audio')

    if CLI.list:
        print("Plex audio playlists:")
        for pl in audio_playlists:
            print(f"  {pl.title} ({pl.leafCount} tracks)")
        return

    CLI.output.mkdir(parents=True, exist_ok=True)

    if CLI.playlist_name:
        match = [pl for pl in audio_playlists if pl.title == CLI.playlist_name]
        if not match:
            print(f"Playlist '{CLI.playlist_name}' not found in Plex")
            return
        export_playlist(plex, match[0], CLI.output)
    else:
        for pl in audio_playlists:
            export_playlist(plex, pl, CLI.output)

if __name__ == '__main__':
    main()
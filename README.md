# m2p2m
A Python command-line tool for syncing MusicBee playlists to Plex Media Server, and exporting Plex playlists back to m3u format.
Scripts

* m2p.py — Imports m3u playlists into Plex
* p2m.py — Exports Plex playlists to m3u files

## Features

Supports both extended m3u (with #EXTINF: headers) and bare m3u (paths only) formats
Multiple track matching strategies: exact path, normalized path variants, stripped comparison, artist/title metadata, and brute force full-library scan
Change detection via MD5 fingerprinting — unchanged playlists are skipped on subsequent runs
Handles Unicode characters in filenames (e.g. µ-Ziq, Björk)
Dry run mode — preview matches without creating playlists
Export single or all Plex playlists to m3u

## Requirements

- Python 3.7+
- A Plex Media Server account and running server instance

`bashpip install plexapi`

## Configuration

Create a plex_account.ini file in the same folder as the scripts:

```
login = your@email.com
password = yourpassword
server = YourServerName
```

The server name should match exactly what appears in your Plex interface.

## Usage
### Import m3u to Plex

**Single playlist**
`python m3u_to_plex.py /path/to/playlist.m3u`

**Entire folder of playlists**
`python m3u_to_plex.py /path/to/playlists/`

**Dry run - match tracks without creating playlists**
`python m3u_to_plex.py -v -p /path/to/playlist.m3u`

**Replace existing playlist if m3u has changed**
`python m3u_to_plex.py -r /path/to/playlist.m3u`

### Export Plex to m3u

**List all Plex audio playlists**
`python plex_to_m3u.py -l`

**Export a single playlist**
`python plex_to_m3u.py "My Playlist"`

**Export to a specific folder**
`python plex_to_m3u.py "My Playlist" -o /path/to/output/`

**Export all playlists**
`python plex_to_m3u.py -o /path/to/output/`

## Flags (m3u_to_plex.py)

* `-v` (--verbose): Detailed output including match counts
* `-d` (--debug): Debug output including raw path comparisons
* `-r` (--replace): Delete and recreate playlist if m3u has changed
* `-p` (--pretend): Dry run, do not create playlists

# Notes

* The playlist name in Plex is taken from the m3u filename

* Brute force matching scans your entire Plex library and can be slow on large collections — a library of 50,000+ tracks may take several minutes to load

* The status_db file tracks fingerprints of processed playlists to skip unchanged ones on reruns

* Paths in your m3u files must be accessible from the machine running the script

# Credits
Originally based on a script by yarnairb. Improvements include bare m3u support, Unicode/mojibake fixes, a trailing comma bug fix in path comparison, and the companion export script.

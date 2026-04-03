import configparser
from plexapi.myplex import MyPlexAccount

config = configparser.ConfigParser()
config.read('plex_account.ini')
account = MyPlexAccount(config['PLEX']['login'], config['PLEX']['password'])
plex = account.resource(config['PLEX']['server']).connect()

tracks = plex.library.section('Music').search(libtype='track', limit=5)
for t in tracks:
    print(t.media[0].parts[0].file)
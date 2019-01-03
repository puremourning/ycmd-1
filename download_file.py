import build # This is build.py
import argparse

parser = argparse.ArgumentParser()
parser.add_argument( '--url', action = 'store', help='Url to download' )
parser.add_argument( '--dest', action = 'store', help='Where to save it' )
args = parser.parse_args()

print( "Downloading {} to {}".format( args.url, args.dest ) )
build.DownloadFileTo( args.url, args.dest )

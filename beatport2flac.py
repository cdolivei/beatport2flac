# vim: set expandtab tabstop=4 shiftwidth=4: 

# "THE BEER-WARE LICENSE" (Revision 42):
# <a.sacred.line+beatport@gmail.com> wrote this file. As long as you retain
# this notice you can do whatever you want with this stuff. If we meet some day,
# and you think this stuff is worth it, you can buy me a beer in return
# Cesar Oliveira

# beatport2flac requires flac executable to be in the PATH
# as well as the additional libraries:
#       metagen - http://code.google.com/p/mutagen/

from mutagen.flac import FLAC
import json
import urllib
import subprocess
import sys
import os
import re
import tempfile
import stat

def log(message) :
    print message

def extract_id(filename):
    """
    Get the id of the track from the audio file
    """
    matches = re.match("(\d+)_.+?.wav", filename)

    assert matches != None, \
           "Format of file %s does not match expected format of Beatport downloads" % filename

    # group 0 is the full match
    return matches.group(1)

def generate_beatport_url(id):
    return "http://api.beatport.com/catalog/tracks?format=json&v=1.0&id=%s" % id

# Makes a call to Beatport and returns a python dictionary of the metadata we
# need. This dictionary will be in the following format
# {
#   artists
#   track_name
#   remix_name
#   genre
#   release
#   date        - (year, month, day) tuple
#   album_url   - album artwork, 500x500 jpg
# }
def beatport_api(id):
    url = generate_beatport_url(id)
    data = dict()

    request = urllib.urlopen(url)
    response = request.read()

    obj = json.loads(response)

    assert 'results' in obj, \
           "Beatport returned an object we were not expecting"
    assert len(obj['results']) == 1, \
           "Beatport returned %d items instead of 1" %  len(obj['results'])

    result = obj['results'][0]
    assert 'mixName' in result, \
           "Mix name not found in this track"
    assert 'name' in result, \
           "Name of track not found in the API"
    assert 'genres' in result and len(result['genres']) > 0, \
           "No genres found in this track"
    assert 'release' in result, \
           "Could not find release for this track"
    assert 'releaseDate' in result, \
           "Could not find the track's release date"
    assert 'images' in result, \
           "Could not find album artwork"
    assert 'artists' in result, \
           "Could not find track artists"

    data['track_name'] = result['name']
    data['remix_name'] = result['mixName']
    data['genre'] = result['genres'][0]['name']
    data['release'] = result['release']['name']
    data['date'] = result['releaseDate'].split('-', 2)

    if 'large' in result['images'] :
        data['album_url'] = result['images']['large']['url']
    else :
        data['album_url'] = None
    """
    # medium and small album art look like garbage on the iAudio 9. Don't even bother
    elif 'medium' in result['images'] :
            data['album_url'] = result['images']['medium']['url']
    elif 'small' in result['images'] :
            data['album_url'] = result['images']['small']['url']
    """

    artists = map(lambda artist: artist['name'],
                  filter(lambda artist : artist['type'] == 'Artist',
                         result['artists']))

    if len(artists) == 1:
        data['artist'] = artists[0]
    elif len(artists) > 1:
        data['artist'] = ', '.join(artists[0:-1]) + ' and ' + artists[-1]

    return data

# returns path to album artwork. Caller is responsible for deleteing
# temporary file
def download_album_artwork(url):
    temp = tempfile.mkstemp(prefix="jpg")
    fd = open(temp[1], "wb")

    request = urllib.urlopen(url)
    response = request.read()

    fd.write(response)
    fd.close()
    return temp[1]

def usage(name):
    print "%s - A beatport wav to flac converter" % name
    print "\tUsage: %s filename1 [ filename2 ... ]" % name
    print "\tExample: %s 12345_sometitle.wav 67890_othertitle.wav" % name

if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage(sys.argv[0])
        sys.exit(0)

    # skip the calling script
    arguments = sys.argv[1:]

    for filename in arguments:
        try:
            log("Inspecting %s" % (filename))
            assert os.path.exists(filename), "File not found: %s" % (filename) 

            id = extract_id(filename)
            log("Retrieved id %s" % (id))

            log("Connecting to beatport to retrieve metadata")
            metadata = beatport_api(id)
            print metadata

            process = None
            artwork = None
            if metadata['album_url'] != None :
                log("Downloading album artwork")
                artwork = download_album_artwork(metadata['album_url'])

                process = subprocess.Popen(['flac',
                                            '-V',
                                            '--picture=|image/jpeg|||%s' % artwork,
                                            filename ])
            else :
                process = subprocess.Popen([ 'flac', '-V', filename ])
            process.wait()
            if artwork != None:
                os.remove(artwork)
            assert process.returncode == 0, \
                   "flac command did not execute successfully"

            flac_file = filename.replace('.wav', '.flac')
            assert os.path.exists(flac_file), \
                   "%s file was not converted to %s" % (filename, flac_file)

            os.chmod(flac_file,
                     stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)

            audio = FLAC(flac_file)
            audio['title'] = "%s (%s)" % (metadata['track_name'],
                                          metadata['remix_name'])
            audio['artist'] = metadata['artist']
            audio['album'] = metadata['release']
            audio['date'] = metadata['date'][0]
            audio['genre'] = metadata['genre']

            log(audio.pprint())

            audio.save()
        except AssertionError as exception:
            print exception

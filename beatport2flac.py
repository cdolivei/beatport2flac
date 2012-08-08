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
from pprint import pprint
import json
import urllib
import subprocess
import sys
import os
import re
import tempfile
import stat

class MissingMetadataError(Exception):
    def __init__(self, value):
        self.message = value
    def __str__(self):
        return repr(self.message)


def log(message) :
    print message

def extract_id(filename):
    """
    Get the id of the track from the audio file
    """
    matches = re.match("(\d+)_.+?.wav", os.path.basename(filename))

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
#   mix_name
#   genre
#   release
#   release_date - (year, month, day) tuple
#   album_url    - album artwork, 500x500 jpg
# }
def beatport_api(id):
    url = generate_beatport_url(id)
    data = dict()
    emptyd = dict() # empty dictionary

    request = urllib.urlopen(url)
    response = request.read()

    obj = json.loads(response)

    assert 'results' in obj, \
           "Beatport returned an object we were not expecting"
    assert len(obj['results']) == 1, \
           "Beatport returned %d items instead of 1" %  len(obj['results'])

    result = obj['results'][0]
    data['track_name'] = result.get('name', None)
    data['mix_name'] = result.get('mixName', None)
    data['genre'] = next(iter(result.get('genres', list())),
                         emptyd).get('name', None)
    data['release'] = result.get('release', emptyd).get('name', None)
    data['release_date'] = result.get('releaseDate', None)

    missing_data = filter(lambda key: data[key] == None, data.keys())
    if len(missing_data) > 0:
        raise MissingMetadataError(', '.join(map(lambda x : x.replace('_', ' ')
                                                             .capitalize(),
                                                 missing_data)))

    data['release_date'] = data['release_date'].split('-', 2)

    # medium and small album art look like garbage on the iAudio 9. Don't even bother
    data['album_url'] = result.get('images', emptyd) \
                              .get('large', emptyd) \
                              .get('url', None)

    artists = map(lambda artist: artist['name'],
                  filter(lambda artist : artist['type'].lower() == 'artist',
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

    try :
        request = urllib.urlopen(url)
        response = request.read()

        fd.write(response)
    except :
        pass
    finally :
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
        artwork = None
        try:
            log("Inspecting %s" % (filename))
            assert os.path.exists(filename), "File not found: %s" % (filename) 

            id = extract_id(filename)
            log("Retrieved id %s" % (id))

            log("Connecting to beatport to retrieve metadata")
            metadata = beatport_api(id)
            pprint(metadata)

            process = None
            if metadata.get('album_url', None) != None :
                log("Downloading album artwork")
                artwork = download_album_artwork(metadata['album_url'])

                process = subprocess.Popen(['flac',
                                            '-V',
                                            '--picture=|image/jpeg|||%s' % artwork,
                                            filename ])
            else :
                process = subprocess.Popen([ 'flac', '-V', filename ])
            process.wait()
            assert process.returncode == 0, \
                   "flac command did not execute successfully"

            flac_file = filename.replace('.wav', '.flac')
            assert os.path.exists(flac_file), \
                   "%s file was not converted to %s" % (filename, flac_file)

            os.chmod(flac_file,
                     stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)

            audio = FLAC(flac_file)
            audio['title'] = "%s (%s)" % (metadata['track_name'],
                                          metadata['mix_name'])
            audio['artist'] = metadata['artist']
            audio['album'] = metadata['release']
            audio['date'] = metadata['release_date'][0]
            audio['genre'] = metadata['genre']

            log(audio.pprint())

            audio.save()
        except MissingMetadataError as exception :
            log("Could not find (or missing) track information: %s. Skipping" %
                exception.message)
        except AssertionError as exception :
            log(exception)
        except Exception as exception :
            log("Hey you found a bug! Bugs really suck, I'm sorry.\r\n"\
                "We have to skip this file, but you can file an issue at\r\n"\
                "https://github.com/cdolivei/beatport2flac/issues\r\n"
                "with the track name and this message : %s" % repr(exception))
        finally:
            if artwork != None:
                os.remove(artwork)


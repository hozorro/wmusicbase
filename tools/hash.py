import re, json
from enum import Enum

def parse_cue_to_json(cue_content: str) -> dict:
    '''
    parse cue content to json format
    
    :param cue_content: cue content, string
    :return: dict of cue content, dict
    '''
    # init result
    result = {
        'album_info': {},
        'tracks': []
    }
    # parse album info
    album_patterns = {
        'PERFORMER': r"^PERFORMER\s+(.+)$",
        'TITLE': r"^TITLE\s+(.+)$",
        'MUSICBRAINZ_ALBUM_ID': r"^REM\s+MUSICBRAINZ_ALBUM_ID\s+(.+)$",
        'MUSICBRAINZ_ALBUM_ARTIST_ID': r"^REM\s+MUSICBRAINZ_ALBUMARTISTID\s+(.+)$",
        'DATE': r"^REM\s+DATE\s+(.+)$",
    }
    for line in cue_content.split('\n'):
        line = line.strip()
        for key, pattern in album_patterns.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1).strip().strip('"').strip("'")
                result['album_info'][key] = value
        if re.match(r"^\s*TRACK\s+\d+\s+AUDIO", line):
            break

    track_sections = re.split(r"(?=\s*TRACK\s+\d+\s+AUDIO)", cue_content)
    cur_file = ''

    for section in track_sections:
        section = section.strip()
        if not section: continue

        track_id_match = re.search(r"\s*TRACK\s+(\d+)\s+AUDIO", section, re.IGNORECASE)
        performer_match = re.search(r"\s*PERFORMER\s+(.+?)$", section, re.MULTILINE | re.IGNORECASE)
        title_match = re.search(r"\s*TITLE\s+(.+?)$", section, re.MULTILINE | re.IGNORECASE)
        mb_track_id_match = re.search(r"\s*REM\s+MUSICBRAINZ_TRACK_ID\s+(\S+?)$", section, re.MULTILINE | re.IGNORECASE)
        mb_artist_id_match = re.search(r"\s*REM\s+MUSICBRAINZ_ARTIST_ID\s+(\S+?)$", section, re.MULTILINE | re.IGNORECASE)
        file_match = re.search(r"\s*FILE\s+(.+?)\s+MP3$", section, re.MULTILINE | re.IGNORECASE)

        if track_id_match:
            track_data = {
                'TRACK_ID': track_id_match.group(1).zfill(2),
                'PERFORMER': performer_match.group(1).strip().strip('"').strip("'") if performer_match else '',
                'TITLE': title_match.group(1).strip().strip('"').strip("'") if title_match else '',
                'MUSICBRAINZ_TRACK_ID': mb_track_id_match.group(1).strip() if mb_track_id_match else '',
                'MUSICBRAINZ_ARTIST_ID': mb_artist_id_match.group(1).strip() if mb_artist_id_match else '',
                'FILE': file_match.group(1).strip().strip('"').strip("'") if file_match else ''
            }
            result['tracks'].append(track_data)
    return result

def parse_cue_file(cue_file_path: str) -> dict:
    with open(cue_file_path, 'r', encoding='utf-8') as f:
        cue_content = f.read()
    result = parse_cue_to_json(cue_content)
    print(json.dumps(result, indent=2, ensure_ascii=False))

class ArtType(str, Enum):
    ALBUM = 'album'
    ARTIST = 'artist'
    TRACK = 'track'

def get_art(art_type: ArtType):
    print(art_type)

if __name__ == '__main__':
    # cue_file_path = r'D:\tmp\testmusiclib\Chinese\A-G\A-Lin\Love Song（出道十周年情歌精选）\traklist.cue'
    # file1 = r"D:\tmp\testmusiclib\Foreign\U-Z\Various Artists\Now That's What I Call 40 Years_ Volume 1 1983-1993\2-12 Teardrops.flac"
    # from app.utils.metadata import easy_metadata
    # meta = easy_metadata(file1)
    # print(meta)
    # get_art(ArtType.TRACK.value)
    from app.core.config import settings
    count = 0
    for f in settings.MUSIC_LIBRARY_PATH.rglob('*.flac'):
        count += 1
    print(count)
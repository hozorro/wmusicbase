# -*- encoding: utf-8 -*-
'''
@File      :   aidmatch.py
@Time      :   2025/11/13 09:19:43
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   fingerprint tools
'''


import acoustid
from app.core.config import settings

META = ['recordings', 'releases', 'compress']

def generate_fingerprint(file_path, force_fpcalc=False):
    try:
        duration, fp = acoustid.fingerprint_file(file_path, force_fpcalc=force_fpcalc)
    except acoustid.NoBackendError:
        print('No acoustid lib/tool available')
        raise RuntimeError('No acoustid lib/tool available')
    except acoustid.FingerprintGenerationError:
        print('Fingerprint generation failed')
        raise RuntimeError('Fingerprint generation failed')
    return duration, fp

def _parse_result(data):
    if data['status'] != 'ok':
        raise RuntimeError('Acoustid error')
    if 'results' not in data:
        raise RuntimeError('No results')
    
    parsed = []
    for result in data['results']:
        acoustid_id = result.get('id')
        score = result['score']
        if 'recordings' not in result: continue # no recording, the result is not useful#
        
        for recording in result['recordings']:
            id = recording.get('id', '')
            title = recording.get('title', '')
            duration = recording.get('duration', 0)
            artists = []
            recording_artists = recording.get('artists')
            if recording_artists:
                artists = [{'id': a.get('id', ''), 'name': a.get('name', '')} for a in recording_artists]

            releases = recording.get('releases')
            if releases:
                for release in releases:
                    rid = release.get('id', '')
                    rtitle = release.get('title', '')
                    rcountry = release.get('country', '')

                    date = release.get('date')
                    if date:
                        year = date.get('year', 0)
                    ryear = year if year else ''
                    rtrackcount = release.get('track_count', 0)
                    
                    rartists = []
                    release_artists = release.get('artists')
                    if release_artists:
                        rartists = [{'id': a.get('id', ''), 'name': a.get('name', '')} for a in release_artists]
                    else:
                        rartists = artists
                    
                    parsed.append({
                        'acoustid_id': acoustid_id,
                        'id': id,
                        'title': title,
                        'duration': duration,
                        'artists': artists,
                        'release_id': rid,
                        'release_title': rtitle,
                        'release_year': ryear,
                        'release_artists': rartists,
                        'release_country': rcountry,
                        'release_track_count': rtrackcount,
                        'score': score
                    })
    parsed.sort(key=lambda x: x['score'], reverse=True)
    return parsed
def match_fingerprint(duration, fp, meta=META, timeout=None):
    try:
        response = acoustid.lookup(settings.ACOUSTID_API_KEY, fp, duration, meta, timeout)
    except acoustid.WebServiceError:
        print('Acoustid webservice error')
        raise RuntimeError('Acoustid webservice error')
    
    return _parse_result(response)
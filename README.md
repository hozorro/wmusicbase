# Introduction
WMusicbase is a personal musicbase api backend. Through the request from frontend(player and manager), it can:
- Scan music files from music library and analyze meta data to the database. Support mp3 file with ID3v1, ID3v2, and flac files, with enforced decoding function.
- Analyze or extract artwork of all the artists, albums and tracks and generate artwork cache at one time.
- Organize music with artist, album, genre, folder and playlist. The artists and genres of a certain track is analyzed as list and organized one by one.
- Streaming files to the frontend PWA player.
- Supply lyrics to the forntend PWA player(request from 3rd part function).
- Upload, stage and archive music files to the music library from frontend web page.
- Edit track meta data and cover art from the frontend web page.
- Backup and restore playback data(playlists, hits, favs).

The project is the backend of and used together with [wmusicplayer](https://github.com/hozorro/wmusicplayer) and [wmusicman](https://github.com/hozorro/wmusicman).

# Installation
* pull the repo
```bash
git clone git@github.com:hozorro/wmusicbase.git
cd wmusicbase
```
* install dependencies
`uv sync`
* install chromaprint
  * If you do not use chromaprint to generate fingerprint of audio files to match musicbrainz info, you can skip this step.
  * Chromaprint is a library for fingerprinting audio files. There are two ways to use chromaprint:
    * make the chromaprint dynamic library from [source code](https://github.com/acoustid/chromaprint)
    * the [fpcalc command-line tool](https://github.com/acoustid/chromaprint/releases). If you use fpcalc, either ensure that it is on your $PATH or set the FPCALC environment variable to its location.
* create database(postgresql)
* create or edit .env(copy from .env.example)
* initialization:
```bash
uv run init-dirs
uv run init-db
```

# Deployment
## dev or test
```bash
uv run uvicorn app.main:app --reload      # run main app
uv run python -m app.background.watcher   # run watcher
```

## run by supervisor (recomended)
- create supervisor conf file in `/etc/supervisor/conf.d/`(copy from template in `deploy` dir of this proj).
- run:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start wmusicbase:* # restart main app and watcher at the same time
```

## nginx proxy api service for frontend
- create nginx conf file(copy from template in `deploy` dir of this proj, including frontend configure).
- run:
```bash
sudo nginx -t
sudo nginx -s reload
```

## Update
* pull the repo
```bash
git pull
uv sync         # if pyproject.toml changed
uv run init-db  # if alembic version changed
sudo supervisorctl restart wmusicbase:* # restart main app and watcher at the same time
```

## Docker depolyment
An umbrella repository is recomended, look up [wmusic-suite](https://github.com/hozorro/wmusic-suite).

# Additional
## About database
- Only PostgreSQL supported, if use sqlite, modify the relevant code.

## About music library directory structure
- Most of the project features including scanning process and music database etc. **are unconcerned with** the music library directory struction.
- If you upload/archive music files directly to the music library directory, the music library directory structure is also **unconcerned**.
- But when you upload music files, stage then archive them to the music library directory from web page of wmusicman(music management frontend), a normal structure used:
```plaintext
(Chinese or Foreign)
  └── (first alpherbit range of artist name, A-G, H-N, O-T, U-Z, Z_)
        └── (artist name) 
              └── (album title)
                    └── (track file)
```
- That means when you archive music files, some dirs will be made automatically with track file like the structure.
- If you don't want that, modify the relevant file-archive code.

## About authentication
- The user run this project should have authentication to read and write music library directory and media root directory.
- The nginx user(www-data) should have authentication to read music library directory and media root directory.

# WMusicbase
WMusicbase is a personal musicbase system.

## Installation
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

* create or edit .env(see .env.example)

* initialization
```bash
uv run init-dirs
uv run init-db
```
* run
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start wmusicbase

sudo systemctl restart nginx
```

## Update
* pull the repo
```bash
git pull
uv sync
uv run init-db
sudo supervisorctl restart wmusicbase
```

## Additional
### Gunicorn
* Install gunicorn: 
  * if use gunicorn only in this project, you can use edit `pyproject.toml` and add "gunicorn>=23,<26".
  * if use gunicorn in other projects on the server, you can run `sudo apt install gunicorn`.[wrong: even if you install gunicorn in the global environment, you still need to install gunicorn in the project venv. because even if you set PATH env in the supervisor configuration file, it will not work.]
### Supervisor
* Install supervisor: `sudo apt install supervisor`
* Create a configuration file: `sudo nano /etc/supervisor/conf.d/wmusicbase.conf`
suppose the project is in `/srv/wmusicbase`, the configuration file is as follows:
```
[program:wmusicbase]
directory=/srv/wmusicbase
; if you use more than one worker, you should use redis to share system state
command=/srv/wmusicbase/.venv/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 1 -b 127.0.0.1:8000
user=www-data ; user, change to your user
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/srv/wmusicbase/logs/supervisor_stdout.log
stderr_logfile=/srv/wmusicbase/logs/supervisor_stderr.log
```
### Nginx
* Install nginx: `sudo apt install nginx`
* Create a configuration file: `sudo nano /etc/nginx/sites-available/wmusicbase`
suppose the project is in `/srv/wmusicbase`, the configuration file is as follows:
```
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }
}
```
### uv
uv is a simple tool to manage virtual environments and project dependencies.
* Install uv: 
  * Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  * Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
### About www-data
  * Since www-data is ususally used for web service processes such as nginx, apache etc., you can use it to run your project.
  * Therefore, you need to config the authentication of www-data.
  ```bash
  sudo chown -R youruser:www-data /srv/wmusicbase
  sudo find /srv/wmusicbase -type d -exec chmod 750 {} \;
  sudo find /srv/wmusicbase -type f -exec chmod 640 {} \;
  sudo chmod -R 770 /srv/wmusicbase/media
  sudo chmod -R 770 /srv/wmusicbase/logs
  ```

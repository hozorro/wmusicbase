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
  * if use gunicorn only in this project, you can use edit `pyproject.toml` and add "gunicorn>=21,<22".
  * if use gunicorn in other projects on the server, you can run `sudo apt install gunicorn`.
### Supervisor
* Install supervisor: `sudo apt install supervisor`
* Create a configuration file: `sudo nano /etc/supervisor/conf.d/wmusicbase.conf`
suppose the project is in `/srv/wmusicbase`, the configuration file is as follows:
```
[program:wmusicbase]
directory=/srv/wmusicbase
command=/usr/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 127.0.0.1:8000
; if you install gunicorn in the venv, you can use this command
; command=/srv/wmusicbase/.venv/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 127.0.0.1:8000
user=www-data ; user, change to your user
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/srv/wmusicbase/logs/supervisor_stdout.log
stderr_logfile=/srv/wmusicbase/logs/supervisor_stderr.log
environment=
    PATH="/srv/wmusicbase/.venv/bin:/usr/local/bin:/usr/bin",
    PYTHONPATH="/srv/wmusicbase"
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
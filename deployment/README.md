# Production deployment

This project deploys `main.py` as a systemd service behind Nginx. Each release
is placed in `/opt/qq-rpg/releases`, and `/opt/qq-rpg/current` points at the
active one. A failed restart or health check automatically restores the prior
release.

## One-time Ubuntu setup

Run the following as `root`. Replace `DEPLOY_PUBLIC_KEY` with the public key
created specifically for GitHub Actions; never use a personal key or password
in repository files.

```bash
apt update
apt install -y python3-venv python3-pip nginx rsync curl
useradd --system --create-home --shell /usr/sbin/nologin qqbot
useradd --create-home --shell /bin/bash deploy
install -d -o deploy -g deploy /opt/qq-rpg/releases /opt/qq-rpg/incoming /opt/qq-rpg/shared/logs
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
printf '%s\n' 'DEPLOY_PUBLIC_KEY' > /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
```

Create `/etc/sudoers.d/qq-rpg-deploy` with `visudo -f /etc/sudoers.d/qq-rpg-deploy`:

```sudoers
deploy ALL=(root) NOPASSWD: /bin/systemctl restart qq-rpg.service
```

Copy `qq-rpg.service` to `/etc/systemd/system/qq-rpg.service`, then create
`/etc/qq-rpg/qq-rpg.env` from `.env.example`. It must contain the real QQ,
database, and administrator values and be protected with `chmod 600`.

Keep `GM_STATE_FILE=/opt/qq-rpg/shared/logs/gm_state.yaml` (or set another
absolute path writable by `qqbot`). This YAML preserves verified GM UIDs and
the global image mode across service restarts and release switches.

```bash
install -d -m 700 /etc/qq-rpg
install -m 600 /dev/null /etc/qq-rpg/qq-rpg.env
systemctl daemon-reload
systemctl enable qq-rpg.service
```

Copy `nginx-qq-rpg.conf` to `/etc/nginx/sites-available/qq-rpg`, replace
`YOUR_DOMAIN`, configure its certificate paths, and enable it:

```bash
ln -s /etc/nginx/sites-available/qq-rpg /etc/nginx/sites-enabled/qq-rpg
nginx -t && systemctl reload nginx
```

## GitHub Actions secrets

Add these repository secrets before pushing `main`:

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | Server IP or hostname |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_PORT` | `22` (or your changed SSH port) |
| `DEPLOY_SSH_PRIVATE_KEY` | Dedicated private ED25519 deployment key |

## Rollback

Log in as `deploy`, list releases, and activate the desired version:

```bash
find /opt/qq-rpg/releases -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r
bash /opt/qq-rpg/current/deployment/rollback.sh
# or: bash /opt/qq-rpg/current/deployment/rollback.sh 20260726120000-abcdef0
```

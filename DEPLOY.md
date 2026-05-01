# Bridge Dashboard Deployment Notes

## Live site

- URL: `https://bridgeenergydash.home.kg/`
- Public IP: `132.145.208.19`
- Host: Oracle Cloud VM

## How it works

- GitHub stores the code.
- Oracle Cloud runs the live website.
- `nginx` handles public web traffic and HTTPS.
- `nginx` forwards requests to the FastAPI app running on `127.0.0.1:8000`.
- The app runs as the `bridge-dashboard` systemd service.

## Normal update flow

This project is set up for auto-deploy.

1. Make a change.
2. Push to GitHub `main`.
3. GitHub sends a webhook to the server.
4. The server pulls the latest code and restarts the app.
5. The live website updates.

Important: pushing to a separate branch should not update the live site. Only `main` should deploy.

## Auto-deploy pieces

- Webhook endpoint: `POST /webhook/github`
- Deploy script: `deploy-webhook.sh`
- Deploy branch: `refs/heads/main`

The deploy script does 4 things:

1. Goes to the app folder on the VM
2. Fetches the latest code from GitHub
3. Pulls the latest `main`
4. Restarts `bridge-dashboard`

## Important VM paths

- App folder: `/home/ubuntu/bridge-dashboard`
- Python virtual environment: `/home/ubuntu/bridge-dashboard/.venv`
- Service file: `/etc/systemd/system/bridge-dashboard.service`
- Nginx config: `/etc/nginx/sites-available/bridge-dashboard`
- TLS certs: `/etc/letsencrypt/live/bridgeenergydash.home.kg/`

## If the website goes down

SSH into the Oracle VM, then check these in order:

### 1. App status

```bash
sudo systemctl status bridge-dashboard --no-pager
sudo systemctl restart bridge-dashboard
```

### 2. Nginx status

```bash
sudo systemctl status nginx --no-pager
sudo systemctl restart nginx
```

### 3. Local app test on the server

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/docs
```

### 4. Public site test

```bash
curl -I https://bridgeenergydash.home.kg/
```

## If GitHub deploy stops working

Check these:

- GitHub webhook is still active
- Webhook secret matches the server setting
- The server repo can still access GitHub
- `deploy-webhook.sh` still exists and is executable
- The service user can still restart `bridge-dashboard`

## If `git pull` fails on the VM

Check the repo remote:

```bash
cd ~/bridge-dashboard
git remote -v
```

If needed, switch the VM repo to GitHub SSH:

```bash
git remote set-url origin git@github.com:YOUR_GITHUB_USERNAME/bridge-dashboard.git
ssh -T git@github.com
```

## If Python dependencies change

```bash
cd ~/bridge-dashboard
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart bridge-dashboard
```

## If `.venv` is missing

```bash
cd ~/bridge-dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
sudo systemctl restart bridge-dashboard
```

## Notes

- You do not need to keep Cloud Shell open for the site to stay up.
- Oracle access controls the server.
- SSH access lets someone log in and repair or restart the app.
- DNS access controls the public website address.

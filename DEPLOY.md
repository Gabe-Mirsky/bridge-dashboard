# Bridge Dashboard Deployment Runbook

This document is the working deployment guide for the live Bridge Dashboard.

## Live site

- Production URL: `https://bridgeenergydash.home.kg/`
- HTTP URL: `http://bridgeenergydash.home.kg/`
- Reserved public IP: `132.145.208.19`

## Hosting setup

- Host: Oracle Cloud VM
- VM user: `ubuntu`
- App directory on VM: `/home/ubuntu/bridge-dashboard`
- Python app entrypoint: `server.py`
- App service name: `bridge-dashboard`
- Reverse proxy: `nginx`
- TLS: `certbot` / Let's Encrypt

## Current architecture

1. `nginx` listens on ports `80` and `443`
2. `nginx` proxies requests to FastAPI on `127.0.0.1:8000`
3. FastAPI is started by `systemd` using the `bridge-dashboard` service
4. DNS for `bridgeenergydash.home.kg` points to `132.145.208.19`

## Simplest deploy model

Use these 3 pieces:

1. GitHub is the editing place
2. GitHub sends a webhook on commit
3. The server deploys automatically by pulling latest code and restarting the app

That removes the need for coworkers to SSH into the VM, remember commands, or restart services manually.

## Automatic deploy setup

The repo now includes:

- FastAPI webhook endpoint: `POST /webhook/github`
- Deploy script: `deploy-webhook.sh`

### Part 1: Configure environment variables for the app service

Add these environment variables to the `bridge-dashboard` systemd service or another secure environment file loaded by that service:

```bash
GITHUB_WEBHOOK_SECRET=choose-a-long-random-secret
DEPLOY_BRANCH=refs/heads/main
DEPLOY_SCRIPT_PATH=/home/ubuntu/bridge-dashboard/deploy-webhook.sh
```

After updating the service definition:

```bash
sudo systemctl daemon-reload
sudo systemctl restart bridge-dashboard
```

### Part 2: Install and test the deploy script on the VM

On the VM:

```bash
cd /home/ubuntu/bridge-dashboard
chmod +x deploy-webhook.sh
```

The script is intentionally small. It does:

```bash
cd /home/ubuntu/bridge-dashboard
git fetch origin main
git checkout main
git pull --ff-only origin main
sudo systemctl restart bridge-dashboard
```

### Part 3: Allow only the restart command in sudoers

The FastAPI service user usually cannot restart systemd services unless you allow that exact command.

Recommended approach:

1. Open sudoers safely:

```bash
sudo visudo
```

2. Add a narrow rule for the service user. Example for user `ubuntu`:

```bash
ubuntu ALL=NOPASSWD: /usr/bin/systemctl restart bridge-dashboard
```

Do not grant broad sudo access. Allow only the specific restart command needed by the deploy script.

### Part 4: Add the webhook in GitHub

In the GitHub repo:

1. Go to `Settings -> Webhooks -> Add webhook`
2. Set `Payload URL` to:

```text
https://bridgeenergydash.home.kg/webhook/github
```

3. Set `Content type` to `application/json`
4. Set `Secret` to the same value as `GITHUB_WEBHOOK_SECRET`
5. Choose `Just the push event`
6. Save

### Deployment flow after setup

1. Coworker edits in GitHub
2. Coworker clicks Commit
3. GitHub sends a signed push webhook
4. FastAPI verifies the signature
5. FastAPI runs `deploy-webhook.sh`
6. The server pulls latest code and restarts `bridge-dashboard`

### Quick manual webhook checks

GitHub should send a `ping` event when the webhook is first created.

- If the secret is wrong, the endpoint returns `401`
- If the push is for a different branch, the endpoint returns `ignored`
- If the deploy script fails, the endpoint returns `500`

### Important limitation

This webhook path can only complete a deployment if:

- the VM repo already has working GitHub access
- the service user can execute the deploy script
- sudoers allows restarting only the `bridge-dashboard` service

## One-time GitHub SSH setup on the VM

Use this once so the VM can run `git pull` without asking for a username or token.

### 1. SSH into the VM

From Oracle Cloud Shell:

```bash
ssh -i ~/ssh-key-2026-03-06.key ubuntu@132.145.208.19
```

### 2. Generate a GitHub SSH key on the VM

```bash
ssh-keygen -t ed25519 -C "bridge-dashboard-vm"
```

When prompted:

- Press `Enter` to accept the default path
- Press `Enter` again for no passphrase

### 3. Print the public key

```bash
cat ~/.ssh/id_ed25519.pub
```

### 4. Add that key to GitHub

In GitHub:

- Go to `Settings -> SSH and GPG keys`
- Click `New SSH key`
- Title: `bridge-dashboard-vm`
- Paste the full public key
- Save

### 5. Test GitHub SSH access from the VM

```bash
ssh -T git@github.com
```

The first time, type `yes` to trust GitHub.

You should get a success message mentioning your GitHub username.

### 6. Point the repo at the SSH remote

In the VM project directory:

```bash
cd ~/bridge-dashboard
git remote -v
git remote set-url origin git@github.com:YOUR_GITHUB_USERNAME/bridge-dashboard.git
git remote -v
```

After this, `git pull` will use SSH instead of HTTPS.

## Normal update process

Use this when the site is already running and you only want to publish code changes.

### Step 1: Update code locally

Edit the local project files in:

`C:\Users\GabeMirsky-BridgeEne\Downloads\Python\Bridge_Dashboard Project`

### Step 2: Push changes to GitHub

Push the updated files to the GitHub repo for this project.

### Step 3: SSH into the Oracle VM

From Oracle Cloud Shell:

```bash
ssh -i ~/ssh-key-2026-03-06.key ubuntu@132.145.208.19
```

### Step 4: Pull the latest code on the VM

```bash
cd ~/bridge-dashboard
git pull
```

Important:

- `git pull` is safe and keeps the existing `.venv`
- a fresh `git clone` into a new `~/bridge-dashboard` folder does **not** include `.venv`
- if `.venv` is missing, the site will fail and Nginx will show `502 Bad Gateway`

### Step 5: Restart the app

```bash
sudo systemctl restart bridge-dashboard
sudo systemctl status bridge-dashboard --no-pager
```

### Step 6: Verify the site

Open:

- `https://bridgeenergydash.home.kg/`
- `https://bridgeenergydash.home.kg/docs`

Or test on the VM:

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/docs
```

## Fast manual fallback

Use this only if GitHub pull is not available or the repo on the VM is not set up correctly.

### From Cloud Shell

Upload changed files to your Cloud Shell home directory, then run:

```bash
bash ~/cloudshell-deploy.sh
```

This script copies the app files to the VM and restarts `bridge-dashboard`.

## Important service commands

### Check app status

```bash
sudo systemctl status bridge-dashboard --no-pager
```

### Restart app

```bash
sudo systemctl restart bridge-dashboard
```

### View recent app logs

```bash
sudo journalctl -u bridge-dashboard -n 100 --no-pager
```

### Check nginx status

```bash
sudo systemctl status nginx --no-pager
```

### Reload nginx after config change

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Important file locations on the VM

- App code: `/home/ubuntu/bridge-dashboard`
- Python virtualenv: `/home/ubuntu/bridge-dashboard/.venv`
- Systemd service: `/etc/systemd/system/bridge-dashboard.service`
- Nginx site config: `/etc/nginx/sites-available/bridge-dashboard`
- Enabled nginx site symlink: `/etc/nginx/sites-enabled/bridge-dashboard`
- TLS cert path: `/etc/letsencrypt/live/bridgeenergydash.home.kg/fullchain.pem`
- TLS key path: `/etc/letsencrypt/live/bridgeenergydash.home.kg/privkey.pem`

## If the website goes down

### 1. Check the app service

```bash
sudo systemctl status bridge-dashboard --no-pager
```

If it is not running:

```bash
sudo systemctl restart bridge-dashboard
```

### 2. Check nginx

```bash
sudo systemctl status nginx --no-pager
```

If needed:

```bash
sudo systemctl restart nginx
```

### 3. Check local app response on the VM

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/docs
```

### 4. Check public website response

From a browser or Cloud Shell:

```bash
curl -I https://bridgeenergydash.home.kg/
```

## If Git pull fails on the VM

Use the manual fallback:

1. Upload changed files to Cloud Shell
2. Run:

```bash
bash ~/cloudshell-deploy.sh
```

If the error mentions GitHub authentication:

1. Check the remote:

```bash
cd ~/bridge-dashboard
git remote -v
```

2. If it still shows an `https://` GitHub URL, switch it to SSH:

```bash
git remote set-url origin git@github.com:YOUR_GITHUB_USERNAME/bridge-dashboard.git
```

3. Test SSH auth:

```bash
ssh -T git@github.com
```

## If Python dependencies change

After `git pull`, run:

```bash
cd ~/bridge-dashboard
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart bridge-dashboard
```

## If `.venv` is missing

This usually happens if the app directory was replaced with a fresh `git clone`.

Symptoms:

- website shows `502 Bad Gateway`
- `curl http://127.0.0.1:8000/` fails
- `source .venv/bin/activate` says file not found

Recovery:

```bash
cd ~/bridge-dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
sudo systemctl restart bridge-dashboard
sudo systemctl status bridge-dashboard --no-pager
```

Verify locally on the VM:

```bash
curl http://127.0.0.1:8000/
```

## TLS / HTTPS renewal

Certbot auto-renew is installed already.

Check timer:

```bash
sudo systemctl status snap.certbot.renew.timer --no-pager
```

Manual renewal test:

```bash
sudo certbot renew --dry-run
```

## Notes

- You do not need to keep Cloud Shell open for the site to run.
- The site runs continuously because `bridge-dashboard` is managed by `systemd`.
- `nginx` handles the public web traffic and forwards it to FastAPI.

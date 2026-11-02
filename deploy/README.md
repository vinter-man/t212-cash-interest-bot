# Deploying

The bot runs as one container on a VPS next to other projects, under a `deploy` user that is in
the `docker` group and has no shell over SSH. Long polling needs no inbound port, so nothing is
published.

## Once, on the server

```bash
ssh root@YOUR_SERVER
install -d -o deploy -g deploy /srv/t212-cash-interest-bot
sudo -u deploy git clone https://github.com/vinter-man/t212-cash-interest-bot /srv/t212-cash-interest-bot
install -m 600 -o deploy -g deploy /dev/null /srv/t212-cash-interest-bot/.env
$EDITOR /srv/t212-cash-interest-bot/.env    # BOT_TOKEN=..., REGION=EU, OWNER_ID=... (see .env.example)
sudo -u deploy sh -c 'cd /srv/t212-cash-interest-bot && docker compose up -d --build'
```

Then a key that CI uses and that can do exactly one thing:

```bash
ssh-keygen -t ed25519 -N '' -C t212-cash-interest-bot-ci -f cash_interest_ci
# on the server, append to /home/deploy/.ssh/authorized_keys:
command="/srv/t212-cash-interest-bot/deploy/deploy.sh",no-agent-forwarding,no-port-forwarding,no-pty,no-user-rc,no-X11-forwarding ssh-ed25519 AAAA... t212-cash-interest-bot-ci
```

The forced command means a session with that key runs `deploy.sh` and exits, whatever the
client asks for; a leaked secret buys an attacker a redeploy of this repository's `main` and
nothing else.

## Repository secrets and variables

| Secret | What it is |
|---|---|
| `DEPLOY_HOST` | the server's address |
| `DEPLOY_SSH_KEY` | the private half of `cash_interest_ci` |
| `DEPLOY_HOST_KEY` | `ssh-keyscan -t ed25519 YOUR_SERVER`, pinned so the first connection cannot be intercepted |

| Variable | What it is |
|---|---|
| `DEPLOY_USER` | `deploy`: not a secret, and as one GitHub would mask the word in every log line |

## What a push to `main` does

CI runs ruff, mypy `--strict`, the tests with their coverage gates, shellcheck, and builds the
image and imports every module from it. Only when all of that is green does it SSH in with the
tested commit's sha. `deploy.sh` accepts that sha only if it is on `origin/main` and not behind
what is running, builds first (a broken build changes nothing), restarts, and waits for the
container's healthcheck: a heartbeat file a background task touches each minute after a
successful `getMe`, so "healthy" means the process is alive and reaches Telegram. Unhealthy after
a deploy that started from a healthy state means an automatic rollback to the previous commit.

`.env` and the `data` volume (the SQLite file: check history and subscriptions) are never touched
by a deploy. A restart does not poll the sources early either: the next poll is six hours after
the last one recorded in the database.

To deploy by hand: `ssh -i cash_interest_ci deploy@YOUR_SERVER` (or with a sha as the command).

## Feeding it a saved page

trading212.com answers anything that is not a browser with a bot check, and the bot does not
pretend to be one. To refresh the website's rates, open the page in a browser, save it
(`Save Page As…`, HTML), and send the file to the bot from the `OWNER_ID` account. It reads the
same JSON the live check would, records it as "a saved page sent" that day, and replies with
whatever differs from before. Subscribers are not alerted: the bot cannot tell how old the page is.

# linkedin_agent

A C++20 job that runs once a day. It collects the last 24 h of posts from people you follow
and the people who viewed your profile, then e-mails you a summary. If `ANTHROPIC_API_KEY`
is set, Claude adds a short digest of the day's themes.

> **Read first.** LinkedIn has no public API for your feed or for "who viewed my profile".
> This agent calls LinkedIn's internal web API (Voyager) with your own browser session.
> That breaks LinkedIn's User Agreement (section 8.2, automated access) and can get your
> account restricted. Run it only against your own account and keep the volume low (the
> defaults fetch at most 10 feed pages a day, with a 1.5 to 4 s pause between pages). The
> endpoints are undocumented and can change without notice.

## Pipeline

```
verify session (/me) ─► feed/updatesV2 (sortOrder=RECENT, paged until stale)
                     └► identity/wvmpCards (profile views)
        │
        ▼
parse ─► filter (posted_at ≥ now-24h, drop ads / "X liked this") ─► [Claude digest] ─► SMTP
```

- **Login.** You paste the session cookies (`li_at`, `JSESSIONID`) from a browser where you
  are already logged in. The agent never handles your password: LinkedIn challenges headless
  logins with a CAPTCHA or an e-mail PIN, and a stored password is a bigger risk than a
  cookie you can revoke. A `li_at` cookie lasts about a year. When it expires the agent exits
  with code `3`.
- **Freshness.** A post's age comes from its activity ID, not from the "5h" label shown in
  the feed. The ID is Snowflake-style, so `id >> 22` gives the creation time in ms since the
  Unix epoch.
- **"Profiles I follow".** These are the posts in your feed whose author you follow or are
  connected to. Sponsored posts are always dropped. Posts that appear only because someone in
  your network liked or commented on them are dropped too, unless you pass
  `--include-network-activity`.
- **Profile views.** Free accounts see only a few viewers by name. The rest are listed as
  "Private viewer".

## Build and test

```bash
sudo apt install libcurl4-openssl-dev nlohmann-json3-dev   # or: vcpkg install curl nlohmann-json
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j
ctest --test-dir build --output-on-failure

# offline dry run against the fixtures
./build/linkedin_agent --feed-json tests/fixtures/feed.json --views-json tests/fixtures/views.json \
    --now-ms 1790856000000 --dry-run --no-llm
```

## Run

```bash
cp deploy/linkedin-agent.env.example ~/.config/linkedin-agent.env && chmod 600 ~/.config/linkedin-agent.env
set -a; . ~/.config/linkedin-agent.env; set +a
./build/linkedin_agent --dry-run          # print to stdout first
./build/linkedin_agent                    # e-mail it
```

Schedule it with systemd (user units):

```bash
install -Dm755 build/linkedin_agent ~/.local/bin/linkedin_agent
cp deploy/linkedin-agent.{service,timer} ~/.config/systemd/user/
systemctl --user enable --now linkedin-agent.timer
```

or with cron: `45 7 * * * set -a; . ~/.config/linkedin-agent.env; ~/.local/bin/linkedin_agent`

| Flag | Default | Meaning |
| --- | --- | --- |
| `--hours N` | 24 | Freshness window |
| `--max-pages N` | 10 | Feed pages of 50 to fetch at most |
| `--include-network-activity` | off | Keep "X liked this" posts |
| `--no-llm` | off | Skip the Claude digest |
| `--dry-run` | off | Print instead of sending mail |

Exit codes: `0` ok, `1` error, `2` usage, `3` session expired.

## Layout

| File | Role |
| --- | --- |
| `src/linkedin.*` | Voyager client and pure parsers (`parse_feed`, `parse_profile_views`, `activity_time`) |
| `src/summarizer.*` | Claude Messages API call (`claude-opus-5-5`, server-side refusal fallback). Post text is passed as untrusted data |
| `src/mailer.*` | SMTP over TLS using libcurl |
| `src/report.*` | Plain-text e-mail rendering |
| `src/http.*` | RAII wrapper around libcurl |

Notes:

- The JSON parsers search the response for its fields instead of assuming fixed paths, so
  small schema changes on LinkedIn's side don't break them. The fixtures in `tests/fixtures`
  are synthetic. If LinkedIn changes a response shape, save a real response with
  `--feed-json` or `--views-json` to reproduce the problem offline.
- The Claude digest is best-effort. If the API call fails or the request is refused, the
  e-mail still goes out with the plain post list.

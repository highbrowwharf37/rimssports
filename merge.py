import json, datetime, os, subprocess, sys, time, urllib.request, urllib.parse

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://barttorvik.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}


def fetch_json(url, attempts=4):
    last_err = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last_err = e
            print(f"Attempt {i + 1}/{attempts} failed for {url}: {e}")
            time.sleep(5 * (i + 1))
    # curl has a different TLS fingerprint than urllib and sometimes passes
    # Cloudflare's bot check where Python does not.
    try:
        header_args = []
        for k, v in BROWSER_HEADERS.items():
            header_args += ['-H', f'{k}: {v}']
        out = subprocess.run(
            ['curl', '-sfL', '--max-time', '60', *header_args, url],
            capture_output=True, check=True
        )
        print(f"curl fallback succeeded for {url}")
        return json.loads(out.stdout.decode())
    except Exception as e:
        print(f"curl fallback failed for {url}: {e}")
    raise last_err


# Fetch team data from Barttorvik
teams = None
try:
    teams = fetch_json('https://barttorvik.com/2026_team_results.json')
    print(f"Total teams: {len(teams)}")
except Exception as e:
    print(f"Barttorvik fetch failed after retries: {e}")

# Fetch player stats from NCAA stats site
players = []
try:
    url = 'https://stats.ncaa.org/rankings/change_sport_year_div?sport_code=MBB&academic_year=2026&division=1&ranking_period=113&team_individual=I&stat_seq=145'
    req2 = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json, text/javascript, */*',
        'X-Requested-With': 'XMLHttpRequest'
    })
    with urllib.request.urlopen(req2, timeout=30) as r:
        content = r.read().decode()
        print(f"NCAA response preview: {content[:300]}")
except Exception as e:
    print(f"NCAA failed: {e}")

if teams is None:
    # Blocked (e.g. Cloudflare 403 on GitHub runner IPs): keep the existing
    # data.json instead of failing the whole run.
    if os.path.exists('data.json'):
        print("Keeping existing data.json; skipping update.")
        sys.exit(0)
    print("No existing data.json to fall back to.")
    sys.exit(1)

out = {
    'teams': teams,
    'players': players,
    'updated': datetime.datetime.now(datetime.timezone.utc).isoformat()
}

with open('data.json', 'w') as f:
    json.dump(out, f)
print("Done!")

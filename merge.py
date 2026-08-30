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

def fetch_cbbd(path):
    key = os.environ.get('CBB_DATA_API_KEY', '')
    if not key:
        raise RuntimeError('CBB_DATA_API_KEY not set')
    req = urllib.request.Request(
        'https://api.collegebasketballdata.com' + path,
        headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def teams_from_cbbd(existing_rows):
    """Rebuild Barttorvik-format rows from collegebasketballdata.com.

    Only some columns exist there (name, conf, record, adjOE, adjDE, pace),
    so start from the last known Barttorvik row per team and update those,
    preserving fields like SoS/WAB that CBBD does not provide.
    """
    ratings = fetch_cbbd('/ratings/adjusted?season=2026')
    stats = {s['team']: s for s in fetch_cbbd('/stats/team/season?season=2026')}
    print(f"CBBD: {len(ratings)} ratings, {len(stats)} stat lines")
    prev = {r[1]: r for r in existing_rows if isinstance(r, list) and len(r) > 44}

    rows = []
    for t in ratings:
        name = t.get('team')
        oe, de = t.get('offensiveRating'), t.get('defensiveRating')
        if not name or oe is None or de is None:
            continue
        st = stats.get(name, {})
        w = int(st.get('wins') or 0)
        l = int(st.get('losses') or 0)
        row = list(prev[name]) if name in prev else [0] * 45
        row[1] = name
        row[2] = t.get('conference') or row[2]
        row[3] = f"{w}-{l}"
        row[4] = oe
        row[6] = de
        row[8] = oe ** 11.5 / (oe ** 11.5 + de ** 11.5)  # barthag
        row[10], row[11] = float(w), float(l)
        if st.get('pace'):
            row[44] = st['pace']
        rows.append(row)
    rows.sort(key=lambda r: -r[8])
    for i, row in enumerate(rows):
        row[0] = i + 1
    return rows


if teams is None:
    # Barttorvik blocks GitHub runner IPs via Cloudflare; rebuild from the
    # collegebasketballdata.com API instead.
    existing = []
    if os.path.exists('data.json'):
        try:
            existing = json.load(open('data.json')).get('teams', [])
        except Exception:
            pass
    try:
        teams = teams_from_cbbd(existing)
        print(f"Total teams (via CBBD): {len(teams)}")
    except Exception as e:
        print(f"CBBD fallback failed: {e}")

if not teams:
    # Keep the existing data.json instead of failing the whole run.
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

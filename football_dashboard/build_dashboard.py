"""Build a standalone dashboard from the CSV exports in the parent folder."""

import argparse
import csv
import io
import json
import math
import re
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
RESULTS_CACHE = HERE / "football-data-results.json"
RESULTS_SOURCE = "Football-Data.co.uk"
VERIFIED_UPDATES = HERE / "verified-match-updates.json"
POINTS_ADJUSTMENTS = {("championship", "2026-27"): {"Southampton": -4}}
LEAGUES = {
    "premier-league": ("Premier League", "Prem", "Prem", "E0"),
    "championship": ("Championship", "champ", "Champ", "E1"),
    "league-one": ("League One", "L1", "Lg1", "E2"),
    "league-two": ("League Two", "L2", "Lg2", "E3"),
}
ALIASES = {
    "Hull": "Hull City", "Man City": "Manchester City", "Man United": "Manchester United",
    "Nott'm Forest": "Nottingham Forest", "Sheffield Utd": "Sheffield United", "Stoke": "Stoke City",
    "Burton": "Burton Albion", "Cambridge": "Cambridge United", "Mansfield": "Mansfield Town",
    "Oxford": "Oxford United", "Peterboro": "Peterborough", "Sheffield Weds": "Sheffield Wednesday",
    "Stockport": "Stockport County", "Accrington ST": "Accrington Stanley",
    "Accrington": "Accrington Stanley", "Bristol Rvs": "Bristol Rovers", "Exeter": "Exeter City",
    "Salford": "Salford City", "Swindon": "Swindon Town",
}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line, row in enumerate(reader, 2):
            if any(value and value.strip() for value in row.values() if isinstance(value, str)):
                yield line, row


def team(name):
    name = " ".join(name.split())
    if not name:
        raise ValueError("missing team name")
    return ALIASES.get(name, name)


def result(row):
    day = datetime.strptime(row["Date"], "%d/%m/%Y").date()
    home, away = team(row["HomeTeam"]), team(row["AwayTeam"])
    goals = [int(row[field]) for field in ("FTHG", "FTAG")]
    if min(goals) < 0:
        raise ValueError("negative goal count")
    xg = [row.get(field, "").strip() for field in ("HxG", "AxG")]
    values = [None, None]
    if all(xg):
        values = [float(value) for value in xg]
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("invalid expected goals")
    return day.isoformat(), row.get("Time", "").strip(), home, away, *goals, "Played", *values


def fixture(row):
    day = date.fromisoformat(row["date"])
    status = row["status"].strip()
    goals = [None, None]
    if status.casefold() == "played":
        score = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", row["result"].strip())
        if not score:
            raise ValueError("played match is missing a valid score")
        goals = [int(goal) for goal in score.groups()]
        status = "Played"
    elif status.casefold() == "to be played":
        status = "To be played"
    return day.isoformat(), row["time"].strip(), team(row["home_team"]), team(row["away_team"]), *goals, status


def season_label(year):
    return f"{year}-{(year + 1) % 100:02}"


def baseline_season(day):
    year, month, _ = map(int, day.split("-"))
    # The 2019/20 season continued into July 2020.
    return season_label(year - (month < 7 or (year == 2020 and month == 7)))


def build(downloaded=None):
    matches = defaultdict(dict)
    sources = defaultdict(set)
    conflicts = defaultdict(int)
    verified_sources = defaultdict(set)
    verified_results = defaultdict(int)
    verified_checked = {}
    updates = json.loads(VERIFIED_UPDATES.read_text(encoding="utf-8")) if VERIFIED_UPDATES.exists() else []

    def add(slug, season, match, path):
        bucket = (slug, season)
        key = match[2:4]
        previous = matches[bucket].get(key)
        if previous and previous[6] == "Played" and match[6] != "Played":
            return
        if previous and previous[6] == match[6] == "Played" and previous[4:6] != match[4:6]:
            conflicts[bucket] += 1
        match = tuple(match[:7]) + tuple(match[7:9] or (None, None))
        if previous and len(previous) >= 9 and all(value is not None for value in previous[7:9]):
            if any(value is None for value in match[7:9]):
                match = match[:7] + tuple(previous[7:9])
        matches[bucket][key] = match
        sources[bucket].add(path.name)

    def load(path, consume):
        for line, row in read_csv(path):
            try:
                consume(row)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise ValueError(f"{path.name}, row {line}: {exc}") from exc

    baseline = SOURCE / "Baseline.csv"
    if baseline.exists():
        divisions = {info[2]: slug for slug, info in LEAGUES.items()}

        def add_baseline(row):
            match = result(row)
            add(divisions[row["Div"]], baseline_season(match[0]), match, baseline)

        load(baseline, add_baseline)

    for slug, (_, prefix, _, division) in LEAGUES.items():
        for path in sorted(SOURCE.glob(f"{slug}-gb-eng_*.csv")):
            label = re.fullmatch(r".+_(\d{4})-(\d{2})", path.stem)
            if label:
                season = season_label(int(label[1]))
                if not season.endswith(label[2]):
                    raise ValueError(f"Invalid season in {path.name}")
                load(path, lambda row: add(slug, season, fixture(row), path))

        for path in sorted(SOURCE.glob(f"{prefix}*.csv")):
            label = re.fullmatch(rf"{prefix}_?(\d{{2}})(\d{{2}})", path.stem, re.IGNORECASE)
            if label:
                season = season_label(2000 + int(label[1]))
                if not season.endswith(label[2]):
                    raise ValueError(f"Invalid season in {path.name}")

                def add_result(row):
                    if row["Div"] != division:
                        raise ValueError(f"expected division {division}, got {row['Div']}")
                    add(slug, season, result(row), path)

                load(path, add_result)

        for season, snapshot in (downloaded or {}).items():
            for match in snapshot["leagues"][slug]:
                add(slug, season, tuple(match), Path(RESULTS_SOURCE))

        for update in updates:
            if update["league"] != slug:
                continue
            season = update["season"]
            checked = date.fromisoformat(update["verified_on"]).isoformat()
            for record in update["matches"]:
                match = tuple(record[:2]) + tuple(team(name) for name in record[2:4]) + tuple(record[4:])
                date.fromisoformat(match[0])
                key = match[2:4]
                previous = matches[slug, season].get(key)
                if not previous:
                    raise ValueError(f"Verified update has an unknown fixture: {slug} {key}")
                if match[6] not in {"Played", "To be played", "Postponed"}:
                    raise ValueError(f"Invalid verified fixture status: {match[6]}")
                if match[6] == "Played" and any(type(goal) is not int or goal < 0 for goal in match[4:6]):
                    raise ValueError(f"Invalid verified score: {key}")
                # The results feed takes over when it catches up with a verified score.
                if previous[6] == "Played":
                    continue
                if match[6] == "Played":
                    kickoff = previous[1] if previous[0] == match[0] else ""
                    match = match[:1] + (kickoff,) + match[2:]
                add(slug, season, match, VERIFIED_UPDATES)
                verified_sources[slug, season].add(update["source"])
                verified_results[slug, season] += match[6] == "Played"
                verified_checked[slug, season] = max(checked, verified_checked.get((slug, season), ""))

    if not matches:
        raise ValueError("No matching CSV exports found beside the football_dashboard folder.")
    data = {}
    for slug, (name, *_) in LEAGUES.items():
        seasons = {
            season: {
                "matches": sorted(matches[slug, season].values()),
                "sources": sorted(sources[slug, season]),
                "conflicts": conflicts[slug, season],
                "points_adjustments": POINTS_ADJUSTMENTS.get((slug, season), {}),
                "results_checked": (downloaded or {}).get(season, {}).get("checked"),
                "verified_sources": sorted(verified_sources[slug, season]),
                "verified_results": verified_results[slug, season],
                "verified_checked": verified_checked.get((slug, season)),
            }
            for league, season in sorted(matches, reverse=True)
            if league == slug
        }
        if seasons:
            data[slug] = {"name": name, "seasons": seasons}
    return data


def download_results(today, previous):
    year = today.year - (today.month < 7)
    season = season_label(year)
    season_code = f"{year % 100:02}{(year + 1) % 100:02}"
    leagues = {}
    for slug, (name, _, _, division) in LEAGUES.items():
        url = f"https://football-data.co.uk/mmz4281/{season_code}/{division}.csv"
        try:
            with urlopen(url, timeout=25) as response:
                content = response.read().decode("utf-8-sig")
        except HTTPError as exc:
            raise ValueError(f"{name} results download returned HTTP {exc.code}") from None
        except (URLError, TimeoutError) as exc:
            raise ValueError(f"{name} results download failed: {exc}") from None

        matches = {}
        reader = csv.DictReader(io.StringIO(content, newline=""))
        required = {"Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"{name} results have an unexpected CSV header")
        for row in reader:
            if not any(row.get(field) for field in required):
                continue
            try:
                if row["Div"] != division:
                    raise ValueError(f"expected division {division}")
                match = result(row)
                key = match[2:4]
                if baseline_season(match[0]) != season or match[0] > today.isoformat():
                    raise ValueError("match date is outside the current season or in the future")
                if key in matches or key[0] == key[1]:
                    raise ValueError("invalid or duplicate home/away pairing")
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(f"{name} results, CSV line {reader.line_num}: {exc}") from exc
            matches[key] = match

        previous_matches = previous.get(season, {}).get("leagues", {}).get(slug, [])
        if not matches or any(tuple(match[2:4]) not in matches for match in previous_matches):
            raise ValueError(f"{name} results are empty or missing previously downloaded matches")
        leagues[slug] = list(matches.values())

    return season, {"checked": datetime.now(UTC).isoformat(), "leagues": leagues}


def write_atomic(path, content):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
        except OSError:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-results", action="store_true", help="download current-season results first")
    parser.add_argument("--output", type=Path, default=SOURCE / "Football Dashboard.html",
                        help="path for the generated dashboard")
    options = parser.parse_args()
    downloaded = json.loads(RESULTS_CACHE.read_text(encoding="utf-8")) if RESULTS_CACHE.exists() else {}
    if options.refresh_results:
        season, snapshot = download_results(date.today(), downloaded)
        downloaded[season] = snapshot

    data = build(downloaded)
    try:
        from season_simulation import simulate_season
    except ModuleNotFoundError as exc:
        raise ValueError("Install simulation dependencies with: python -m pip install -r football_dashboard/requirements.txt") from exc
    for slug, league in data.items():
        latest = max(league["seasons"])
        league["seasons"][latest]["prediction"] = simulate_season(
            league["seasons"][latest], seed=20261125 + list(LEAGUES).index(slug))
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = (HERE / "dashboard.template.html").read_text(encoding="utf-8")
    output = options.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if options.refresh_results:
        write_atomic(RESULTS_CACHE, json.dumps(downloaded, ensure_ascii=False, separators=(",", ":")))
        print(f"Downloaded {sum(map(len, snapshot['leagues'].values()))} results for {season} from {RESULTS_SOURCE}")
    write_atomic(output, template.replace("/* DASHBOARD_DATA */", encoded, 1))
    print(f"Built {output.name}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Dashboard refresh failed: {exc}") from exc

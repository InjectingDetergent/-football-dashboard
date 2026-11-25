# Football Dashboard

A personal dashboard for the Premier League, Championship, League One and League Two, built from the CSV exports in this folder.

## Publish with GitHub Pages

1. Create a public GitHub repository named `football-dashboard`, using `main` as its default branch.
2. Upload the CSV files, the `football_dashboard` folder, this README, `.gitignore` and `.github/workflows/publish-dashboard.yml`, preserving their folder structure.
3. In the repository, open **Settings → Pages** and choose **GitHub Actions** under **Build and deployment → Source**.
4. Open **Actions → Refresh and publish football dashboard → Run workflow**.
5. After the run succeeds, open **Settings → Pages** to find the published address.

The public repository includes the uploaded data and source code. The published dashboard includes the match history used by its tables.

## Updates

The GitHub workflow downloads free results for all four divisions, rebuilds the dashboard and publishes it every Tuesday at 8 am in Europe/London. It also runs when changes are pushed to `main` or when started manually. GitHub may delay scheduled runs.

Replace fixture CSVs in the repository when fixture dates change. Changes made only on your PC reach the website after you upload or push them to GitHub.

GitHub can disable scheduled workflows in public repositories after 60 days without repository activity. If this happens, enable the workflow again under Actions.

The results download is validated before publication. A failed refresh leaves the previous deployed website available. The workflow caches downloaded results between runs, with the uploaded snapshot as its starting point.

## Local use

Install the simulation dependencies once with `py -3 -m pip install -r football_dashboard/requirements.txt`.

Run `Refresh Football Dashboard.cmd` to rebuild and open the local dashboard from the supplied files and cached results.

To download fresh results and rebuild manually, run

```powershell
py -3 football_dashboard/build_dashboard.py --refresh-results
```

To build the website for hosting, run

```powershell
py -3 football_dashboard/build_dashboard.py --output dist/index.html
```

## Season predictions

Every rebuild simulates 20,000 regular seasons for each division's latest season using a fixed seed. Open **Season Predictions** and choose a division to see a finishing-position heatmap and current versus projected points chart. Both charts can be downloaded as SVG, and the predictions can be downloaded as CSV.

The model estimates attack and defence strengths with home advantage, a 90-day recency half-life and regularisation towards league average. It compares goals-only and 70% xG / 30% goals models on a chronological holdout, then refits the lower-loss model on all completed matches. The holdout stays together by date. This first comparison uses one split of the current season.

The downloader retains available home and away xG. Existing seven-field results caches are supported, and matching local xG is retained when a cached result lacks it. Missing xG falls back to actual goals. The page reports xG coverage and the last result date.

Remaining fixtures include postponed and overdue games. A complete home-and-away programme is required. Current points deductions are preserved. Simulated standings use points, goal difference and goals scored, with random order for remaining ties. Later tie-break rules and play-off results are outside this model.

The middle 80% points range reflects match randomness with fixed estimated strengths. Parameter uncertainty, injuries and future squad changes are outside this first version. The model settings are shown on the page and can be reviewed in `football_dashboard/season_simulation.py`.

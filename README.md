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

Run `Refresh Football Dashboard.cmd` to rebuild and open the local dashboard from the supplied files and cached results.

To download fresh results and rebuild manually, run

```powershell
py -3 football_dashboard/build_dashboard.py --refresh-results
```

To build the website for hosting, run

```powershell
py -3 football_dashboard/build_dashboard.py --output dist/index.html
```

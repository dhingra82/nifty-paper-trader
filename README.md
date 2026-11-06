# Nifty Paper Trader: setup (about 10 minutes, no coding)

1. Sign in at github.com as **dhingra82**. Click **+ > New repository**. Name it `nifty-paper-trader`, choose **Public** (free GitHub Pages needs this), tick "Add a README", and click Create.
2. In the repo, click **Add file > Create new file**. In the name box type `worker/run.py` (typing the slash makes the folder). Paste the contents of `run.py`, then click **Commit changes**.
3. Repeat for `.github/workflows/daily.yml` (paste the contents of daily.yml) and for `docs/index.html` (paste index.html).
4. Go to **Settings > Pages**. Under "Build and deployment", set Source to **Deploy from a branch**, Branch **main**, folder **/docs**, and Save.
5. Go to the **Actions** tab. If asked, click "I understand my workflows, enable them". Open **daily-paper-trader**, click **Run workflow**, and wait about 1-2 minutes for a green tick.
6. Your dashboard is at: **https://dhingra82.github.io/nifty-paper-trader/** (first load can take a few minutes).

From then on it updates itself every weekday at about 5 PM IST.

## Notes
- Results are public, because the repo is public. Don't put any keys or passwords in it.
- Paper trades begin from the day of your first run (stored in `docs/state.json`).
- Change symbol or thresholds at the top of `worker/run.py`. Swapping data source means editing `load_data()` only.

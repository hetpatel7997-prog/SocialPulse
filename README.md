# SocialPulse – Social Media Intelligence & Analytics Platform

Upload your Instagram data export and turn it into analytics: followers and following, content performance,
interactive charts, automated insights, machine learning and downloadable PDF/Excel reports.
Built for a Data Management and Visual Insights (DMVI) portfolio.

**Core principle:** only metrics the uploaded data supports are calculated. Anything missing (for example
like counts, which Instagram's standard export does not contain) is labelled *unavailable*, never invented.

## Features
- Register / login / logout, hashed passwords, CSRF protection, per-user data isolation
- Import JSON, CSV, XLSX and HTML (drag and drop, progress, import summary, duplicate-file detection)
- Flexible parser for nested Instagram JSON, flat tables, Excel sheets and HTML account lists
- Followers / following: mutual, not-following-back, ratio, search, sort, pagination
- New / no-longer-following lists **only** when 2+ follower snapshots (different export dates) exist
- Content analytics: top/lowest posts, trends, filters (date, type, performance), type comparison
- 8 interactive Chart.js visualisations with empty states
- Data cleaning page: quality report, raw vs cleaned preview, saved as a separate cleaned dataset (raw is never deleted)
- Insights engine (plain-language, every statement computed from data)
- ML: K-Means groups, anomaly detection, trend analysis, short trend forecast (with honest limits)
- Reports: PDF (ReportLab) and Excel (OpenPyXL, only sheets your data supports)
- Demo mode with clearly labelled sample data; one-click deletion of any upload or all data

## Technologies
Python 3, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, MySQL (PyMySQL), Pandas, NumPy, OpenPyXL,
BeautifulSoup, scikit-learn, ReportLab, Bootstrap 5, Chart.js.

## Setup (Windows + VS Code)
1. Install Python 3.10+ and MySQL 8 (keep the server running).
2. In a VS Code terminal:
```powershell
cd SocialPulse
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
3. Edit `.env`: set `SECRET_KEY` (any long random text) and your MySQL `DB_USER` / `DB_PASSWORD`.
   Generate a key with: `python -c "import secrets; print(secrets.token_hex(32))"`
4. Create the database and tables (creates the `socialpulse` database automatically):
```powershell
python init_db.py
```
   Or manually in MySQL: `CREATE DATABASE socialpulse CHARACTER SET utf8mb4;` then run `python init_db.py`.
5. Start the app: `python app.py` and open http://127.0.0.1:5000

## Run the tests
```powershell
pytest
```
`tests/test_services.py` covers parsing (JSON/CSV/Excel/HTML), cleaning, analytics, ML and reports.
`tests/test_routes.py` covers registration, login, uploads, invalid files, user isolation, deletion, cleaning and reports.
Tests use in-memory SQLite, so MySQL is not needed for them.

## Importing your Instagram data
Instagram: **Accounts Center → Your information and permissions → Download your information →
Download or transfer information →** choose your account and data (Followers and following, Posts) →
**Download to device**, format **JSON**, range **All time**. When ready, unzip and upload files such as
`followers_1.json`, `following.json`, `posts_1.json`. Menu names may vary slightly. The same steps are shown on the Upload page.

- If a file's type can't be detected, choose *Followers*, *Following* or *Posts* before uploading.
- Instagram splits large lists into several files; upload them with the same **export date** and they are combined.
- To track follower growth, upload exports from different dates.
- Standard Instagram exports have **no like/comment counts per post**. Upload a CSV/Excel with columns like
  `date, caption, likes, comments, type` (insights export or your own sheet) to unlock engagement analytics.

## Sample datasets
`tests/sample_data/` contains fictional files (no real people) in every supported format.
Or press **Load demo data** on the Upload page for a full labelled demo account.

## Project structure
```
app.py  config.py  extensions.py  init_db.py
models/    users, datasets/followers/following/posts, analytics/reports tables
routes/    auth, dashboard, uploads, analytics, reports
services/  instagram_parser, data_cleaner, analytics_engine, insights_engine, ml_engine, report_generator, repository, demo_data
templates/ static/ tests/ uploads/ generated_reports/
```

## Design notes
- Raw vs cleaned: import keeps the original file on disk and drops only unusable rows/duplicates (counts are shown).
  The cleaning page saves a *separate* cleaned dataset; analytics use it when it exists; reverting restores raw.
- Every query filters by `user_id`; files are stored under per-user folders with random names and never served directly.

## Screenshots
Add your screenshots here (dashboard, upload, followers, content, ML, reports).

## Future improvements
Scheduled snapshot reminders, more HTML post layouts, story/reel insight exports, Alembic migrations, Docker.

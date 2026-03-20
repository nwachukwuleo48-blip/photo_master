# photography_masterpiece

Flask photography portfolio + booking site.

## Why the hero/portfolio can look “wiped” on Render

- Linux is case-sensitive: a filename mismatch like `hero8.PNG` vs `hero8.png` works locally on Windows but breaks on Render.
- Render filesystem is ephemeral: **SQLite databases** and **uploaded files** stored on disk reset on every deploy/restart unless you use a persistent disk.
- `.env` is ignored by git and won’t be present on Render — set env vars in the Render dashboard.

## Render setup (recommended)

- Use **Render Postgres** and set `DATABASE_URL`.
- If you insist on SQLite, mount a persistent disk and set `DATA_DIR=/var/data`.
- For Cloudinary uploads, set `CLOUD_NAME`, `CLOUD_API_KEY`, `CLOUD_API_SECRET`.

## Local run

- `pip install -r requirements.txt`
- `python app.py`

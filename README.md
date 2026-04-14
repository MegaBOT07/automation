# Google Sheets → HeyGen Automation

Automatically turns approved scripts in a Google Sheet into avatar videos using HeyGen's built-in voices.

## How It Works

1. Type a script in column A, set column B to **Approved**
2. Python watcher detects it (every 30 seconds)
3. Script sent directly to **HeyGen** with your avatar's built-in voice
4. HeyGen renders the avatar video
5. **Video link** written back to column C, status set to **Done**

---

## Google Sheet Layout

| A — Script | B — Status | C — Video Link | D — Notes |
|---|---|---|---|
| Your script text | **Approved** ← you set this | auto | errors |

**Status values:**
- `Pending` — waiting, not yet processed
- `Approved` — **triggers the automation** ← you set this
- `Processing` — running right now
- `Done` — video link is in column C
- `Error` — something failed (see column D for details)

---

## Setup

### Step 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 2 — Set up Google Service Account

1. Go to https://console.cloud.google.com
2. Create a new project (or select an existing one)
3. Go to **APIs & Services → Enable APIs**
   - Enable **Google Sheets API**
   - Enable **Google Drive API**
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → Service Account**
6. Give it any name, click **Done**
7. Click the service account → **Keys tab → Add Key → JSON**
8. Download the JSON file
9. Open the downloaded JSON file with a text editor
10. Copy the **entire JSON content** (keep it as one line)

### Step 3 — Share your Google Sheet with the service account

1. From the JSON you copied, find the `client_email` field — it looks like:
   `your-bot@your-project.iam.gserviceaccount.com`
2. Open your Google Sheet
3. Click **Share** (top right)
4. Paste that email address → set role to **Editor** → click Share

### Step 4 — Get your Sheet ID

Your sheet URL looks like:
```
https://docs.google.com/spreadsheets/d/   /edit
```
The long string in the middle is your `GOOGLE_SHEET_ID`.

### Step 5 — Set up your .env

```bash
cp .env.example .env
```

Edit `.env` and fill in:
- `GOOGLE_CREDENTIALS_JSON` — paste the entire JSON file content here (as single line)
- `GOOGLE_SHEET_ID` — your sheet ID from step 4
- `HEYGEN_API_KEY` — your HeyGen API key
- `HEYGEN_AVATAR_ID` — your HeyGen avatar ID

**Find your HeyGen Avatar ID:** Go to https://app.heygen.com/avatars → click your avatar → copy the ID from the URL or details panel

### Step 6 — Add headers to your Google Sheet (row 1)

Add these exact headers in row 1:

| A | B | C | D |
|---|---|---|---|
| Script | Status | Video Link | Notes |

### Step 7 — Run the automation

```bash
python automation.py
```

Or use Flask for headless continuous operation:

```bash
python app.py
```

---

## Configuration

Edit your `.env` file to customize:

```env
# Video quality and format
VIDEO_RESOLUTION=1080p        # 720p, 1080p, or 4k
VIDEO_ASPECT_RATIO=16:9       # 16:9 (desktop) or 9:16 (mobile)

# Poll frequency
POLL_INTERVAL=30              # seconds between sheet checks
HEYGEN_POLL_SECS=15           # seconds between video render checks
```

---

## Troubleshooting

**"word time metadata is missing"**  
(This was needed with external audio—not applicable now since we use avatar's built-in voice)

**"avatar look not found"**  
Check your `HEYGEN_AVATAR_ID` is valid at https://app.heygen.com/avatars

**No videos generating**  
- Ensure status is exactly `Approved` (case-sensitive)
- Check logs for API key errors
- Verify avatar has a built-in voice configured in HeyGen

**Videos stuck in "Processing"**  
- Check HeyGen API quota
- Higher resolutions (4k) take longer—wait a few minutes

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `credentials.json not found` | Download service account JSON and place it here |
| `403 / PERMISSION_DENIED` | Share the sheet with the service account email (Editor role) |
| `Missing required env vars` | Check your `.env` file — all required keys must be set |
| `401 Unauthorized` | API key is wrong or expired |
| `HeyGen video failed` | Double-check HEYGEN_AVATAR_ID at app.heygen.com/avatars |
| Row stuck on "Processing" | Restart was interrupted — manually reset Status to "Approved" |

---

## Run Through Flask (Headless)

If you want this to run without UI/buttons, start Flask in headless mode:

```bash
python app.py
```

It auto-starts the worker and keeps polling continuously using `POLL_INTERVAL`.

Optional status endpoints:

- `GET /` returns a simple JSON message + worker state
- `GET /health` returns worker state

### Important for Vercel

Vercel serverless functions are not designed for always-on background threads. For truly continuous polling, deploy this worker on an always-on service (for example Render, Railway, Fly.io, or a VM) instead of Vercel.

"""
Google Sheets → HeyGen Automation
----------------------------------
Watches a Google Sheet for rows with Status = "Approved",
submits the script to HeyGen with the avatar's built-in voice (no ElevenLabs),
then writes the video link back to the sheet.

Sheet columns (row 1 = headers):
  A: Script
  B: Status       ← user sets to "Approved" to trigger
  C: Video Link   ← auto-filled by this script
  D: Notes        ← error messages written here
"""

import os
import json
import time
import requests
import logging
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config from .env ─────────────────────────────────────────────────────────
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_SHEET_ID         = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SHEET_NAME       = os.getenv("GOOGLE_SHEET_NAME", "Sheet1")
POLL_INTERVAL           = int(os.getenv("POLL_INTERVAL", "30"))

HEYGEN_API_KEY          = os.getenv("HEYGEN_API_KEY")
HEYGEN_AVATAR_ID        = os.getenv("HEYGEN_AVATAR_ID")
HEYGEN_POLL_SECS        = int(os.getenv("HEYGEN_POLL_SECS", "15"))
VIDEO_RESOLUTION        = os.getenv("VIDEO_RESOLUTION", "1080p")  # 720p, 1080p, 4k
VIDEO_ASPECT_RATIO      = os.getenv("VIDEO_ASPECT_RATIO", "16:9")  # 16:9 (desktop) or 9:16 (mobile)

# ── Column positions (1-based for gspread) ───────────────────────────────────
COL_SCRIPT     = 1   # A
COL_STATUS     = 2   # B
COL_VIDEO_LINK = 3   # C
COL_NOTES      = 4   # D

TRIGGER_VALUE    = "Approved"
PROCESSING_VALUE = "Processing"
DONE_VALUE       = "Done"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ── Google Sheets ────────────────────────────────────────────────────────────

def connect_sheet():
    """Authenticate and return the target worksheet."""
    # Parse credentials JSON from environment
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    return spreadsheet.worksheet(GOOGLE_SHEET_NAME)


def read_pending_rows(ws) -> list:
    """Return all rows where Status == 'Approved'."""
    all_rows = ws.get_all_values()
    pending = []
    for idx, row in enumerate(all_rows[1:], start=2):  # skip header
        while len(row) < 4:
            row.append("")
        if row[COL_STATUS - 1].strip() == TRIGGER_VALUE and row[COL_SCRIPT - 1].strip():
            pending.append({"row_idx": idx, "script": row[COL_SCRIPT - 1].strip()})
    return pending


def col_letter(n: int) -> str:
    """Convert 1-based column number to letter."""
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def update_row(ws, row_idx: int, **kwargs):
    """Update specific cells in a row."""
    updates = []
    mapping = {
        "status":     COL_STATUS,
        "video_link": COL_VIDEO_LINK,
        "notes":      COL_NOTES,
    }
    for key, col in mapping.items():
        if key in kwargs:
            updates.append({
                "range": f"{col_letter(col)}{row_idx}",
                "values": [[kwargs[key]]]
            })
    if updates:
        ws.batch_update(updates)
        log.info("Sheet row %d updated.", row_idx)


# ── HeyGen ───────────────────────────────────────────────────────────────────

def create_heygen_video(script: str) -> str:
    """Submit video generation job with avatar's built-in voice, return video_id."""
    payload = {
        "type": "avatar",
        "avatar_id": HEYGEN_AVATAR_ID,
        "script": script,
        "resolution": VIDEO_RESOLUTION,
        "aspect_ratio": VIDEO_ASPECT_RATIO,
        "background": {
            "type": "color",
            "value": "#FFFFFF",
        },
    }
    
    log.info("HeyGen v3 payload: %s", payload)
    
    resp = requests.post(
        "https://api.heygen.com/v3/videos",
        headers={"x-api-key": HEYGEN_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    
    if not resp.ok:
        error_text = resp.text[:300]
        log.error("HeyGen v3 video create failed %d: %s", resp.status_code, error_text)
        resp.raise_for_status()
    
    video_id = resp.json()["data"]["video_id"]
    log.info("HeyGen v3: video job submitted → %s", video_id)
    return video_id


def poll_heygen_video(video_id: str) -> str:
    """Poll until HeyGen video is complete, return the video URL."""
    headers = {"x-api-key": HEYGEN_API_KEY}
    while True:
        resp = requests.get(
            f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data.get("status")
        log.info("HeyGen %s → %s", video_id, status)
        if status == "completed":
            video_url = data.get("video_url")
            log.info("Video ready → %s", video_url)
            return video_url
        if status in ("failed", "error"):
            raise RuntimeError(f"HeyGen video failed: {data}")
        time.sleep(HEYGEN_POLL_SECS)


# ── Row processing ───────────────────────────────────────────────────────────

def process_row(ws, row: dict):
    row_idx, script = row["row_idx"], row["script"]
    log.info("Row %d: %.60s…", row_idx, script)
    update_row(ws, row_idx, status=PROCESSING_VALUE, notes="")

    try:
        # Submit to HeyGen v3 (uses avatar's built-in voice, no audio generation needed)
        update_row(ws, row_idx, video_link="Rendering video…")
        video_id = create_heygen_video(script)

        # Poll until complete
        video_url = poll_heygen_video(video_id)

        update_row(ws, row_idx, status=DONE_VALUE, video_link=video_url, notes="")
        log.info("Row %d done → %s", row_idx, video_url)

    except Exception as exc:
        log.error("Row %d failed: %s", row_idx, exc)
        update_row(ws, row_idx, status="Error", notes=str(exc)[:250])


def process_pending_rows(ws) -> int:
    """Process all currently approved rows and return count."""
    pending = read_pending_rows(ws)
    if pending:
        log.info("%d approved row(s) found.", len(pending))
        for row in pending:
            process_row(ws, row)
    return len(pending)


# ── Startup validation ────────────────────────────────────────────────────────

def validate_config():
    missing = [v for v in ["GOOGLE_SHEET_ID", "GOOGLE_CREDENTIALS_JSON", "HEYGEN_API_KEY", "HEYGEN_AVATAR_ID"]
               if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    validate_config()
    log.info("Connecting to Google Sheet…")
    ws = connect_sheet()
    log.info("Connected. Polling every %ds for 'Approved' rows.", POLL_INTERVAL)

    while True:
        try:
            process_pending_rows(ws)
        except gspread.exceptions.APIError as exc:
            log.error("Sheets API error: %s", exc)
        except Exception as exc:
            log.error("Error: %s", exc)
        time.sleep(POLL_INTERVAL)


def run_once() -> int:
    """Run exactly one scan/process cycle. Useful for web-triggered execution."""
    validate_config()
    ws = connect_sheet()
    return process_pending_rows(ws)


if __name__ == "__main__":
    run()
import os
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify

import automation

app = Flask(__name__)

worker_thread = None
worker_stop_event = threading.Event()
worker_lock = threading.Lock()
state = {
    "running": False,
    "last_run": None,
    "last_error": None,
    "last_processed": 0,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _is_worker_alive() -> bool:
    return worker_thread is not None and worker_thread.is_alive()


def _worker_loop():
    try:
        automation.validate_config()
        ws = automation.connect_sheet()
        with worker_lock:
            state["running"] = True
            state["last_error"] = None

        while not worker_stop_event.is_set():
            try:
                processed = automation.process_pending_rows(ws)
                with worker_lock:
                    state["last_processed"] = processed
                    state["last_run"] = _utc_now()
                    state["last_error"] = None
            except Exception as exc:  # Keep worker alive after transient failures.
                with worker_lock:
                    state["last_error"] = str(exc)
                    state["last_run"] = _utc_now()

            worker_stop_event.wait(automation.POLL_INTERVAL)
    except Exception as exc:
        with worker_lock:
            state["last_error"] = str(exc)
    finally:
        with worker_lock:
            state["running"] = False


def _snapshot_state() -> dict:
    with worker_lock:
        return dict(state)


def ensure_worker_running() -> bool:
    """Start worker if needed. Returns True if started now."""
    global worker_thread

    with worker_lock:
        already_running = state["running"] and _is_worker_alive()
    if already_running:
        return False

    worker_stop_event.clear()
    worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    worker_thread.start()
    return True


@app.route("/")
def hello_world():
    ensure_worker_running()
    return jsonify({"message": "automation worker is running", "state": _snapshot_state()})


@app.route("/health")
def health():
    ensure_worker_running()
    return jsonify(_snapshot_state())


if __name__ == "__main__":
    # Only auto-start the worker in the actual Werkzeug reloader child process.
    # WERKZEUG_RUN_MAIN is only set to "true" in the child, not the parent.
    if os.getenv("WERKZEUG_RUN_MAIN") == "true":
        ensure_worker_running()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)

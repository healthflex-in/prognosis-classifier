"""
Progress tracking for triage agent runs.
Uses a JSON file to track progress across requests.
Thread-safe for concurrent processing.
"""
import json
import os
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any


PROGRESS_FILE = Path(__file__).parent.parent / "LLM" / "triage_progress.json"
_progress_lock = threading.Lock()


def get_progress() -> Dict[str, Any]:
    """
    Get current progress from file (thread-safe).
    
    Returns:
        Dictionary with progress information
    """
    with _progress_lock:
        if not PROGRESS_FILE.exists():
            return {
                "status": "idle",
                "current": 0,
                "total": 0,
                "started_at": None,
                "completed_at": None,
                "error": None,
                "message": None,
                "output_file": None
            }
        
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading progress file: {e}")
            return {
                "status": "idle",
                "current": 0,
                "total": 0,
                "started_at": None,
                "completed_at": None,
                "error": None,
                "message": None,
                "output_file": None
            }


def _get_progress_internal() -> Dict[str, Any]:
    """Internal function to get progress without lock (called from within locked context)."""
    if not PROGRESS_FILE.exists():
        return {
            "status": "idle",
            "current": 0,
            "total": 0,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "output_file": None
        }
    
    try:
        with open(PROGRESS_FILE, 'r') as f:
            data = json.load(f)
            # Ensure output_file is in the dict
            if "output_file" not in data:
                data["output_file"] = None
            return data
    except Exception as e:
        print(f"Error reading progress file: {e}")
        return {
            "status": "idle",
            "current": 0,
            "total": 0,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "output_file": None
        }


def set_progress(
    status: str,
    current: int = 0,
    total: int = 0,
    error: Optional[str] = None,
    message: Optional[str] = None,
    output_file: Optional[str] = None
):
    """
    Update progress in file (thread-safe).
    
    Args:
        status: Status of the process ("running", "completed", "error", "idle")
        current: Current number of patients processed
        total: Total number of patients to process
        error: Error message if status is "error"
        message: Optional message describing current phase (e.g., "Listing patients...", "Filtering...")
        output_file: Optional path to the current classification output file
    """
    with _progress_lock:
        progress = {
            "status": status,
            "current": current,
            "total": total,
            "started_at": None,
            "completed_at": None,
            "error": error,
            "message": message,
            "output_file": output_file
        }
        
        # Load existing progress to preserve timestamps and output_file (use internal function to avoid deadlock)
        existing = _get_progress_internal()
        if existing.get("started_at") and status == "running":
            progress["started_at"] = existing.get("started_at")
        elif status == "running" and not existing.get("started_at"):
            progress["started_at"] = datetime.now().isoformat()
        
        if status in ["completed", "error"]:
            progress["completed_at"] = datetime.now().isoformat()
            if existing.get("started_at"):
                progress["started_at"] = existing.get("started_at")
        
        # Preserve output_file if not explicitly set
        if output_file is None and existing.get("output_file"):
            progress["output_file"] = existing.get("output_file")
        
        # Ensure directory exists
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(PROGRESS_FILE, 'w') as f:
                json.dump(progress, f, indent=2)
        except Exception as e:
            print(f"Error writing progress file: {e}")


def increment_progress(total: int):
    """
    Thread-safe increment of progress counter.
    
    Args:
        total: Total number of patients to process
    """
    with _progress_lock:
        existing = _get_progress_internal()
        current = existing.get("current", 0) + 1
        # Update message to show current progress if it's a classification message
        existing_message = existing.get("message", "")
        if "Classifying" in existing_message or existing_message == "":
            message = f"Classifying patients ({current}/{total})..."
        else:
            message = existing_message  # Preserve other messages (e.g., "Filtering...")
        
        progress = {
            "status": "running",
            "current": current,
            "total": total,
            "started_at": existing.get("started_at") or datetime.now().isoformat(),
            "completed_at": None,
            "error": None,
            "message": message,
            "output_file": existing.get("output_file")  # Preserve output file
        }
        
        # Ensure directory exists
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(PROGRESS_FILE, 'w') as f:
                json.dump(progress, f, indent=2)
        except Exception as e:
            print(f"Error writing progress file: {e}")


def reset_progress():
    """Reset progress to idle state."""
    set_progress("idle", 0, 0)

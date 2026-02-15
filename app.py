import hashlib
import json
import os
import pickle
import re
import secrets
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

import pdfplumber
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, session
from flask_cors import CORS
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from pymongo.errors import DuplicateKeyError

from backend.config.mongo import course_collection
from backend.ics_converter import json_to_ics
from backend.study_guide_generator import generate_study_guide_pdf


load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# ----------------------------
# Session Configuration (Fixes "State mismatch" on localhost)
# ----------------------------
app.config["SESSION_COOKIE_SECURE"] = False  # Allow cookies over HTTP (for localhost)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Allow cookies in redirects

# ----------------------------
# Google Calendar Configuration
# ----------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5000/oauth2callback")
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.json"

# In-memory store for pending OAuth states (auto-cleaned on use)
_pending_oauth_states = {}

# ----------------------------
# OpenRouter Configuration
# ----------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-pro")

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")

USE_LOCAL_FALLBACK = os.getenv("USE_LOCAL_FALLBACK", "true").lower() == "true"
LOW_ACCURACY_THRESHOLD = 80.0


# ----------------------------
# PDF Extraction
# ----------------------------
def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            texts = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
            return "\n\n".join(texts)
    except Exception:
        return ""


# ----------------------------
# Local Regex Fallback
# ----------------------------
def parse_events_local(text: str) -> list:
    events = []
    current_year = datetime.now().year
    lines = text.split('\n')

    for line in lines:
        match = re.search(
            r'(.+?)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2}',
            line,
            re.IGNORECASE
        )

        if match:
            title = match.group(1).strip()
            date_match = re.search(
                r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2}',
                line,
                re.IGNORECASE
            )

            if date_match:
                parsed = parse_flexible_date(date_match.group(0), current_year)
                if parsed:
                    events.append({
                        "title": title,
                        "due_date": parsed,
                        "type": "assignment",
                        "accuracy": 100.0,
                        "is_low_accuracy": False,
                    })

    return events


def parse_flexible_date(date_str: str, default_year: int = None) -> str:
    if default_year is None:
        default_year = datetime.now().year

    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)

    try:
        dt = datetime.strptime(date_str, "%b %d")
        dt = dt.replace(year=default_year)
        return dt.date().isoformat()
    except Exception:
        return None


def _parse_accuracy_value(raw_accuracy) -> float:
    if raw_accuracy is None:
        return 100.0
    if isinstance(raw_accuracy, (int, float)):
        value = float(raw_accuracy)
    elif isinstance(raw_accuracy, str):
        cleaned = raw_accuracy.strip().replace("%", "")
        if not cleaned:
            return 100.0
        try:
            value = float(cleaned)
        except Exception:
            return 100.0
    else:
        return 100.0

    if value < 0:
        return 0.0
    if value > 100:
        return 100.0
    return round(value, 2)


def normalize_extracted_assignments(items: list) -> list:
    normalized = []
    if not isinstance(items, list):
        return normalized

    for item in items:
        if not isinstance(item, dict):
            continue

        title = (item.get("title") or "Untitled").strip()
        due_date = item.get("due_date")
        event_type = (item.get("type") or "assignment").strip().lower()
        accuracy = _parse_accuracy_value(item.get("accuracy"))
        is_low_accuracy = accuracy < LOW_ACCURACY_THRESHOLD

        normalized.append({
            "title": title,
            "due_date": due_date,
            "type": event_type,
            "accuracy": accuracy,
            "is_low_accuracy": is_low_accuracy,
        })

    return normalized


# ----------------------------
# Discord Sharing Helpers
# ----------------------------
def normalize_discord_handle(handle: str) -> str:
    if not handle:
        return ""
    handle = handle.strip()
    if handle.startswith("@"):  # allow @ prefix
        handle = handle[1:]
    return handle.strip()


def build_discord_avatar_url(user_id: str, avatar_hash: str) -> str:
    if not user_id or not avatar_hash:
        return ""
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=128"


# ----------------------------
# OpenRouter (Gemini) Call
# ----------------------------
def call_openrouter_to_extract_assignments(text: str) -> list:

    prompt_system = """
You are replacing a production LLM.

CRITICAL REQUIREMENTS:
- Output MUST be a raw JSON array.
- Do NOT wrap in markdown.
- Do NOT include explanation.
- Do NOT include code fences.
- Do NOT include text before or after JSON.

Required format:

[
  {
    "title": string,
    "due_date": string (YYYY-MM-DD) or null,
    "type": string,
    "accuracy": number
  }
]

"type" must be one of:
assignment, test, quiz, exam, project, presentation, other

Rules:
- Dates must be normalized to YYYY-MM-DD.
- If date cannot be determined, use null.
- "accuracy" is confidence from 0 to 100 for that specific entry.
- Do not include extra fields beyond title, due_date, type, accuracy.
- Do not reorder keys.
- Return [] if nothing found.
"""

    prompt_user = f"""
Extract all course events (assignments, tests, quizzes, exams, projects, presentations, deadlines).

Normalize all dates to YYYY-MM-DD.

Text:
{text}
"""

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "Assignment Extractor"
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": prompt_system.strip()},
                    {"role": "user", "content": prompt_user.strip()}
                ],
                "temperature": 0,
                "max_tokens": 1000
            },
            timeout=60
        )

        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

    except Exception as e:
        raise RuntimeError(f"OpenRouter request failed: {e}")

    # Parse JSON from response
    try:
        raw_items = json.loads(content)
        return normalize_extracted_assignments(raw_items)
    except Exception:
        # Try to extract JSON array from markdown or other wrapper
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1 and end > start:
            snippet = content[start:end + 1]
            try:
                raw_items = json.loads(snippet)
                return normalize_extracted_assignments(raw_items)
            except Exception as e:
                raise RuntimeError(f"Failed to parse JSON from model output: {e}\nOutput was:\n{content}")
        raise RuntimeError(f"Model did not return valid JSON.\nOutput:\n{content}")


# ----------------------------
# Study Plan Generation
# ----------------------------
def call_openrouter_to_generate_study_plan(assignments: list, course_name: str) -> dict:
    """Generate a personalized study plan based on assignments."""
    
    # Format assignments into readable text
    assignments_text = "\n".join([
        f"- {a.get('title', 'Untitled')} ({a.get('type', 'assignment')}): Due {a.get('due_date', 'TBD')}"
        for a in assignments
    ])

    prompt_system = """
You are a helpful academic advisor creating personalized study plans.

CRITICAL REQUIREMENTS:
- Output MUST be a raw JSON object (not wrapped in markdown or code blocks).
- Do NOT include explanation text before or after JSON.
- Do NOT include code fences.

Required format:

{
  "overview": string (brief description of the course study approach),
  "weekly_schedule": [string, string, ...] (array of 4-8 weekly recommendations),
  "study_tips": [string, string, ...] (array of 5-8 practical tips),
  "resource_recommendations": string (recommended resources and tools)
}

Be practical and specific. Base recommendations on the actual assignments provided.
"""

    prompt_user = f"""
Create a personalized study plan for {course_name} based on these assignments:

{assignments_text}

Generate practical, actionable guidance that helps the student succeed in this course.
"""

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "Study Plan Generator"
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": prompt_system.strip()},
                    {"role": "user", "content": prompt_user.strip()}
                ],
                "temperature": 0.7,
                "max_tokens": 2000
            },
            timeout=60
        )

        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

    except Exception as e:
        raise RuntimeError(f"OpenRouter request failed: {e}")

    # Parse JSON from response
    try:
        return json.loads(content)
    except Exception:
        # Try to extract JSON object from markdown or other wrapper
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = content[start:end + 1]
            try:
                return json.loads(snippet)
            except Exception as e:
                raise RuntimeError(f"Failed to parse JSON from model output: {e}\nOutput was:\n{content}")
        raise RuntimeError(f"Model did not return valid JSON.\nOutput:\n{content}")


# ----------------------------
# Google Calendar Helper Functions
# ----------------------------
def get_google_calendar_service():
    """Get authenticated Google Calendar service."""
    creds = None
    
    # Load existing token if available
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
        except Exception:
            pass
    
    # Refresh or create new credentials
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    
    return creds


def save_google_token(creds):
    """Save Google OAuth token to file."""
    with open(TOKEN_FILE, 'wb') as token:
        pickle.dump(creds, token)


def create_google_calendar_event(service, event_title: str, due_date: str, calendar_id: str = "primary"):
    """Create a single event in Google Calendar.
    
    Args:
        service: Authenticated Google Calendar service
        event_title: Title of the event
        due_date: Due date in YYYY-MM-DD format
        calendar_id: Calendar ID (default: primary)
    
    Returns:
        Event object if successful, None otherwise
    """
    try:
        event = {
            'summary': event_title,
            'start': {'date': due_date},
            'end': {'date': due_date},
            'reminders': {
                'useDefault': True,
            }
        }
        
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        
        return created_event
    except Exception as e:
        print(f"Error creating event: {e}")
        return None


def upload_assignments_to_google_calendar(assignments: list, course_name: str, credentials):
    """Upload all assignments to Google Calendar.
    
    Args:
        assignments: List of assignment dicts with 'title' and 'due_date'
        course_name: Name of the course/calendar
        credentials: Google OAuth credentials
    
    Returns:
        Dict with success status and calendar info
    """
    try:
        service = build('calendar', 'v3', credentials=credentials)
        
        # Create a new calendar for this course
        calendar_body = {
            'summary': course_name,
            'description': f'Assignments for {course_name}',
            'timeZone': 'UTC'
        }
        
        calendar = service.calendarList().list().execute()
        existing_calendars = calendar.get('items', [])
        
        # Check if calendar already exists
        calendar_id = None
        for cal in existing_calendars:
            if cal.get('summary') == course_name:
                calendar_id = cal.get('id')
                break
        
        # Create new calendar if it doesn't exist
        if not calendar_id:
            created_calendar = service.calendars().insert(body=calendar_body).execute()
            calendar_id = created_calendar.get('id')
        
        # Add events to calendar
        created_events = 0
        for assignment in assignments:
            title = assignment.get('title', 'Assignment')
            due_date = assignment.get('due_date')
            
            if due_date:
                result = create_google_calendar_event(
                    service, 
                    title, 
                    due_date, 
                    calendar_id
                )
                if result:
                    created_events += 1
        
        return {
            'success': True,
            'calendar_id': calendar_id,
            'calendar_name': course_name,
            'events_created': created_events,
            'total_assignments': len(assignments)
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# ----------------------------
# Routes
# ----------------------------
@app.route("/", methods=["GET"])
def home():
    return render_template("/index.html")


@app.route("/extract_assignments", methods=["POST"])
def extract_assignments():
    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400

    file = request.files["file"]
    filename = file.filename
    pdf_bytes = file.read()
    
    # Generate SHA256 hash of PDF
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    
    # Check cache first (if MongoDB is available)
    if course_collection is not None:
        try:
            cached = course_collection.find_one({"_id": file_hash})
            if cached and "assignments" in cached:
                cached_assignments = normalize_extracted_assignments(cached["assignments"])
                update_fields = {}
                if "created_at" not in cached:
                    update_fields["created_at"] = datetime.utcnow()
                if cached_assignments != cached["assignments"]:
                    update_fields["assignments"] = cached_assignments
                if update_fields:
                    course_collection.update_one(
                        {"_id": file_hash},
                        {"$set": update_fields}
                    )
                print(f"Cache hit for {filename} (hash: {file_hash[:8]}...)")
                return jsonify({
                    "assignments": cached_assignments,
                    "file_hash": file_hash,
                    "study_plans": cached.get("study_plans", {})
                })
        except Exception as e:
            print(f"Cache lookup failed: {e}")
    
    # Extract text from PDF
    text = extract_text_from_pdf_bytes(pdf_bytes)
    if not text.strip():
        return jsonify({"error": "no extractable text"}), 400

    # Extract assignments (using fallback or API)
    if USE_LOCAL_FALLBACK:
        items = normalize_extracted_assignments(parse_events_local(text))
    else:
        items = normalize_extracted_assignments(call_openrouter_to_extract_assignments(text))
    
    # Cache the result (if MongoDB is available)
    if course_collection is not None:
        try:
            course_collection.insert_one({
                "_id": file_hash,
                "filename": filename,
                "assignments": items,
                "study_plans": {},
                "created_at": datetime.utcnow()
            })
            print(f"Cached assignments for {filename} (hash: {file_hash[:8]}...)")
        except DuplicateKeyError:
            print(f"Cache already exists for {filename} (race condition)")
        except Exception as e:
            print(f"Cache save failed: {e}")

    return jsonify({
        "assignments": items,
        "file_hash": file_hash,
        "study_plans": {}
    })


@app.route("/json_to_ics", methods=["POST"])
def json_to_ics_endpoint():
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "expected JSON array"}), 400

    course_name = request.args.get("course_name", "Assignments")

    try:
        ics_content = json_to_ics(data, course_name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return send_file(
        BytesIO(ics_content.encode('utf-8')),
        mimetype="text/calendar",
        as_attachment=True,
        download_name=f"{course_name}.ics"
    )


@app.route("/pdf_to_ics", methods=["POST"])
def pdf_to_ics_endpoint():
    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400

    file = request.files["file"]
    filename = file.filename
    pdf_bytes = file.read()

    # Generate SHA256 hash of PDF
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Check cache first
    if course_collection is not None:
        try:
            cached = course_collection.find_one({"_id": file_hash})
            if cached and "assignments" in cached:
                items = normalize_extracted_assignments(cached["assignments"])
                update_fields = {}
                if "created_at" not in cached:
                    update_fields["created_at"] = datetime.utcnow()
                if items != cached["assignments"]:
                    update_fields["assignments"] = items
                if update_fields:
                    course_collection.update_one(
                        {"_id": file_hash},
                        {"$set": update_fields}
                    )
                print(f"Cache hit for {filename} (hash: {file_hash[:8]}...)")
                course_name = request.args.get("course_name", "Course Assignments")
                ics_content = json_to_ics(items, course_name)
                return send_file(
                    BytesIO(ics_content.encode('utf-8')),
                    mimetype="text/calendar",
                    as_attachment=True,
                    download_name=f"{course_name}.ics"
                )
        except Exception as e:
            print(f"Cache lookup failed: {e}")

    text = extract_text_from_pdf_bytes(pdf_bytes)
    if not text.strip():
        return jsonify({"error": "no extractable text"}), 400

    if USE_LOCAL_FALLBACK:
        items = normalize_extracted_assignments(parse_events_local(text))
    else:
        items = normalize_extracted_assignments(call_openrouter_to_extract_assignments(text))

    # Cache the result
    if course_collection is not None:
        try:
            course_collection.insert_one({
                "_id": file_hash,
                "filename": filename,
                "assignments": items,
                "created_at": datetime.utcnow(),
            })
            print(f"Cached assignments for {filename} (hash: {file_hash[:8]}...)")
        except DuplicateKeyError:
            print(f"Cache already exists for {filename} (race condition)")
        except Exception as e:
            print(f"Cache save failed: {e}")

    course_name = request.args.get("course_name", "Course Assignments")

    ics_content = json_to_ics(items, course_name)

    return send_file(
        BytesIO(ics_content.encode('utf-8')),
        mimetype="text/calendar",
        as_attachment=True,
        download_name=f"{course_name}.ics"
    )


@app.route("/generate_study_plan", methods=["POST"])
def generate_study_plan_endpoint():
    payload = request.get_json()
    
    # Handle both old format (array) and new format (dict with data and file_hash)
    allow_cache = True
    if isinstance(payload, list):
        data = payload
        file_hash = None
    elif isinstance(payload, dict) and "data" in payload:
        data = payload["data"]
        file_hash = payload.get("file_hash")
        allow_cache = payload.get("allow_cache", True)
    else:
        return jsonify({"error": "expected JSON array or object with 'data' key"}), 400

    course_name = request.args.get("course_name", "Course Assignments")

    try:
        # Check cache first if file_hash is provided
        study_plan = None
        generation_assignments = data
        cached_doc = None

        if file_hash and course_collection is not None:
            try:
                cached_doc = course_collection.find_one({"_id": file_hash})
                if allow_cache and cached_doc and "study_plans" in cached_doc and course_name in cached_doc["study_plans"]:
                    print(f"Cache hit for study plan: {course_name} (hash: {file_hash[:8]}...)")
                    study_plan = cached_doc["study_plans"][course_name]

                # If caching is enabled, only allow DB writes from original extracted assignments in Mongo.
                if allow_cache:
                    if cached_doc and "assignments" in cached_doc:
                        generation_assignments = normalize_extracted_assignments(cached_doc["assignments"])
                    else:
                        # No original Gemini extraction available for this hash, so disable cache writes.
                        allow_cache = False
            except Exception as e:
                print(f"Study plan cache lookup failed: {e}")
        
        # Generate study plan if not cached
        if study_plan is None:
            if USE_LOCAL_FALLBACK:
                # Simple fallback: return a basic study plan structure
                study_plan = {
                    "overview": f"Study plan for {course_name}",
                    "weekly_schedule": [
                        "Review syllabus and course materials",
                        "Complete assigned readings",
                        "Work on assignments and projects",
                        "Prepare for exams and quizzes"
                    ],
                    "study_tips": [
                        "Start assignments early to avoid last-minute rush",
                        "Form a study group with classmates",
                        "Review notes regularly, not just before the exam",
                        "Attend office hours if you need clarification",
                        "Take care of your physical and mental health"
                    ],
                    "resource_recommendations": "Take advantage of tutoring services, online resources, and library materials available at your institution."
                }
            else:
                study_plan = call_openrouter_to_generate_study_plan(generation_assignments, course_name)
            
            # Cache the generated study plan
            if allow_cache and file_hash and course_collection is not None:
                try:
                    course_collection.update_one(
                        {"_id": file_hash},
                        {"$set": {f"study_plans.{course_name}": study_plan}},
                        upsert=False
                    )
                    print(f"Cached study plan for {course_name} (hash: {file_hash[:8]}...)")
                except Exception as e:
                    print(f"Study plan cache save failed: {e}")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(study_plan)


@app.route("/share_discord", methods=["POST"])
def share_discord():
    if course_collection is None:
        return jsonify({"error": "database unavailable"}), 503

    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "expected JSON object"}), 400

    file_hash = payload.get("file_hash")
    discord_handle = normalize_discord_handle(payload.get("discord_handle", ""))
    avatar_url = payload.get("avatar_url") or ""

    if not file_hash:
        return jsonify({"error": "missing file_hash"}), 400
    if not discord_handle:
        return jsonify({"error": "missing discord_handle"}), 400
    doc = course_collection.find_one({"_id": file_hash}) or {}
    shared_discords = doc.get("shared_discords", [])
    changed = False

    if "created_at" not in doc:
        changed = True
        doc["created_at"] = datetime.utcnow()

    lower_handle = discord_handle.lower()
    existing_entry = None
    for entry in shared_discords:
        if entry.get("handle", "").lower() == lower_handle:
            existing_entry = entry
            break

    if existing_entry is None:
        shared_discords.append({
            "handle": discord_handle,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "avatar_url": avatar_url,
        })
        changed = True
    elif avatar_url and not existing_entry.get("avatar_url"):
        existing_entry["avatar_url"] = avatar_url
        changed = True

    if changed:
        try:
            course_collection.update_one(
                {"_id": file_hash},
                {"$set": {
                    "shared_discords": shared_discords,
                    "created_at": doc.get("created_at", datetime.utcnow()),
                }},
                upsert=True,
            )
        except Exception as e:
            print(f"share_discord update failed: {e}")
            return jsonify({"error": "database update failed"}), 500

    return jsonify({"shared_discords": shared_discords, "added": existing_entry is None})


@app.route("/shared_discords", methods=["POST"])
def shared_discords():
    if course_collection is None:
        return jsonify({"error": "database unavailable"}), 503

    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "expected JSON object"}), 400

    file_hash = payload.get("file_hash")
    viewer_handle = normalize_discord_handle(payload.get("viewer_handle", ""))

    if not file_hash:
        return jsonify({"error": "missing file_hash"}), 400
    if not viewer_handle:
        return jsonify({"error": "missing viewer_handle"}), 400

    doc = course_collection.find_one({"_id": file_hash}) or {}
    shared_discords_list = doc.get("shared_discords", [])

    viewer_lower = viewer_handle.lower()
    is_opted_in = any(entry.get("handle", "").lower() == viewer_lower for entry in shared_discords_list)
    if not is_opted_in:
        return jsonify({"error": "opt-in required"}), 403

    # Return ALL opted-in users (mark the viewer with is_you)
    unique = {}
    for entry in shared_discords_list:
        handle = entry.get("handle")
        if not handle:
            continue
        key = handle.lower()
        if key not in unique:
            unique[key] = {
                "handle": handle,
                "avatar_url": entry.get("avatar_url", ""),
                "is_you": key == viewer_lower,
            }

    sorted_entries = [unique[key] for key in sorted(unique.keys())]

    return jsonify({"shared_discords": sorted_entries})


@app.route("/discord/oauth/start", methods=["GET"])
def discord_oauth_start():
    if not DISCORD_CLIENT_ID or not DISCORD_REDIRECT_URI or not DISCORD_CLIENT_SECRET:
        return jsonify({"error": "Discord OAuth is not configured"}), 500

    state = secrets.token_urlsafe(16)
    # Store state server-side (avoids cookie/session issues with popups)
    _pending_oauth_states[state] = datetime.utcnow()
    # Clean up states older than 10 minutes
    cutoff = datetime.utcnow()
    expired = [k for k, v in _pending_oauth_states.items() if (cutoff - v).total_seconds() > 600]
    for k in expired:
        _pending_oauth_states.pop(k, None)

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "consent",
    }
    auth_url = "https://discord.com/api/oauth2/authorize?" + urlencode(params)
    return redirect(auth_url)


@app.route("/discord/oauth/callback", methods=["GET"])
def discord_oauth_callback():
    error = request.args.get("error")
    if error:
        return f"Discord OAuth error: {error}", 400

    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state or state not in _pending_oauth_states:
        return "Invalid OAuth state", 400
    _pending_oauth_states.pop(state, None)

    token_response = requests.post(
        "https://discord.com/api/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        },
        timeout=30,
    )

    if not token_response.ok:
        return "Failed to get Discord token", 400

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return "Missing access token", 400

    user_response = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )

    if not user_response.ok:
        return "Failed to fetch Discord user", 400

    user_data = user_response.json()
    username = user_data.get("username", "")
    discriminator = user_data.get("discriminator", "")
    if discriminator and discriminator != "0":
        handle = f"{username}#{discriminator}"
    else:
        handle = username

    avatar_url = build_discord_avatar_url(user_data.get("id"), user_data.get("avatar"))

    html = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <title>Discord Connected</title>
</head>
<body>
  <script>
    (function () {{
      var payload = {{
        type: 'discord-auth',
        handle: {json.dumps(handle)},
        avatar_url: {json.dumps(avatar_url)},
      }};
      try {{
        localStorage.setItem('discord-auth', JSON.stringify(payload));
      }} catch (e) {{}}
      if (window.opener) {{
        try {{ window.opener.postMessage(payload, window.location.origin); }} catch (e) {{}}
      }}
      window.close();
      document.body.textContent = 'Discord connected! You can close this window.';
    }})();
  </script>
</body>
</html>
"""

    return html


@app.route("/download_study_guide", methods=["POST"])
def download_study_guide():
    """Generate and download a study guide as PDF."""
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "expected JSON object"}), 400

    study_plan = payload.get("study_plan")
    assignments = payload.get("assignments", [])
    course_name = payload.get("course_name", "Course")

    if not study_plan:
        return jsonify({"error": "missing study_plan data"}), 400

    try:
        file_bytes = generate_study_guide_pdf(study_plan, course_name, assignments)
        safe_name = course_name.replace(" ", "_")
        return send_file(
            BytesIO(file_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{safe_name}_Study_Guide.pdf"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/google_auth_start", methods=["POST"])
def google_auth_start():
    """Start Google OAuth flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({"error": "Google Calendar not configured"}), 400
    
    try:
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [GOOGLE_REDIRECT_URI]
                }
            },
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI
        )
        
        # Get authorization URL and state
        auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
        
        # Store state in session for callback verification  
        session['oauth_state'] = state
        
        return jsonify({"auth_url": auth_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/oauth2callback", methods=["GET"])
def oauth2callback():
    """Google OAuth callback."""
    auth_code = request.args.get('code')
    state = request.args.get('state')
    
    if not auth_code:
        return jsonify({"error": "No authorization code"}), 400
    
    # Verify state matches
    if state != session.get('oauth_state'):
        return jsonify({"error": "State mismatch"}), 400
    
    try:
        # Recreate flow with redirect_uri
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [GOOGLE_REDIRECT_URI]
                }
            },
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI
        )
        
        # Exchange code for credentials
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials
        
        # Save token for future use
        save_google_token(credentials)
        
        return redirect(f"/?success=true")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/get_calendar_events", methods=["POST"])
def get_calendar_events():
    """Get events from a Google Calendar."""
    payload = request.get_json()
    calendar_id = payload.get("calendar_id", "primary")
    
    try:
        creds = get_google_calendar_service()
        if not creds:
             return jsonify({
                "error": "not_authenticated",
                "message": "Please authenticate with Google first"
            }), 401
        
        service = build('calendar', 'v3', credentials=creds)
        
        # Get events for the next year
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=now,
            maxResults=250, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        
        return jsonify({"events": events, "calendar_id": calendar_id})
    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/upload_to_google_calendar", methods=["POST"])
def upload_to_google_calendar():
    """Upload assignments to Google Calendar."""
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "expected JSON object"}), 400
    
    assignments = payload.get("assignments", [])
    course_name = payload.get("course_name", "Assignments")
    
    if not assignments:
        return jsonify({"error": "no assignments provided"}), 400
    
    try:
        # Check for existing credentials
        creds = get_google_calendar_service()
        
        if not creds:
            # Need to initiate auth flow
            return jsonify({
                "error": "not_authenticated",
                "message": "Please authenticate with Google first"
            }), 401
        
        # Upload assignments to Google Calendar
        result = upload_assignments_to_google_calendar(assignments, course_name, creds)
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 500
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/check_google_auth", methods=["GET"])
def check_google_auth():
    """Check if user is authenticated with Google."""
    try:
        creds = get_google_calendar_service()
        is_authenticated = creds is not None and not creds.expired
        
        return jsonify({
            "authenticated": is_authenticated,
            "client_id": GOOGLE_CLIENT_ID is not None
        })
    except Exception as e:
        return jsonify({"authenticated": False, "error": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

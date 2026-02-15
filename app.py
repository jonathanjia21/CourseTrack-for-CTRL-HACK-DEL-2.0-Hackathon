import os
import json
import re
from io import BytesIO
from datetime import datetime
import hashlib
import requests
from flask import Flask, request, jsonify, send_file, render_template, redirect, url_for, session
from flask_cors import CORS
import pdfplumber
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import pickle

from backend.ics_converter import json_to_ics
from backend.config.mongo import course_collection
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

# ----------------------------
# OpenRouter Configuration
# ----------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-pro")

USE_LOCAL_FALLBACK = os.getenv("USE_LOCAL_FALLBACK", "true").lower() == "true"


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
                        "type": "assignment"
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


def parse_date_yyyy_mm_dd(date_str: str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None


def prune_expired_discords(shared_discords: list) -> tuple[list, bool]:
    if not shared_discords:
        return [], False
    today = datetime.utcnow().date()
    active = []
    changed = False
    for entry in shared_discords:
        term_end_str = entry.get("term_end")
        term_end = parse_date_yyyy_mm_dd(term_end_str)
        if term_end and term_end < today:
            changed = True
            continue
        active.append(entry)
    return active, changed


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
    "type": string
  }
]

"type" must be one of:
assignment, test, quiz, exam, project, presentation, other

Rules:
- Dates must be normalized to YYYY-MM-DD.
- If date cannot be determined, use null.
- Do not include extra fields.
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
        return json.loads(content)
    except Exception:
        # Try to extract JSON array from markdown or other wrapper
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1 and end > start:
            snippet = content[start:end + 1]
            try:
                return json.loads(snippet)
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
                print(f"Cache hit for {filename} (hash: {file_hash[:8]}...)")
                return jsonify({
                    "assignments": cached["assignments"],
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
        items = parse_events_local(text)
    else:
        items = call_openrouter_to_extract_assignments(text)
    
    # Cache the result (if MongoDB is available)
    if course_collection is not None:
        try:
            course_collection.insert_one({
                "_id": file_hash,
                "filename": filename,
                "assignments": items,
                "study_plans": {}
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
                print(f"Cache hit for {filename} (hash: {file_hash[:8]}...)")
                items = cached["assignments"]
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
        items = parse_events_local(text)
    else:
        items = call_openrouter_to_extract_assignments(text)

    # Cache the result
    if course_collection is not None:
        try:
            course_collection.insert_one({
                "_id": file_hash,
                "filename": filename,
                "assignments": items,
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
    if isinstance(payload, list):
        data = payload
        file_hash = None
    elif isinstance(payload, dict) and "data" in payload:
        data = payload["data"]
        file_hash = payload.get("file_hash")
    else:
        return jsonify({"error": "expected JSON array or object with 'data' key"}), 400

    course_name = request.args.get("course_name", "Course Assignments")

    try:
        # Check cache first if file_hash is provided
        study_plan = None
        if file_hash and course_collection is not None:
            try:
                cached = course_collection.find_one({"_id": file_hash})
                if cached and "study_plans" in cached and course_name in cached["study_plans"]:
                    print(f"Cache hit for study plan: {course_name} (hash: {file_hash[:8]}...)")
                    study_plan = cached["study_plans"][course_name]
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
                study_plan = call_openrouter_to_generate_study_plan(data, course_name)
            
            # Cache the generated study plan
            if file_hash and course_collection is not None:
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
    term_end = payload.get("term_end") or None

    if not file_hash:
        return jsonify({"error": "missing file_hash"}), 400
    if not discord_handle:
        return jsonify({"error": "missing discord_handle"}), 400
    if term_end and not parse_date_yyyy_mm_dd(term_end):
        return jsonify({"error": "term_end must be YYYY-MM-DD"}), 400

    doc = course_collection.find_one({"_id": file_hash}) or {}
    shared_discords = doc.get("shared_discords", [])
    shared_discords, changed = prune_expired_discords(shared_discords)

    lower_handle = discord_handle.lower()
    existing = any(entry.get("handle", "").lower() == lower_handle for entry in shared_discords)
    if not existing:
        shared_discords.append({
            "handle": discord_handle,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "term_end": term_end,
        })
        changed = True

    if changed:
        course_collection.update_one(
            {"_id": file_hash},
            {"$set": {"shared_discords": shared_discords}},
            upsert=True
        )

    return jsonify({"shared_discords": shared_discords, "added": not existing})


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
    shared_discords_list, changed = prune_expired_discords(shared_discords_list)
    if changed:
        course_collection.update_one(
            {"_id": file_hash},
            {"$set": {"shared_discords": shared_discords_list}},
            upsert=True
        )

    viewer_lower = viewer_handle.lower()
    is_opted_in = any(entry.get("handle", "").lower() == viewer_lower for entry in shared_discords_list)
    if not is_opted_in:
        return jsonify({"error": "opt-in required"}), 403

    handles = [
        entry.get("handle")
        for entry in shared_discords_list
        if entry.get("handle") and entry.get("handle").lower() != viewer_lower
    ]
    handles = sorted(set(handles), key=str.lower)

    return jsonify({"shared_discords": handles})


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

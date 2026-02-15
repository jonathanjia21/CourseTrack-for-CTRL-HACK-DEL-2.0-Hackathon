import os
import json
import re
from io import BytesIO
from datetime import datetime
import hashlib
import requests
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pdfplumber
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

from backend.ics_converter import json_to_ics
from backend.config.mongo import course_collection

load_dotenv()

app = Flask(__name__)
CORS(app)

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
            cached = course_collection.find_one({"file_hash": file_hash})
            if cached and "assignments" in cached:
                print(f"Cache hit for {filename} (hash: {file_hash[:8]}...)")
                return jsonify(cached["assignments"])
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
                "file_hash": file_hash,
                "filename": filename,
                "assignments": items,
                "extracted_at": datetime.utcnow(),
                "method": "local" if USE_LOCAL_FALLBACK else "api"
            })
            print(f"Cached assignments for {filename} (hash: {file_hash[:8]}...)")
        except DuplicateKeyError:
            print(f"Cache already exists for {filename} (race condition)")
        except Exception as e:
            print(f"Cache save failed: {e}")

    return jsonify(items)


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
    pdf_bytes = file.read()

    file_hash = hashlib.md5(pdf_bytes).hexdigest()

    text = extract_text_from_pdf_bytes(pdf_bytes)
    if not text.strip():
        return jsonify({"error": "no extractable text"}), 400

    if USE_LOCAL_FALLBACK:
        items = parse_events_local(text)
    else:
        items = call_openrouter_to_extract_assignments(text, file_hash)

    course_name = request.args.get("course_name", "Course Assignments")

    ics_content = json_to_ics(items, course_name)

    return send_file(
        BytesIO(ics_content.encode('utf-8')),
        mimetype="text/calendar",
        as_attachment=True,
        download_name=f"{course_name}.ics"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

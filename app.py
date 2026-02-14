import os
import json
import re
from io import BytesIO
from datetime import datetime

from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv
from backend.ics_converter import json_to_ics

load_dotenv()  # Load .env file

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Use Featherless.AI (OpenAI-compatible API)
client = OpenAI(
    api_key=os.getenv("FEATHERLESS_API_KEY"),
    base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
)

USE_LOCAL_FALLBACK = os.getenv("USE_LOCAL_FALLBACK", "true").lower() == "true"


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


def parse_assignments_local(text: str) -> list:
    """Local regex-based assignment extraction (fallback when API is unavailable)"""
    assignments = []
    
    # Pattern for common assignment keywords followed by potential dates
    # Matches: A1, A2, Assignment 1, Homework 1, Project, Quiz, etc.
    assignment_pattern = r'(?:^|\n)\s*([A-Z][0-9]+|Assignment\s+[0-9]+|Homework\s+[0-9]+|Project(?:\s+\w+)?|Quiz(?:\s+\w+)?)\s+.*?(\w+\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})'
    
    # Also look for grading tables with Component/Due/Date columns
    lines = text.split('\n')
    in_table = False
    current_year = datetime.now().year
    
    for i, line in enumerate(lines):
        # Check if we're in a grading table
        if re.search(r'Component.*Due.*Percentage', line, re.IGNORECASE):
            in_table = True
            continue
        
        if in_table:
            # Stop at empty lines or section breaks
            if not line.strip() or re.match(r'^[A-Z][a-z]+\s+[A-Z]', line):
                in_table = False
                continue
            
            # Parse table rows: "A1 Jan 28th Feb 13th 13%"
            parts = line.split()
            if len(parts) >= 3:
                title = parts[0]
                # Look for month patterns
                for j, part in enumerate(parts[1:], 1):
                    if re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', part, re.IGNORECASE):
                        # Next parts might be: 28th, Feb, 13th or just 28th
                        date_str = ' '.join(parts[j:min(j+3, len(parts))])
                        try:
                            # Try to parse date
                            parsed_date = parse_flexible_date(date_str, current_year)
                            if parsed_date:
                                assignments.append({
                                    "title": title,
                                    "due_date": parsed_date
                                })
                                break
                        except Exception:
                            continue
    
    return assignments


def parse_flexible_date(date_str: str, default_year: int = None) -> str:
    """Parse various date formats and return ISO format YYYY-MM-DD"""
    if default_year is None:
        default_year = datetime.now().year
    
    # Clean up the string
    date_str = date_str.strip()
    
    # Try various formats
    formats = [
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
    ]
    
    # Handle "Feb 13th" => "Feb 13"
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.date().isoformat()
        except Exception:
            continue
    
    # Try month + day without year
    match = re.match(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})', date_str, re.IGNORECASE)
    if match:
        try:
            month_str = match.group(1)
            day_str = match.group(2)
            month_num = datetime.strptime(month_str, '%b').month
            dt = datetime(default_year, month_num, int(day_str))
            return dt.date().isoformat()
        except Exception:
            pass
    
    return None


def call_openai_to_extract_assignments(text: str) -> list:
    prompt_system = (
        "You are an assistant that extracts assignment titles and due dates from raw document text. "
        "Respond with a JSON array only, where each item is an object with `title` and `due_date`. "
        "`due_date` must be in ISO format `YYYY-MM-DD` or `null` if unknown. "
        "Do not add any extra explanation or wrapper text."
    )

    prompt_user = (
        "Extract assignment titles and their due dates from the following text. "
        "If a date is written in words or multiple formats, normalize it to YYYY-MM-DD. "
        f"Text:\n\n{text}"
    )

    try:
        resp = client.chat.completions.create(
            model=os.getenv("FEATHERLESS_MODEL", "meta-llama/Llama-3.2-3B-Instruct"),
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user},
            ],
            temperature=0,
            max_tokens=700,
        )
        content = resp.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"Featherless.AI request failed: {e}")

    # Try to parse JSON directly; if model returned text around JSON, extract the JSON substring.
    try:
        return json.loads(content)
    except Exception:
        # crude extraction of JSON array
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1 and end > start:
            snippet = content[start:end + 1]
            try:
                return json.loads(snippet)
            except Exception as e:
                raise RuntimeError(f"Failed to parse JSON from model output: {e}\nOutput was:\n{content}")
        raise RuntimeError(f"Model did not return valid JSON. Output:\n{content}")


@app.route("/", methods=["GET"])
def home():
    return render_template("/index.html")

@app.route("/extract_assignments", methods=["POST"])
def extract_assignments():
    if "file" not in request.files:
        return jsonify({"error": "missing file (form field 'file')"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400

    pdf_bytes = None
    try:
        pdf_bytes = file.read()
    except Exception:
        return jsonify({"error": "could not read uploaded file"}), 400

    if not pdf_bytes:
        return jsonify({"error": "empty file"}), 400

    text = extract_text_from_pdf_bytes(pdf_bytes)
    if not text.strip():
        return jsonify({"error": "no extractable text in PDF"}), 400

    # Use local fallback or API
    if USE_LOCAL_FALLBACK:
        items = parse_assignments_local(text)
    else:
        try:
            items = call_openai_to_extract_assignments(text)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500

    # Basic validation & normalization: ensure due_date is ISO or null
    cleaned = []
    for it in items:
        title = it.get("title") if isinstance(it, dict) else None
        due = it.get("due_date") if isinstance(it, dict) else None
        if not title:
            continue
        if due is None:
            due_iso = None
        else:
            # try to parse YYYY-MM-DD or coerce
            try:
                # if already ISO-like, accept it
                due_dt = datetime.fromisoformat(due)
                due_iso = due_dt.date().isoformat()
            except Exception:
                # fallback: try to parse common formats with datetime.strptime attempts
                parsed = None
                for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                    try:
                        parsed = datetime.strptime(due, fmt)
                        break
                    except Exception:
                        continue
                if parsed:
                    due_iso = parsed.date().isoformat()
                else:
                    due_iso = None
        cleaned.append({"title": title, "due_date": due_iso})

    return jsonify(cleaned)


@app.route("/json_to_ics", methods=["POST"])
def json_to_ics_endpoint():
    """Convert JSON assignments to ICS calendar file"""
    try:
        data = request.get_json()
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400
    
    if not isinstance(data, list):
        return jsonify({"error": "expected JSON array of assignments"}), 400
    
    course_name = request.args.get("course_name", "Assignments")
    
    try:
        ics_content = json_to_ics(data, course_name)
    except Exception as e:
        return jsonify({"error": f"ICS conversion failed: {e}"}), 500
    
    return send_file(
        BytesIO(ics_content.encode('utf-8')),
        mimetype="text/calendar",
        as_attachment=True,
        download_name=f"{course_name}.ics"
    )


@app.route("/pdf_to_ics", methods=["POST"])
def pdf_to_ics_endpoint():
    """Extract assignments from PDF and return as ICS calendar file"""
    if "file" not in request.files:
        return jsonify({"error": "missing file (form field 'file')"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400

    pdf_bytes = None
    try:
        pdf_bytes = file.read()
    except Exception:
        return jsonify({"error": "could not read uploaded file"}), 400

    if not pdf_bytes:
        return jsonify({"error": "empty file"}), 400

    text = extract_text_from_pdf_bytes(pdf_bytes)
    if not text.strip():
        return jsonify({"error": "no extractable text in PDF"}), 400

    # Use local fallback or API
    if USE_LOCAL_FALLBACK:
        items = parse_assignments_local(text)
    else:
        try:
            items = call_openai_to_extract_assignments(text)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500

    # Validate and normalize dates
    cleaned = []
    for it in items:
        title = it.get("title") if isinstance(it, dict) else None
        due = it.get("due_date") if isinstance(it, dict) else None
        if not title:
            continue
        if due is None:
            due_iso = None
        else:
            try:
                due_dt = datetime.fromisoformat(due)
                due_iso = due_dt.date().isoformat()
            except Exception:
                parsed = None
                for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                    try:
                        parsed = datetime.strptime(due, fmt)
                        break
                    except Exception:
                        continue
                if parsed:
                    due_iso = parsed.date().isoformat()
                else:
                    due_iso = None
        cleaned.append({"title": title, "due_date": due_iso})

    # Generate ICS
    course_name = request.args.get("course_name", "Course Assignments")
    try:
        ics_content = json_to_ics(cleaned, course_name)
    except Exception as e:
        return jsonify({"error": f"ICS conversion failed: {e}"}), 500

    return send_file(
        BytesIO(ics_content.encode('utf-8')),
        mimetype="text/calendar",
        as_attachment=True,
        download_name=f"{course_name}.ics"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

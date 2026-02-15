# CourseTrack

CourseTrack turns course syllabi into actionable academic calendars.
Upload a syllabus PDF, extract deadlines with AI-assisted parsing, review/edit results, export an `.ics` file, and optionally sync that calendar to Google Calendar after signing in with Google OAuth.

## ✨ Features

- **Syllabus → structured events** from PDF uploads (assignments, quizzes, exams, projects, presentations).
- **Interactive review flow** to confirm and edit extracted events before export.
- **ICS generation** for easy import into Google Calendar, Apple Calendar, Outlook, and more.
- **Google OAuth login (optional)** so users can authenticate with Google and sync generated `.ics` events to Google Calendar.
- **Discord opt-in classmate discovery** (users can share Discord handles for matching syllabus hashes).
- **Study plan generation** from extracted course deadlines.
- **Study guide PDF generation** from selected assignments.

## 🧱 Tech Stack

- **Backend:** Flask, Python
- **Frontend:** HTML, CSS, vanilla JavaScript
- **Parsing & extraction:** `pdfplumber` + LLM extraction via OpenRouter
- **Storage:** MongoDB
- **Calendar:** iCalendar (`.ics`) generation + Google Calendar sync flow (OAuth)

## 📁 Project Structure

```text
.
├── app.py                     # Flask app + API routes
├── backend/
│   ├── ics_converter.py       # JSON events -> .ics conversion
│   ├── study_guide_generator.py
│   └── config/mongo.py        # MongoDB configuration
├── static/                    # Frontend JS/CSS
├── templates/                 # HTML templates
└── requirements.txt
```

## 🚀 Getting Started

### 1) Clone and install dependencies

```bash
git clone <your-repo-url>
cd CourseTrack-for-CTRL-HACK-DEL-2.0-Hackathon
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Configure environment variables

Create a `.env` file in the project root:

```env
# LLM extraction
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=google/gemini-pro

# MongoDB
MONGO_URI=your_mongodb_connection_string

# Discord OAuth
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
DISCORD_REDIRECT_URI=http://localhost:5000/discord/oauth/callback

# Google OAuth + Calendar sync
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5000/google/oauth/callback
GOOGLE_CALENDAR_ID=primary

# Optional behavior
USE_LOCAL_FALLBACK=true
```

> If Google OAuth variables are not provided, users can still use CourseTrack and download `.ics` files manually.

### 3) Run the app

```bash
python app.py
```

Then open: `http://localhost:5000`

## 🔄 Typical User Flow

1. Upload one or more syllabus PDFs.
2. CourseTrack extracts deadlines and event types.
3. User reviews/edits selected events.
4. User generates and downloads `.ics` calendar file.
5. *(Optional)* User logs in with Google and syncs generated calendar events directly to Google Calendar.


## 🧪 Development Notes

- Reduced API usage by detecting previously processed PDF's from their hash value. This hash value is the id within the database, i.e. if a duplicate course syllabus is uploaded a new API call is not made.
- Extraction quality depends on syllabus formatting and OCR quality.
- Keep `OPENROUTER_API_KEY` and OAuth client secrets out of source control.
- For production, add robust auth/session handling, rate limits, and input validation hardening.

---


Built for **CTRL HACK DEL 2.0 Hackathon**.

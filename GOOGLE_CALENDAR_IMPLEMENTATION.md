# Google Calendar Integration Implementation Guide

## Overview
This document outlines the step-by-step implementation of Google Calendar integration into CourseTrack. The feature allows users to upload extracted assignments directly to their Google Calendar without breaking existing functionality.

## Changes Made

### 1. **Dependencies Added** (`requirements.txt`)
- `google-auth-oauthlib>=1.0` - OAuth authentication for Google
- `google-auth-httplib2>=0.1` - HTTP transport for Google auth
- `google-api-python-client>=2.80` - Google Calendar API client

### 2. **Backend Implementation** (`app.py`)

#### New Imports
```python
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle
```

#### New Configuration (after app initialization)
```python
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# Google Calendar Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5000/oauth2callback")
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.json"
```

#### New Helper Functions

1. **`get_google_calendar_service()`**
   - Loads OAuth token from `token.json`
   - Refreshes expired tokens
   - Returns authenticated service or None

2. **`save_google_token(creds)`**
   - Saves OAuth credentials to `token.json` for future use

3. **`create_google_calendar_event(service, event_title, due_date, calendar_id)`**
   - Creates individual events in Google Calendar
   - Supports all-day events on due dates

4. **`upload_assignments_to_google_calendar(assignments, course_name, credentials)`**
   - Creates a calendar for the course (or uses existing)
   - Uploads all checked assignments as events
   - Returns status with number of events created

#### New Flask Routes

1. **`POST /google_auth_start`**
   - Initiates OAuth flow
   - Returns Google login URL
   - Stores flow in session

2. **`GET /oauth2callback`**
   - OAuth callback endpoint
   - Exchanges auth code for credentials
   - Saves token to `token.json`
   - Redirects back to home page

3. **`POST /upload_to_google_calendar`**
   - Receives assignments and course name
   - Checks for existing authentication
   - Uploads assignments to Google Calendar
   - Returns success status or 401 if not authenticated

4. **`GET /check_google_auth`**
   - Checks if user has valid Google credentials
   - Returns authentication status

### 3. **Frontend Implementation**

#### HTML Changes (`templates/index.html`)
```html
<!-- Success Modal Updated -->
<div class="success-options">
    <div class="success-option">
        <h3>📅 Upload to Google Calendar</h3>
        <p>Add your assignments directly to your Google Calendar</p>
        <button class="btn-primary" id="uploadGoogleCalendar">
            Upload to Google Calendar
        </button>
    </div>
    <div class="success-option">
        <h3>📖 Generate Study Plan</h3>
        <p>Get a personalized study guide for your course</p>
        <button class="btn-primary" id="generateStudyPlan">
            Generate Study Plan
        </button>
    </div>
</div>
```

#### JavaScript Changes (`static/js/index.js`)

1. **DOM Elements Added**
   - `uploadGoogleCalendar` button reference
   - `currentCourseNameForCalendar` variable to track course name

2. **Upload Handler** (`uploadGoogleCalendar.addEventListener`)
   - Checks authentication status via `/check_google_auth`
   - If not authenticated, redirects to Google login
   - If authenticated, uploads assignments
   - Shows success message with event count
   - Handles errors gracefully

3. **Course Name Tracking**
   - Modified `confirmGenerate` to store `currentCourseNameForCalendar`
   - Used when uploading to Google Calendar

#### CSS Changes (`static/css/index.css`)

Added new styles for the updated success modal:
- `.success-options` - Grid layout for two-column option cards
- `.success-option` - Individual option styling with border and background
- Responsive design (single column on mobile)
- Maintains consistent design language

### 4. **Configuration Files**

#### Environment Variables Required (`.env`)
```env
GOOGLE_CLIENT_ID=your_client_id_from_google_console
GOOGLE_CLIENT_SECRET=your_client_secret_from_google_console
GOOGLE_REDIRECT_URI=http://localhost:5000/oauth2callback
SECRET_KEY=your-secret-key-for-session
```

#### .gitignore Update
Added `token.json` to prevent accidental credential commits

## Workflow

1. **User uploads PDF and clicks "Generate Calendar"**
   - Existing functionality unchanged
   - Preview modal shows assignments
   - User selects assignments to include
   - ICS file is generated and downloaded

2. **Success Modal Displays**
   - Two options shown:
     - "Upload to Google Calendar" (NEW)
     - "Generate Study Plan" (existing)
   - "Skip for Now" button (existing)

3. **User Clicks "Upload to Google Calendar"**
   - Frontend checks `/check_google_auth`
   - If not authenticated:
     - Frontend calls `/google_auth_start`
     - Gets authorization URL
     - Redirects user to Google login
     - User grants permissions
     - OAuth callback saves token
     - Returns to page with success indicator
   - If authenticated:
     - Calls `/upload_to_google_calendar`
     - Backend creates course calendar (if new)
     - Uploads all checked assignments as events
     - Shows success message

## Setup Instructions

See [GOOGLE_CALENDAR_SETUP.md](GOOGLE_CALENDAR_SETUP.md) for detailed setup instructions including:
- Creating Google Cloud Project
- Enabling Google Calendar API
- Setting up OAuth 2.0 credentials
- Configuring environment variables

## Current Functionality Preserved

✅ PDF upload and parsing
✅ Assignment extraction
✅ Preview and selection
✅ ICS file generation and download
✅ Study plan generation
✅ Discord sharing
✅ All existing database operations

## New Functionality

✅ Google OAuth authentication
✅ Google Calendar API integration
✅ Automatic calendar creation
✅ Assignment upload to Google Calendar
✅ Token caching for seamless reuse

## Testing Recommendations

1. **Local Testing**
   - Test without Google credentials (should show auth redirect)
   - Test with valid credentials
   - Verify calendar creation in Google Calendar
   - Verify events appear on correct dates

2. **Edge Cases**
   - Test with duplicate calendar names
   - Test with courses that have no due dates
   - Test with expired credentials (should refresh)
   - Test with very long assignment titles

3. **Integration Testing**
   - Full workflow: PDF → ICS → Google Calendar
   - Study plan generation + Google Calendar upload
   - Discord sharing + Google Calendar upload
   - Multiple file uploads

## Notes

- First-time authentication requires user interaction (OAuth flow)
- Subsequent uploads use cached token (stored in `token.json`)
- Token is automatically refreshed if expired
- User can revoke access in Google Account settings
- Calendar names prevent duplicates by checking existing calendars
- All events created as all-day events (matching ICS format)

## Future Enhancements

- Display embedded Google Calendar on page
- Allow users to select existing calendar during upload
- Add sync confirmation with calendar preview
- Support recurring events
- Add calendar color customization
- Implement token revocation endpoint

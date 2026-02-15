# Google Calendar API Endpoints Reference

## Overview
All new endpoints support the existing CourseTrack functionality while adding Google Calendar integration.

---

## New Endpoints

### 1. POST `/google_auth_start`
**Purpose**: Initiate Google OAuth authentication flow

**Request Body**: None (empty POST)

**Response (200 OK)**:
```json
{
    "auth_url": "https://accounts.google.com/o/oauth2/auth?..."
}
```

**Response (400 Bad Request)**:
```json
{
    "error": "Google Calendar not configured"
}
```

**Usage**:
- Called when user clicks "Upload to Google Calendar" without existing credentials
- Frontend redirects user to returned auth_url
- User logs in and grants calendar permissions
- Redirected back to `/oauth2callback`

---

### 2. GET `/oauth2callback`
**Purpose**: Google OAuth callback endpoint - handles authentication response

**Query Parameters**:
- `code` (string): Authorization code from Google
- `state` (string): State parameter for CSRF protection

**Response (302 Redirect)**:
Redirects to `/?google_auth_success=true`

**Response (400 Bad Request)**:
```json
{
    "error": "No authorization code"
}
```

**Response (400 Bad Request)**:
```json
{
    "error": "Session expired"
}
```

**Backend Behavior**:
- Exchanges authorization code for credentials
- Saves credentials to `token.json`
- Stores in Flask session for current request
- Redirects back to home page

---

### 3. POST `/upload_to_google_calendar`
**Purpose**: Upload extracted assignments to Google Calendar

**Request Body**:
```json
{
    "assignments": [
        {
            "title": "Assignment Title",
            "due_date": "2024-02-20",
            "type": "assignment",
            "source": "syllabus.pdf"
        }
    ],
    "course_name": "EECS 2101"
}
```

**Response (200 OK)**:
```json
{
    "success": true,
    "calendar_id": "primary",
    "calendar_name": "EECS 2101",
    "events_created": 8,
    "total_assignments": 10
}
```

**Response (401 Unauthorized)**:
```json
{
    "error": "not_authenticated",
    "message": "Please authenticate with Google first"
}
```

**Response (400 Bad Request)**:
```json
{
    "error": "expected JSON object"
}
```

**Response (400 Bad Request)**:
```json
{
    "error": "no assignments provided"
}
```

**Response (500 Internal Server Error)**:
```json
{
    "error": "Error message from Google API"
}
```

**Backend Behavior**:
1. Validates request format and required fields
2. Retrieves stored Google credentials
3. Creates/finds calendar for course name
4. Creates events for each assignment with due_date
5. Returns count of successfully created events

**Notes**:
- Only assignments with valid `due_date` are uploaded
- Calendar name prevents duplicates (checks existing calendars)
- All events created as all-day events
- Automatically refreshes token if expired

---

### 4. GET `/check_google_auth`
**Purpose**: Check if user has valid Google authentication

**Request**: None required

**Response (200 OK - Authenticated)**:
```json
{
    "authenticated": true,
    "client_id": true
}
```

**Response (200 OK - Not Authenticated)**:
```json
{
    "authenticated": false,
    "client_id": true
}
```

**Response (200 OK - Not Configured)**:
```json
{
    "authenticated": false,
    "client_id": false
}
```

**Frontend Usage**:
- Called before attempting to upload
- If `authenticated: false` and `client_id: true`, redirect to login
- If `client_id: false`, show configuration error

---

## Implementation Flow

### First-Time Authorization
```
┌─────────────┐
│   Frontend  │
└──────┬──────┘
       │ 1. POST /check_google_auth
       ├──────────────────────────>│ Backend │
       │                           └────┬────┘
       │ 2. Returns authenticated=false  │
       │<────────────────────────────────┘
       │
       │ 3. POST /google_auth_start
       ├──────────────────────────>│ Backend │
       │                           └────┬────┘
       │ 4. Returns auth_url             │
       │<────────────────────────────────┘
       │
       │ 5. Redirect to auth_url
       ├──────────────────────────> Google OAuth
       │                           
       │ 6. User logs in & grants access
       │
       │ 7. Redirect to /oauth2callback
       ├──────────────────────────>│ Backend │
       │                           └────┬────┘
       │ 8. Save token.json              │
       │ 9. Redirect to /?success        │
       │<────────────────────────────────┘
```

### Subsequent Uploads (with cached token)
```
┌─────────────┐
│   Frontend  │
└──────┬──────┘
       │ 1. POST /check_google_auth
       ├──────────────────────────>│ Backend │
       │                           └────┬────┘
       │ 2. Returns authenticated=true   │
       │<────────────────────────────────┘
       │
       │ 3. POST /upload_to_google_calendar
       ├──────────────────────────>│ Backend │
       │                           └────┬────┘
       │ 4. Create/find calendar         │
       │ 5. Upload events                │
       │ 6. Return success               │
       │<────────────────────────────────┘
```

---

## Data Models

### Assignment Object
Used in upload requests:
```json
{
    "title": "string - assignment name",
    "due_date": "string - YYYY-MM-DD format",
    "type": "string - assignment|test|quiz|exam|project|presentation|other",
    "source": "string - original filename",
    "file_hash": "string - optional, for caching"
}
```

### Google Calendar Event
Created from assignment:
- **Summary**: Assignment title (with course code prefix)
- **Start Date**: Assignment due_date
- **End Date**: Assignment due_date
- **Type**: All-day event
- **Calendar**: Course-specific calendar

---

## Error Handling

### Authentication Errors
- **401 Unauthorized**: Token invalid or expired - return to auth flow
- **403 Forbidden**: Insufficient permissions - request new auth

### Validation Errors
- **400 Bad Request**: Invalid JSON or missing required fields
- **400 Bad Request**: No assignments provided

### Calendar Errors
- **500 Internal Server Error**: Google API failures
- **500 Internal Server Error**: Calendar creation failures

---

## Security Considerations

1. **Token Storage**
   - Tokens stored locally in `token.json`
   - Not in version control (added to .gitignore)
   - Consider using secure storage in production

2. **CSRF Protection**
   - Flask sessions prevent CSRF attacks
   - State parameter validated by OAuth library

3. **Scope Limitation**
   - Only `https://www.googleapis.com/auth/calendar` requested
   - Users know exactly what permission is granted

4. **User Consent**
   - OAuth flow requires explicit user consent
   - Users can revoke access in Google Account settings

---

## Testing

### Manual Testing
```bash
# Check authentication
curl http://localhost:5000/check_google_auth

# Initiate auth
curl -X POST http://localhost:5000/google_auth_start

# Upload assignments (requires valid token.json)
curl -X POST http://localhost:5000/upload_to_google_calendar \
  -H "Content-Type: application/json" \
  -d '{
    "assignments": [{"title": "Homework 1", "due_date": "2024-02-20"}],
    "course_name": "EECS 2101"
  }'
```

### Integration Testing
1. Complete full workflow with fresh browser session
2. Test token expiration and refresh
3. Test with multiple courses
4. Test with assignments missing due dates
5. Test authorization revocation

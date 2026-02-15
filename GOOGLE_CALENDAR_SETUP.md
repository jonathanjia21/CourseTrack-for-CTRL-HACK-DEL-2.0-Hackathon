# Google Calendar Integration Setup

This guide walks you through setting up Google Calendar API integration with CourseTrack.

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (click the project dropdown at the top)
3. Name it "CourseTrack" or similar
4. Wait for the project to be created

## Step 2: Enable Google Calendar API

1. In the Google Cloud Console, search for "Google Calendar API"
2. Click on it and select "Enable"
3. Wait for it to be enabled

## Step 3: Create OAuth 2.0 Credentials

1. Go to "Credentials" in the left sidebar
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure the OAuth consent screen first:
   - Choose "External" as the user type
   - Fill in the app name: "CourseTrack"
   - Add your email as a test user
4. After setting up the consent screen, create the OAuth client ID:
   - Application type: **Web application**
   - Name: "CourseTrack Web"
   - Authorized JavaScript origins: `http://localhost:5000`
   - Authorized redirect URIs: 
     - `http://localhost:5000/auth/google/callback`
     - `http://localhost:5000/oauth2callback`
5. Copy the Client ID and Client Secret

## Step 4: Set Environment Variables

Add these to your `.env` file:

```
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:5000/oauth2callback
```

## Step 5: Token Storage

The app will automatically create a `token.json` file to store OAuth tokens. This file should be added to `.gitignore` to keep credentials private.

## Testing

Once configured, the "Upload to Google Calendar" button will appear in the success modal after generating a calendar. Users can click it to:
1. Authenticate with their Google account (first time only)
2. Create a new calendar or select an existing one
3. Upload their extracted assignments to Google Calendar

## Notes

- First-time users will be redirected to Google to authorize the app
- Subsequent uploads won't require re-authentication (token is cached)
- Users can revoke access in their Google Account settings
- The app creates events as all-day events on the due dates

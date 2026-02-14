# CourseTrack Frontend

Simple HTML/CSS/JavaScript frontend for converting syllabi PDFs to calendar files.

## Features

- 📄 Drag-and-drop PDF upload
- 📋 Optional course name input
- ⬇️ Automatic .ics file download
- 🎨 Clean, responsive UI
- ⚡ Real-time feedback and status updates

## Running

1. Open `index.html` in your browser (double-click or open from browser)
2. Make sure the backend is running on `http://127.0.0.1:5000`
3. Drag and drop your syllabus PDF
4. Click "Generate Calendar"
5. Your .ics file downloads automatically

## How it Works

1. Frontend sends PDF to backend `/pdf_to_ics` endpoint
2. Backend extracts assignments using AI
3. Backend converts assignments to iCalendar format
4. Frontend downloads the .ics file
5. Import into any calendar app (Google, Outlook, Apple Calendar, etc.)

## Requirements

- Backend running (see backend/README.md)
- Modern browser with fetch API support

Flask PDF Assignment Extractor

Quick start

1. Create a virtualenv and install:

```bash
python -m venv venv
# Windows example
venv\Scripts\activate
pip install -r requirements.txt
```

2. Set your OpenAI API key in the environment:

```bash
# Windows (PowerShell)
$env:OPENAI_API_KEY = "sk-..."
# or cmd
set OPENAI_API_KEY=sk-...
```

3. Run the app:

```bash
python app.py
```

4. Example curl (uploads `syllabus.pdf`):

```bash
curl -X POST "http://localhost:5000/extract_assignments" -F "file=@syllabus.pdf"
```

The endpoint returns JSON like:

```json
[
  {"title": "Homework 1", "due_date": "2026-02-20"},
  {"title": "Project Proposal", "due_date": "2026-03-01"}
]
```

Notes

- The app expects `OPENAI_API_KEY` to be set. Optionally set `OPENAI_MODEL` to choose a specific model.
- This is a minimal, hackathon-friendly prototype; adjust prompts or add authentication as needed.

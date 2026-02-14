Flask PDF Assignment Extractor (backend folder)

Uses Featherless.AI for free LLM-powered assignment extraction.

Setup:

1. Get a free API key at https://featherless.ai
2. Add your key to `.env`:
   ```
   FEATHERLESS_API_KEY=your-key-here
   ```

Run:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Endpoint: `POST /extract_assignments` with form file field `file`.

Example:

```bash
curl -X POST "http://localhost:5000/extract_assignments" -F "file=@syllabus.pdf"
```

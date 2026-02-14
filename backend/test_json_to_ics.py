import requests
import json

url = 'http://127.0.0.1:5000/json_to_ics?course_name=EECS2101'

# Sample assignments from our earlier extraction
assignments = [
    {"title": "A1", "due_date": "2026-02-13"},
    {"title": "A2", "due_date": "2026-03-05"},
    {"title": "A3", "due_date": "2026-03-20"},
    {"title": "A4", "due_date": "2026-04-05"}
]

try:
    response = requests.post(url, json=assignments, timeout=60)
    
    print(f'Status: {response.status_code}')
    if response.status_code == 200:
        with open('EECS2101.ics', 'wb') as f:
            f.write(response.content)
        print(f'Content preview:\n{response.text[:500]}')
        print('\nSaved to: EECS2101.ics')
    else:
        print(f'Error: {response.text}')
except Exception as e:
    print(f'Error: {e}')

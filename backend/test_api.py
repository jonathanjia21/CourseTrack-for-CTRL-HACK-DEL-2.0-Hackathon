import requests

url = "http://127.0.0.1:5000/extract_assignments"
pdf_path = r"C:\Users\ericm\Desktop\syllabus1.pdf"

try:
    with open(pdf_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(url, files=files, timeout=60)
    
    print(f"Status: {response.status_code}")
    print(f"Response:\n{response.text}")
except Exception as e:
    print(f"Error: {e}")

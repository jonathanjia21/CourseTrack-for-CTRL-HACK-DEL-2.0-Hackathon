import requests

url = 'http://127.0.0.1:5000/pdf_to_ics'
pdf_path = r'C:\Users\ericm\Desktop\1310MCourseOutline.pdf'

try:
    with open(pdf_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(url, files=files, timeout=60)
    
    print(f'Status: {response.status_code}')
    if response.status_code == 200:
        with open('test_output.ics', 'wb') as f:
            f.write(response.content)
        print(f'Content preview:\n{response.text[:300]}')
        print('\nSaved to: test_output.ics')
    else:
        print(f'Error: {response.text}')
except Exception as e:
    print(f'Error: {e}')

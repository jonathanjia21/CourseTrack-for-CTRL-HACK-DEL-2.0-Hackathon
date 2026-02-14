const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const fileName = document.getElementById('fileName');
const submitBtn = document.getElementById('submitBtn');
const uploadForm = document.getElementById('uploadForm');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingStatus = document.getElementById('loadingStatus');
const error = document.getElementById('error');
const success = document.getElementById('success');
const courseName = document.getElementById('courseName');

let selectedFile = null;

// Click to browse
dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        fileInput.click();
    }
});

// File input change
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        const file = e.target.files[0];
        if (file.type !== 'application/pdf') {
            showError('Please upload a PDF file');
            return;
        }
        selectedFile = file;
        updateFileName();
    }
});

// Drag and drop
dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('active');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('active');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('active');
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type === 'application/pdf') {
        selectedFile = files[0];
        updateFileName();
    } else {
        showError('Please upload a PDF file');
    }
});

function updateFileName() {
    if (selectedFile) {
        fileName.textContent = selectedFile.name;
        submitBtn.disabled = false;
    }
}

function setLoading(isLoading, statusText) {
    if (statusText) {
        loadingStatus.textContent = statusText;
    }
    loadingOverlay.classList.toggle('active', isLoading);
    loadingOverlay.setAttribute('aria-hidden', String(!isLoading));
}

// Form submission
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    error.style.display = 'none';
    success.style.display = 'none';
    setLoading(true, 'Scanning dates and milestones...');
    submitBtn.disabled = true;

    try {
        const formData = new FormData();
        formData.append('file', selectedFile);

        const course = courseName.value.trim() || 'Course Assignments';
        const response = await fetch(`http://127.0.0.1:5000/pdf_to_ics?course_name=${encodeURIComponent(course)}`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || 'Failed to process PDF');
        }

        setLoading(true, 'Packaging your .ics file...');

        // Download the .ics file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${course.replace(/\\s+/g, '_')}.ics`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showSuccess('Calendar generated! Download started.');
        selectedFile = null;
        fileName.textContent = '';
        submitBtn.disabled = true;
        fileInput.value = '';

    } catch (err) {
        console.error(err);
        showError(err.message || 'An error occurred');
    } finally {
        setLoading(false);
        submitBtn.disabled = false;
    }
});

function showError(msg) {
    error.textContent = msg;
    error.style.display = 'block';
    success.style.display = 'none';
}

function showSuccess(msg) {
    success.textContent = msg;
    success.style.display = 'block';
    error.style.display = 'none';
}
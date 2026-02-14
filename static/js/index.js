const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const submitBtn = document.getElementById('submitBtn');
const uploadForm = document.getElementById('uploadForm');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingStatus = document.getElementById('loadingStatus');
const previewModal = document.getElementById('previewModal');
const previewBody = document.getElementById('previewBody');
const cancelPreview = document.getElementById('cancelPreview');
const confirmGenerate = document.getElementById('confirmGenerate');
const error = document.getElementById('error');
const success = document.getElementById('success');
const courseName = document.getElementById('courseName');

let selectedFiles = [];
let extractedAssignments = [];

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
    const files = Array.from(e.target.files).filter(f => f.type === 'application/pdf');
    if (files.length === 0) {
        showError('Please upload PDF files');
        return;
    }
    selectedFiles = [...selectedFiles, ...files];
    updateFileList();
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
    const files = Array.from(e.dataTransfer.files).filter(f => f.type === 'application/pdf');
    if (files.length === 0) {
        showError('Please upload PDF files');
        return;
    }
    selectedFiles = [...selectedFiles, ...files];
    updateFileList();
});

function updateFileList() {
    if (selectedFiles.length === 0) {
        fileList.innerHTML = '';
        submitBtn.disabled = true;
        return;
    }

    fileList.innerHTML = selectedFiles.map((file, index) => `
        <div class="file-item">
            <span class="file-item-name">${escapeHtml(file.name)}</span>
            <button type="button" class="file-item-remove" data-index="${index}" aria-label="Remove file">×</button>
        </div>
    `).join('');
    
    // Add remove listeners
    fileList.querySelectorAll('.file-item-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            const index = parseInt(btn.dataset.index);
            selectedFiles.splice(index, 1);
            updateFileList();
        });
    });
    
    submitBtn.disabled = false;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function setLoading(isLoading, statusText) {
    if (statusText) {
        loadingStatus.textContent = statusText;
    }
    loadingOverlay.classList.toggle('active', isLoading);
    loadingOverlay.setAttribute('aria-hidden', String(!isLoading));
}

function showPreview() {
    previewModal.classList.add('active');
    previewModal.setAttribute('aria-hidden', 'false');
}

function hidePreview() {
    previewModal.classList.remove('active');
    previewModal.setAttribute('aria-hidden', 'true');
}

// Form submission - Extract assignments and show preview
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (selectedFiles.length === 0) return;

    error.style.display = 'none';
    success.style.display = 'none';
    setLoading(true, 'Extracting assignments from PDFs...');
    submitBtn.disabled = true;

    try {
        extractedAssignments = [];
        
        // Process each PDF
        for (let i = 0; i < selectedFiles.length; i++) {
            const file = selectedFiles[i];
            setLoading(true, `Processing ${file.name} (${i + 1} of ${selectedFiles.length})...`);
            
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/extract_assignments', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Failed to process ${file.name}: ${errorText}`);
            }

            const assignments = await response.json();
            extractedAssignments = [...extractedAssignments, ...assignments];
        }

        setLoading(false);
        
        if (extractedAssignments.length === 0) {
            showError('No assignments found in uploaded PDFs');
            submitBtn.disabled = false;
            return;
        }

        // Show preview modal
        renderPreview();
        showPreview();

    } catch (err) {
        console.error(err);
        showError(err.message || 'An error occurred');
        setLoading(false);
        submitBtn.disabled = false;
    }
});

function renderPreview() {
    if (extractedAssignments.length === 0) {
        previewBody.innerHTML = '<div class="preview-empty">No assignments found</div>';
        return;
    }

    previewBody.innerHTML = extractedAssignments.map((assignment, index) => `
        <div class="assignment-item" data-index="${index}">
            <input type="checkbox" class="assignment-checkbox" id="assignment-${index}" checked>
            <div class="assignment-info">
                <label for="assignment-${index}" class="assignment-title">${escapeHtml(assignment.title || 'Untitled')}</label>
                <div class="assignment-meta">
                    <span class="assignment-date">📅 ${assignment.due_date || 'No date'}</span>
                    <span class="assignment-type">${assignment.type || 'assignment'}</span>
                </div>
            </div>
        </div>
    `).join('');

    // Add checkbox listeners
    previewBody.querySelectorAll('.assignment-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            const item = e.target.closest('.assignment-item');
            item.classList.toggle('unchecked', !e.target.checked);
        });
    });
}

// Cancel preview
cancelPreview.addEventListener('click', () => {
    hidePreview();
    submitBtn.disabled = false;
});

// Generate calendar from selected assignments
confirmGenerate.addEventListener('click', async () => {
    hidePreview();
    setLoading(true, 'Generating calendar file...');

    try {
        // Filter to only checked assignments
        const checkedAssignments = extractedAssignments.filter((_, index) => {
            const checkbox = document.getElementById(`assignment-${index}`);
            return checkbox && checkbox.checked;
        });

        if (checkedAssignments.length === 0) {
            showError('Please select at least one assignment');
            setLoading(false);
            return;
        }

        const course = courseName.value.trim() || 'Course Assignments';
        const response = await fetch(`/json_to_ics?course_name=${encodeURIComponent(course)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(checkedAssignments)
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || 'Failed to generate calendar');
        }

        // Download the .ics file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${course.replace(/\s+/g, '_')}.ics`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showSuccess(`Calendar generated with ${checkedAssignments.length} assignment(s)!`);
        
        // Reset form
        selectedFiles = [];
        extractedAssignments = [];
        fileList.innerHTML = '';
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
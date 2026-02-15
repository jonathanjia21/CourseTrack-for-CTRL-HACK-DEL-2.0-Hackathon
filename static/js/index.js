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
const successModal = document.getElementById('successModal');
const skipStudyPlan = document.getElementById('skipStudyPlan');
const generateStudyPlan = document.getElementById('generateStudyPlan');
const studyPlanModal = document.getElementById('studyPlanModal');
const studyPlanBody = document.getElementById('studyPlanBody');
const studyPlanCourseName = document.getElementById('studyPlanCourseName');
const closeStudyPlan = document.getElementById('closeStudyPlan');
const viewStudyPlanBtn = document.getElementById('viewStudyPlanBtn');
const error = document.getElementById('error');
const success = document.getElementById('success');
const courseName = document.getElementById('courseName');

let selectedFiles = [];
let extractedAssignments = [];
let currentCheckedAssignments = [];
let currentStudyPlan = null;
let currentCourseName = '';

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

function showSuccessModal() {
    successModal.classList.add('active');
    successModal.setAttribute('aria-hidden', 'false');
}

function hideSuccessModal() {
    successModal.classList.remove('active');
    successModal.setAttribute('aria-hidden', 'true');
}

function showStudyPlanModal() {
    studyPlanModal.classList.add('active');
    studyPlanModal.setAttribute('aria-hidden', 'false');
}

function hideStudyPlanModal() {
    studyPlanModal.classList.remove('active');
    studyPlanModal.setAttribute('aria-hidden', 'true');
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
            // Tag each assignment with its source file
            const taggedAssignments = assignments.map(a => ({
                ...a,
                source: file.name
            }));
            extractedAssignments = [...extractedAssignments, ...taggedAssignments];
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

    // Group assignments by source file
    const groupedAssignments = {};
    extractedAssignments.forEach((assignment, index) => {
        const source = assignment.source || 'Unknown source';
        if (!groupedAssignments[source]) {
            groupedAssignments[source] = [];
        }
        groupedAssignments[source].push({ ...assignment, originalIndex: index });
    });

    // Render grouped assignments
    let html = '';
    Object.keys(groupedAssignments).forEach(source => {
        const assignments = groupedAssignments[source];
        html += `
            <div class="file-group">
                <div class="file-group-header">
                    <span class="file-badge">📄</span>
                    <span class="file-group-name">${escapeHtml(source)}</span>
                    <span class="file-group-count">${assignments.length} assignment${assignments.length !== 1 ? 's' : ''}</span>
                </div>
                <div class="file-group-items">
                    ${assignments.map(assignment => `
                        <div class="assignment-item" data-index="${assignment.originalIndex}">
                            <input type="checkbox" class="assignment-checkbox" id="assignment-${assignment.originalIndex}" checked>
                            <div class="assignment-info">
                                <label for="assignment-${assignment.originalIndex}" class="assignment-title">${escapeHtml(assignment.title || 'Untitled')}</label>
                                <div class="assignment-meta">
                                    <span class="assignment-date">📅 ${assignment.due_date || 'No date'}</span>
                                    <span class="assignment-type">${assignment.type || 'assignment'}</span>
                                </div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    });

    previewBody.innerHTML = html;

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

// Skip study plan
skipStudyPlan.addEventListener('click', () => {
    hideSuccessModal();
    resetForm();
});

// Close study plan modal (without resetting form)
closeStudyPlan.addEventListener('click', () => {
    hideStudyPlanModal();
});

// View study plan button
viewStudyPlanBtn.addEventListener('click', () => {
    if (currentStudyPlan) {
        showStudyPlanModal();
    }
});

// Generate study plan
generateStudyPlan.addEventListener('click', async () => {
    hideSuccessModal();
    setLoading(true, 'Generating your personalized study plan...');

    try {
        if (currentCheckedAssignments.length === 0) {
            showError('No assignments available for study plan');
            setLoading(false);
            return;
        }

        const course = courseName.value.trim() || 'Course Assignments';
        const response = await fetch(`/generate_study_plan?course_name=${encodeURIComponent(course)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(currentCheckedAssignments)
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || 'Failed to generate study plan');
        }

        const studyPlan = await response.json();
        
        // Store study plan for later viewing
        currentStudyPlan = studyPlan;
        currentCourseName = course;
        
        // Update course name in study plan modal
        studyPlanCourseName.textContent = `${course} Study Plan`;
        
        // Render study plan
        renderStudyPlan(studyPlan);
        showStudyPlanModal();
        
        // Show the view study plan button
        viewStudyPlanBtn.style.display = 'block';

    } catch (err) {
        console.error(err);
        showError(err.message || 'Failed to generate study plan');
        showSuccessModal();
    } finally {
        setLoading(false);
    }
});

function resetForm() {
    selectedFiles = [];
    extractedAssignments = [];
    currentCheckedAssignments = [];
    currentStudyPlan = null;
    currentCourseName = '';
    fileList.innerHTML = '';
    submitBtn.disabled = true;
    fileInput.value = '';
    viewStudyPlanBtn.style.display = 'none';
}

function renderStudyPlan(studyPlan) {
    let html = '<div class="study-plan-content-inner">';
    
    if (studyPlan.overview) {
        html += `
            <div class="study-plan-section">
                <h3>Overview</h3>
                <p>${escapeHtml(studyPlan.overview)}</p>
            </div>
        `;
    }

    if (studyPlan.weekly_schedule && Array.isArray(studyPlan.weekly_schedule)) {
        html += '<div class="study-plan-section"><h3>Weekly Schedule</h3>';
        studyPlan.weekly_schedule.forEach((week, index) => {
            html += `
                <div class="study-plan-week">
                    <h4>Week ${index + 1}</h4>
                    <p>${escapeHtml(week)}</p>
                </div>
            `;
        });
        html += '</div>';
    }

    if (studyPlan.study_tips && Array.isArray(studyPlan.study_tips)) {
        html += '<div class="study-plan-section"><h3>Study Tips</h3><ul>';
        studyPlan.study_tips.forEach((tip) => {
            html += `<li>${escapeHtml(tip)}</li>`;
        });
        html += '</ul></div>';
    }

    if (studyPlan.resource_recommendations) {
        html += `
            <div class="study-plan-section">
                <h3>Resource Recommendations</h3>
                <p>${escapeHtml(studyPlan.resource_recommendations)}</p>
            </div>
        `;
    }

    html += '</div>';
    studyPlanBody.innerHTML = html;
}

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

        // Prefix titles with course code from filename
        const prefixedAssignments = checkedAssignments.map(assignment => {
            const courseCode = extractCourseCode(assignment.source);
            const prefix = courseCode ? `${courseCode} - ` : '';
            return {
                ...assignment,
                title: `${prefix}${assignment.title}`
            };
        });

        const course = courseName.value.trim() || 'Course Assignments';
        const response = await fetch(`/json_to_ics?course_name=${encodeURIComponent(course)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(prefixedAssignments)
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

        // Store checked assignments for study plan generation
        currentCheckedAssignments = checkedAssignments;

        // Show success modal with study plan option
        hidePreview();
        setLoading(false);
        showSuccessModal();

    } catch (err) {
        console.error(err);
        showError(err.message || 'An error occurred');
    } finally {
        setLoading(false);
        submitBtn.disabled = false;
    }
});

function extractCourseCode(filename) {
    if (!filename) return null;
    
    // Remove file extension
    const nameWithoutExt = filename.replace(/\.pdf$/i, '');
    
    // Try to match common course code patterns
    // Examples: EECS3101, EECS 3101, CS-101, MATH201, etc.
    const patterns = [
        /([A-Z]{2,4}\s*\d{3,4}[A-Z]?)/i,  // EECS3101, EECS 3101, CS101
        /([A-Z]{2,4}-\d{3,4}[A-Z]?)/i,    // CS-101, MATH-201
    ];
    
    for (const pattern of patterns) {
        const match = nameWithoutExt.match(pattern);
        if (match) {
            // Normalize spacing: EECS3101 → EECS 3101
            return match[1].replace(/([A-Z]+)(\d)/, '$1 $2').toUpperCase();
        }
    }
    
    // Fallback: use first word or abbreviation from filename
    const firstWord = nameWithoutExt.split(/[_\-\s]+/)[0];
    if (firstWord && firstWord.length <= 15) {
        return firstWord;
    }
    
    return null;
}

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
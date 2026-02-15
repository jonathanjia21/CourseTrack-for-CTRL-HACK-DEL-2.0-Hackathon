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
const studyPlanSelector = document.getElementById('studyPlanSelector');
const studyPlanDropdown = document.getElementById('studyPlanDropdown');
const inlineDownloadPdf = document.getElementById('inlineDownloadPdf');
const studyGuideInline = document.getElementById('studyGuideInline');
const inlineGuideBody = document.getElementById('inlineGuideBody');
const error = document.getElementById('error');
const success = document.getElementById('success');
const courseName = document.getElementById('courseName');
const discordOptIn = document.getElementById('discordOptIn');
const discordHandle = document.getElementById('discordHandle');
const termEnd = document.getElementById('termEnd');
const discordMatches = document.getElementById('discordMatches');
const discordMatchesBody = document.getElementById('discordMatchesBody');
const discordMatchesEmpty = document.getElementById('discordMatchesEmpty');

let selectedFiles = [];
let extractedAssignments = [];
let currentCheckedAssignments = [];
let studyPlansByCourseName = {}; // Map of courseName -> studyPlan
let courseAssignmentsByName = {}; // Map of courseName -> assignments
let fileHashesByCourseName = {}; // Map of courseName -> file_hash (for caching)
let currentStudyPlanCourse = ''; // Track currently viewed study plan course
const ALL_COURSES_VALUE = '__all__';
let discordMatchesBySource = {}; // Map of filename -> array of handles

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

function normalizeDiscordHandle(handle) {
    if (!handle) return '';
    return handle.trim().replace(/^@/, '').trim();
}

function getTermEndValue() {
    return termEnd && termEnd.value ? termEnd.value : '';
}

function setDefaultTermEnd() {
    if (!termEnd || termEnd.value) return;
    const now = new Date();
    const year = now.getFullYear();
    termEnd.value = `${year}-12-31`;
}

function setOptInFieldsEnabled(isEnabled) {
    const fields = document.querySelector('.discord-opt-fields');
    if (!fields) return;
    fields.classList.toggle('active', isEnabled);
}

function renderDiscordMatches() {
    const entries = Object.entries(discordMatchesBySource);
    if (entries.length === 0) {
        discordMatches.style.display = 'none';
        return;
    }

    discordMatches.style.display = 'block';
    discordMatchesBody.innerHTML = entries.map(([source, handles]) => {
        const safeSource = escapeHtml(source);
        if (!handles || handles.length === 0) {
            return `
                <div class="discord-course-block">
                    <div class="discord-course-title">${safeSource}</div>
                    <div class="discord-match-empty">No matches yet.</div>
                </div>
            `;
        }
        const pills = handles.map(handle => `<span class="discord-handle">${escapeHtml(handle)}</span>`).join('');
        return `
            <div class="discord-course-block">
                <div class="discord-course-title">${safeSource}</div>
                <div class="discord-handle-list">${pills}</div>
            </div>
        `;
    }).join('');

    discordMatchesEmpty.style.display = 'none';
}

discordOptIn.addEventListener('change', (e) => {
    setOptInFieldsEnabled(e.target.checked);
});

setDefaultTermEnd();
setOptInFieldsEnabled(discordOptIn.checked);

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

// Form submission - Extract assignments and show preview
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (selectedFiles.length === 0) return;

    if (discordOptIn.checked) {
        const handle = normalizeDiscordHandle(discordHandle.value);
        if (!handle) {
            showError('Please enter your Discord handle to opt in');
            return;
        }
    }

    error.style.display = 'none';
    success.style.display = 'none';
    setLoading(true, 'Extracting assignments from PDFs...');
    submitBtn.disabled = true;

    try {
        extractedAssignments = [];
        discordMatchesBySource = {};
        
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

            const responseData = await response.json();
            
            // Handle both new format (with file_hash) and old format (just array)
            let assignments = Array.isArray(responseData) ? responseData : responseData.assignments || [];
            const fileHash = responseData.file_hash || null;
            const cachedStudyPlans = responseData.study_plans || {};
            
            // Tag each assignment with its source file and file hash
            const taggedAssignments = assignments.map(a => ({
                ...a,
                source: file.name,
                file_hash: fileHash
            }));
            extractedAssignments = [...extractedAssignments, ...taggedAssignments];
            
            // Store cached study plans if available
            if (cachedStudyPlans && Object.keys(cachedStudyPlans).length > 0) {
                Object.assign(studyPlansByCourseName, cachedStudyPlans);
            }

            if (discordOptIn.checked && fileHash) {
                const handle = normalizeDiscordHandle(discordHandle.value);
                try {
                    await fetch('/share_discord', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            file_hash: fileHash,
                            discord_handle: handle,
                            term_end: getTermEndValue()
                        })
                    });

                    const matchesResponse = await fetch('/shared_discords', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            file_hash: fileHash,
                            viewer_handle: handle
                        })
                    });

                    if (matchesResponse.ok) {
                        const matchesData = await matchesResponse.json();
                        discordMatchesBySource[file.name] = matchesData.shared_discords || [];
                    }
                } catch (matchError) {
                    console.error(matchError);
                }
            }
        }

        setLoading(false);

        renderDiscordMatches();
        
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

// Download study guide as PDF
async function downloadStudyGuide() {
    const cName = currentStudyPlanCourse;
    if (!cName || cName === ALL_COURSES_VALUE || !studyPlansByCourseName[cName]) {
        showError('No study plan available to download');
        return;
    }

    try {
        const response = await fetch('/download_study_guide', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                study_plan: studyPlansByCourseName[cName],
                assignments: courseAssignmentsByName[cName] || currentCheckedAssignments,
                course_name: cName
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || 'Download failed');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${cName.replace(/\s+/g, '_')}_Study_Guide.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (err) {
        console.error(err);
        showError(err.message || 'Failed to download study guide');
    }
}

// Download button in inline section
inlineDownloadPdf.addEventListener('click', () => downloadStudyGuide());

// Show inline study guide section
function showInlineStudyGuide(cName) {
    currentStudyPlanCourse = cName;
    // Update dropdown selection to match
    if (studyPlanDropdown.value !== cName) {
        studyPlanDropdown.value = cName;
    }
    renderInlineStudyGuide(studyPlansByCourseName[cName], courseAssignmentsByName[cName] || currentCheckedAssignments);
    studyGuideInline.style.display = 'block';
    studyPlanSelector.style.display = 'block';
    // Smooth scroll to the inline guide
    setTimeout(() => {
        studyGuideInline.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

function updateStudyGuideScrollbarTheme(selectedCourse) {
    const existing = Array.from(studyGuideInline.classList).filter((name) => name.startsWith('sg-scroll-'));
    existing.forEach((name) => studyGuideInline.classList.remove(name));

    if (!selectedCourse || selectedCourse === ALL_COURSES_VALUE) {
        studyGuideInline.classList.add('sg-scroll-neutral');
        return;
    }

    const courseClass = getCourseColorClass(selectedCourse);
    studyGuideInline.classList.add(`sg-scroll-${courseClass}`);
}

function renderInlineStudyGuide(studyPlan, assignments) {
    let html = '<div class="study-guide-rendered">';
    const selectedCourse = studyPlanDropdown.value || currentStudyPlanCourse;
    updateStudyGuideScrollbarTheme(selectedCourse);

    // Assignments table
    if (assignments && assignments.length > 0) {
        const filteredAssignments = selectedCourse === ALL_COURSES_VALUE
            ? assignments
            : assignments.filter((item) => extractCourseCode(item.source) === selectedCourse);
        const sortedAssignments = [...filteredAssignments].sort((a, b) => {
            const aTime = a && a.due_date ? Date.parse(a.due_date) : Number.POSITIVE_INFINITY;
            const bTime = b && b.due_date ? Date.parse(b.due_date) : Number.POSITIVE_INFINITY;
            if (aTime === bTime) {
                return 0;
            }
            return aTime - bTime;
        });

        html += '<div class="sg-split">';
        html += '<div class="sg-panel sg-panel-assignments">';
        html += '<div class="sg-block-header">Upcoming Assignments & Deadlines</div>';
        html += '<div class="sg-table-wrapper"><table class="sg-table"><thead><tr><th>Title</th><th>Due Date</th><th>Type</th></tr></thead><tbody>';
        if (sortedAssignments.length === 0) {
            html += '<tr><td colspan="3" class="sg-empty">No assignments found for this course</td></tr>';
        } else {
            sortedAssignments.forEach(a => {
                const courseCode = extractCourseCode(a.source);
                const typeLabel = (a.type || 'assignment').charAt(0).toUpperCase() + (a.type || 'assignment').slice(1);
                const typeWithCourse = courseCode ? `${courseCode} • ${typeLabel}` : typeLabel;
                const courseClass = courseCode ? `sg-type-${getCourseColorClass(courseCode)}` : 'sg-type-default';
                html += `<tr>
                    <td>${escapeHtml(a.title || 'Untitled')}</td>
                    <td>${escapeHtml(a.due_date || 'TBD')}</td>
                    <td><span class="sg-type-badge ${courseClass}">${escapeHtml(typeWithCourse)}</span></td>
                </tr>`;
            });
        }
        html += '</tbody></table></div></div>';

        html += '<div class="sg-panel">';
        html += '<div class="sg-block-header">Study Guide</div>';
        if (selectedCourse === ALL_COURSES_VALUE) {
            html += '<div class="sg-empty">Select a course to view its study guide</div>';
        }
    }

    // Overview
    if (studyPlan.overview && studyPlanDropdown.value !== ALL_COURSES_VALUE) {
        html += `<div class="sg-section"><h3>Overview</h3><p>${escapeHtml(studyPlan.overview)}</p></div>`;
    }

    // Weekly Schedule
    if (studyPlan.weekly_schedule && Array.isArray(studyPlan.weekly_schedule) && studyPlanDropdown.value !== ALL_COURSES_VALUE) {
        html += '<div class="sg-section"><h3>Weekly Schedule</h3>';
        studyPlan.weekly_schedule.forEach((week, i) => {
            html += `<div class="sg-week"><h4>Week ${i + 1}</h4><p>${escapeHtml(week)}</p></div>`;
        });
        html += '</div>';
    }

    // Study Tips
    if (studyPlan.study_tips && Array.isArray(studyPlan.study_tips) && studyPlanDropdown.value !== ALL_COURSES_VALUE) {
        html += '<div class="sg-section"><h3>Study Tips</h3><ul class="sg-tips">';
        studyPlan.study_tips.forEach(tip => {
            html += `<li>${escapeHtml(tip)}</li>`;
        });
        html += '</ul></div>';
    }

    // Resource Recommendations
    if (studyPlan.resource_recommendations && studyPlanDropdown.value !== ALL_COURSES_VALUE) {
        html += `<div class="sg-section"><h3>Resource Recommendations</h3><p>${escapeHtml(studyPlan.resource_recommendations)}</p></div>`;
    }

    if (assignments && assignments.length > 0) {
        html += '</div></div>';
    }
    inlineGuideBody.innerHTML = html;
}

// Study plan dropdown selector
studyPlanDropdown.addEventListener('change', (e) => {
    const selectedCourseName = e.target.value;
    if (selectedCourseName === ALL_COURSES_VALUE) {
        currentStudyPlanCourse = ALL_COURSES_VALUE;
        renderInlineStudyGuide({}, currentCheckedAssignments);
        studyGuideInline.style.display = 'block';
        studyPlanSelector.style.display = 'block';
        return;
    }
    if (selectedCourseName && studyPlansByCourseName[selectedCourseName]) {
        currentStudyPlanCourse = selectedCourseName;
        showInlineStudyGuide(selectedCourseName);
    }
});

// Generate study plan
generateStudyPlan.addEventListener('click', async () => {
    hideSuccessModal();
    setLoading(true, 'Generating personalized study plans for each course...');

    try {
        if (currentCheckedAssignments.length === 0) {
            showError('No assignments available for study plan');
            setLoading(false);
            return;
        }

        // Group assignments by course
        const assignmentsByCourseName = {};
        const hashByCourseName = {}; // Track the primary file hash for each course
        
        currentCheckedAssignments.forEach(assignment => {
            const courseCode = extractCourseCode(assignment.source) || 'General';
            if (!assignmentsByCourseName[courseCode]) {
                assignmentsByCourseName[courseCode] = [];
                hashByCourseName[courseCode] = assignment.file_hash || null;
            }
            assignmentsByCourseName[courseCode].push(assignment);
        });

        // Clear previous study plans (but keep already cached ones from response)
        // Don't clear studyPlansByCourseName - preserve cached plans from DB
        courseAssignmentsByName = {};
        fileHashesByCourseName = {};
        
        // Generate a study plan for each course
        const courseNames = Object.keys(assignmentsByCourseName);
        for (let i = 0; i < courseNames.length; i++) {
            const courseName = courseNames[i];
            const assignments = assignmentsByCourseName[courseName];
            const fileHash = hashByCourseName[courseName];
            
            setLoading(true, `Generating study plan for ${courseName} (${i + 1} of ${courseNames.length})...`);
            
            // Check if this study plan is already cached
            if (studyPlansByCourseName[courseName]) {
                console.log(`Using cached study plan for ${courseName}`);
                continue;
            }
            
            const requestPayload = {
                data: assignments,
                file_hash: fileHash
            };
            
            const response = await fetch(`/generate_study_plan?course_name=${encodeURIComponent(courseName)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestPayload)
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Failed to generate study plan for ${courseName}: ${errorText}`);
            }

            const studyPlan = await response.json();
            studyPlansByCourseName[courseName] = studyPlan;
            courseAssignmentsByName[courseName] = assignments;
            fileHashesByCourseName[courseName] = fileHash;
        }

        // Populate dropdown with course names
        populateStudyPlanDropdown(courseNames);
        
        // Show the first study plan
        if (courseNames.length > 0) {
            currentStudyPlanCourse = courseNames[0];
            studyPlanDropdown.value = courseNames[0];
            showInlineStudyGuide(courseNames[0]);
        }

    } catch (err) {
        console.error(err);
        showError(err.message || 'Failed to generate study plans');
        showSuccessModal();
    } finally {
        setLoading(false);
    }
});

function populateStudyPlanDropdown(courseNames) {
    // Keep the first option placeholder
    const options = [
        '<option value="">-- Select a course --</option>',
        `<option value="${ALL_COURSES_VALUE}">All Courses</option>`
    ];
    
    courseNames.forEach(courseName => {
        options.push(`<option value="${escapeHtml(courseName)}">${escapeHtml(courseName)}</option>`);
    });
    
    // Rebuild the dropdown while preserving the first option
    const innerHTML = options.join('');
    studyPlanDropdown.innerHTML = innerHTML;
}

function resetForm() {
    selectedFiles = [];
    extractedAssignments = [];
    currentCheckedAssignments = [];
    studyPlansByCourseName = {};
    courseAssignmentsByName = {};
    fileHashesByCourseName = {};
    currentStudyPlanCourse = '';
    discordMatchesBySource = {};
    fileList.innerHTML = '';
    submitBtn.disabled = true;
    fileInput.value = '';
    discordOptIn.checked = false;
    discordHandle.value = '';
    setDefaultTermEnd();
    setOptInFieldsEnabled(false);
    discordMatches.style.display = 'none';
    discordMatchesBody.innerHTML = '';
    discordMatchesEmpty.style.display = 'block';
    studyPlanSelector.style.display = 'none';
    studyGuideInline.style.display = 'none';
    inlineGuideBody.innerHTML = '';
    populateStudyPlanDropdown([]);
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

function getCourseColorClass(courseCode) {
    const palettes = ['a', 'b', 'c', 'd', 'e', 'f'];
    let hash = 0;
    for (let i = 0; i < courseCode.length; i++) {
        hash = (hash * 31 + courseCode.charCodeAt(i)) % 997;
    }
    return palettes[hash % palettes.length];
}
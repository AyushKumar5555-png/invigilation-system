// Global State
let activeConfig = {
    exam_type: "midsem",
    category_ratio_mode: "target_load_scaling",
    categories: [],
    faculty_list: [],
    sessions: [],
    history: []
};

let activeResult = null;
let currentModalTab = 'general';
let selectedFacultyId = null;
let selectedSessionId = null;
let activeTimetableWeekOffset = 0; // Pagination offset for timetable: 0 represents May 20-26, 2026
let activeViewMode = 'week';

// Deterministic Course & Room Mappings to translate simple slots into university exam schedules
const mockCourses = [
    { code: "CS101", dept: "eng", name: "Intro to Programming" },
    { code: "MA201", dept: "math", name: "Linear Algebra" },
    { code: "PH301", dept: "sci", name: "Quantum Physics" },
    { code: "EC201", dept: "eng", name: "Basic Electronics" },
    { code: "CH101", dept: "sci", name: "General Chemistry" },
    { code: "HS101", dept: "hum", name: "Sociology & Ethics" },
    { code: "MG101", dept: "mgt", name: "Principles of Management" },
    { code: "EE102", dept: "eng", name: "Electrical Networks" },
    { code: "CS204", dept: "eng", name: "Data Structures" },
    { code: "MA102", dept: "math", name: "Calculus II" },
    { code: "PH102", dept: "sci", name: "Physics Labs" }
];

const mockRooms = ["Room A1", "Room B2", "Room C3", "Room B1", "Room C2", "Room D1", "Room E2"];

// Faculty ID to Department mapping for color code consistency
const facultyDeptMap = {
    "P1": "eng",
    "P2": "eng",
    "AS1": "sci",
    "AS2": "sci",
    "AS3": "math",
    "AP1": "hum",
    "AP2": "mgt",
    "AP3": "oth",
    "AP4": "eng"
};

// On Document Load
document.addEventListener('DOMContentLoaded', () => {
    loadConfigFromBackend();
    
    // Bind Keyboard Shortcuts (Focus search on '/')
    document.addEventListener('keydown', (e) => {
        if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
            e.preventDefault();
            document.getElementById('global-search').focus();
        }
    });

    // View mode handlers
    document.getElementById('view-mode-week').addEventListener('click', () => {
        setViewMode('week');
    });
    document.getElementById('view-mode-day').addEventListener('click', () => {
        setViewMode('day');
    });
});

// Toast Notifications
function showToast(message, type = 'info') {
    const toast = document.getElementById('app-toast');
    const msgEl = document.getElementById('toast-msg');
    
    msgEl.textContent = message;
    
    // Remove previous classes
    toast.className = 'toast-notification';
    if (type === 'success') toast.classList.add('toast-success');
    else if (type === 'error') toast.classList.add('toast-error');
    else toast.classList.add('toast-info');
    
    // Show toast
    toast.classList.remove('hidden');
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4000);
}

// API Integration
async function loadConfigFromBackend() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) throw new Error("Failed to fetch configuration.");
        activeConfig = await response.json();
        
        // Handle empty fields
        activeConfig.categories = activeConfig.categories || [];
        activeConfig.faculty_list = activeConfig.faculty_list || [];
        activeConfig.sessions = activeConfig.sessions || [];
        activeConfig.history = activeConfig.history || [];
        
        // Normalize categories for UI consistency
        activeConfig.faculty_list.forEach(f => {
            if (f.category && !f.category_name) {
                f.category_name = f.category;
            } else if (f.category_name && !f.category) {
                f.category = f.category_name;
            }
        });
        
        console.log("Loaded Configuration from Backend:", activeConfig);
        
        // Sync inputs
        syncUIWithConfig();
        
        // Perform initial solve to populate dashboards
        triggerSolve(true); // silent solve on startup
    } catch (err) {
        showToast("Error loading config: " + err.message, "error");
    }
}

async function saveConfigToBackend(silent = false) {
    try {
        // Ensure both properties are normalized before saving
        if (activeConfig.faculty_list) {
            activeConfig.faculty_list.forEach(f => {
                if (f.category_name) {
                    f.category = f.category_name;
                } else if (f.category) {
                    f.category_name = f.category;
                }
            });
        }
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(activeConfig)
        });
        if (!response.ok) throw new Error("Failed to save configuration.");
        
        if (!silent) {
            showToast("Configuration saved successfully!", "success");
        }
    } catch (err) {
        showToast("Error saving config: " + err.message, "error");
    }
}

async function triggerSolve(silent = false) {
    if (!silent) {
        showToast("Running invigilation duty solver...", "info");
    }
    
    const solveBtn = document.getElementById('run-solve-btn');
    if (solveBtn) {
        solveBtn.disabled = true;
        solveBtn.innerHTML = `<span class="btn-icon">⏳</span> Solving...`;
    }

    try {
        const response = await fetch('/api/solve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(activeConfig)
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || "Solver error.");
        }
        
        activeResult = await response.json();
        console.log("Solver execution output result:", activeResult);
        
        // Auto-commit history imbalance
        if (activeResult.success && activeResult.faculty_summaries) {
            activeResult.faculty_summaries.forEach(sum => {
                const record = activeConfig.history.find(h => h.faculty_id === sum.faculty_id);
                if (record) {
                    record.previous_imbalance = sum.cumulative_imbalance;
                } else {
                    activeConfig.history.push({
                        faculty_id: sum.faculty_id,
                        previous_imbalance: sum.cumulative_imbalance
                    });
                }
            });
            // Auto save updated config to backend
            saveConfigToBackend(true);
        }
        
        // Sync results
        renderSolveResults();
        
        if (!silent) {
            if (activeResult.success) {
                showToast("Schedule generated successfully!", "success");
            } else {
                if (activeResult.feasibility_report.includes("PARTIAL")) {
                    showToast("Schedule partially solved. Some slots could not be staffed.", "error");
                } else {
                    showToast("Solver failed to generate a feasible allocation.", "error");
                }
            }
        }
    } catch (err) {
        showToast("Solver failed: " + err.message, "error");
        activeResult = {
            success: false,
            schedule: activeConfig.sessions.map(s => ({ session_id: s.id, assigned_faculty_ids: [] })),
            faculty_summaries: activeConfig.faculty_list.map(f => ({
                faculty_id: f.id,
                name: f.name,
                category_name: f.category_name,
                assigned_sessions: [],
                assigned_hours: 0,
                assigned_weighted_load: 0,
                target_load: 0,
                overload: 0,
                underload: 0,
                historical_imbalance: 0,
                cumulative_imbalance: 0,
                impact_status: "NEUTRAL",
                selection_explanations: {}
            })),
            jains_fairness_index: 0,
            gini_coefficient: 0,
            feasibility_report: "INFEASIBLE",
            conflict_report: ["Solver error: " + err.message],
            history_impact_report: "No allocation performed due to solver failure."
        };
        renderSolveResults();
    } finally {
        if (solveBtn) {
            solveBtn.disabled = false;
            solveBtn.innerHTML = `<span class="btn-icon">▶️</span> Run Allocation`;
        }
    }
}

// UI Sync / Binding
function syncUIWithConfig() {
    // Top-left sidebar texts
    document.getElementById('term-name').textContent = activeConfig.exam_type === 'midsem' ? 'Spring Mid Sem 2026' : 'Spring End Sem 2026';
    
    // Sync header date formats
    const startRange = getTimetableRangeLabel(activeTimetableWeekOffset);
    document.getElementById('timetable-range-label').textContent = startRange;
    document.getElementById('exam-period-dates').textContent = startRange;

    // Stats cards static values
    document.getElementById('stat-sessions').textContent = activeConfig.sessions.length;
    document.getElementById('stat-faculty').textContent = activeConfig.faculty_list.length;
    
    // Synchronize settings forms elements
    document.getElementById('setting-exam-type').value = activeConfig.exam_type;
    document.getElementById('setting-ratio-mode').value = activeConfig.category_ratio_mode;
    document.getElementById('setting-exam-start-date').value = activeConfig.exam_start_date || '';
    
    // Fill category filters in settings
    const filterCatSelect = document.getElementById('filter-category');
    if (filterCatSelect) {
        filterCatSelect.innerHTML = `<option value="all">All Categories</option>`;
        const categories = getCategoriesList();
        categories.forEach(catName => {
            filterCatSelect.innerHTML += `<option value="${catName}">${catName}</option>`;
        });
    }

    // Fill faculty filters in settings
    const filterFacSelect = document.getElementById('filter-faculty');
    if (filterFacSelect) {
        filterFacSelect.innerHTML = `<option value="all">All Faculty</option>`;
        activeConfig.faculty_list.forEach(fac => {
            filterFacSelect.innerHTML += `<option value="${fac.id}">${fac.name}</option>`;
        });
    }

    // Update timetable grid dates immediately
    renderTimetableGrid();
}

function getCategoriesList() {
    if (Array.isArray(activeConfig.categories)) {
        return activeConfig.categories.map(c => c.name);
    } else if (typeof activeConfig.categories === 'object') {
        return Object.keys(activeConfig.categories);
    }
    return [];
}

// Result Renderers
function renderSolveResults() {
    if (!activeResult) return;
    
    // Sync numerical statistics
    const totalAllocations = activeResult.schedule.reduce((acc, curr) => acc + curr.assigned_faculty_ids.length, 0);
    const totalRequired = activeConfig.sessions.reduce((acc, curr) => acc + curr.required_invigilators, 0);
    
    document.getElementById('stat-allocations').textContent = totalAllocations;
    
    const coveragePercent = totalRequired > 0 ? Math.round((totalAllocations / totalRequired) * 100) : 0;
    document.getElementById('stat-coverage').textContent = `${coveragePercent}%`;
    document.getElementById('stat-coverage-sub').textContent = coveragePercent === 100 ? "All sessions covered" : `${totalRequired - totalAllocations} unfilled duties`;

    // Render schedule calendar timetable
    renderTimetableGrid();
    
    // Render Fairness indexes
    renderFairnessMetrics();
    
    // Render Conflicts list
    renderConflictsList();
    
    // Render Workload distribution chart
    renderWorkloadDistribution();
    
    // Render bottom sparklines stats
    renderBottomSparklines(totalAllocations);
    
    // Render History load balancing table
    renderHistoryImpactTable();
}

// Helper: Dates formatting calculations
function getExamBaseDate() {
    if (activeConfig.exam_start_date) {
        const parts = activeConfig.exam_start_date.split('-');
        if (parts.length === 3) {
            return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        }
        return new Date(activeConfig.exam_start_date);
    }
    const today = new Date();
    const day = today.getDay();
    const diff = today.getDate() - day + (day === 0 ? -6 : 1);
    return new Date(today.setDate(diff));
}

function getTimetableDateLabel(dayNum, offset = 0) {
    const baseDate = getExamBaseDate();
    baseDate.setDate(baseDate.getDate() + (dayNum - 1) + (offset * 7));
    const daysOfWeek = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    return `${daysOfWeek[baseDate.getDay()]} ${baseDate.getDate()}`;
}

// Helper to get full day name
function getDayName(dayNum) {
    const dayNames = {
        1: "Monday",
        2: "Tuesday",
        3: "Wednesday",
        4: "Thursday",
        5: "Friday",
        6: "Saturday"
    };
    return dayNames[dayNum] || ("Day " + dayNum);
}

function getTimetableRangeLabel(offset = 0) {
    const baseDate = getExamBaseDate();
    baseDate.setDate(baseDate.getDate() + (offset * 7));
    const endDate = new Date(baseDate);
    endDate.setDate(endDate.getDate() + 6);
    
    const format = (d) => {
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        return `${months[d.getMonth()]} ${d.getDate()}`;
    };
    return `${format(baseDate)} – ${format(endDate)}, ${baseDate.getFullYear()}`;
}

// Dynamic Mock details generator for Course + Room hashing
function getMockDutyDetails(session, assignedIndex, facultyId) {
    // Generate deterministic hash code based on session ID and slot index
    let hash = 0;
    const str = session.id + assignedIndex;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    
    const course = mockCourses[Math.abs(hash) % mockCourses.length];
    const room = mockRooms[Math.abs(hash * 3) % mockRooms.length];
    
    // Determine dept color class
    let dept = course.dept;
    if (facultyId && facultyDeptMap[facultyId]) {
        dept = facultyDeptMap[facultyId];
    }
    
    return {
        courseCode: course.code,
        courseName: course.name,
        room: room,
        dept: dept
    };
}

// Timetable Grid Renderer
function renderTimetableGrid() {
    const tableHeader = document.getElementById('timetable-header-row');
    const tableBody = document.getElementById('timetable-body');
    
    // Reset contents
    tableHeader.innerHTML = `<th class="time-col">Time</th>`;
    tableBody.innerHTML = '';
    
    if (activeConfig.sessions.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="10" class="empty-state-text">No exam sessions configured. Add sessions in settings.</td></tr>`;
        return;
    }
    
    // Fixed Monday–Saturday (1 to 6)
    let days = [1, 2, 3, 4, 5, 6];
    if (activeViewMode === 'day') {
        const filterDay = document.getElementById('filter-day').value;
        const selectedDay = filterDay !== 'all' ? parseInt(filterDay) : 1;
        days = [selectedDay];
    }
    
    // Add headers matching day numbers
    days.forEach(dayNum => {
        const dateLabel = getTimetableDateLabel(dayNum, activeTimetableWeekOffset);
        tableHeader.innerHTML += `<th>${dateLabel}</th>`;
    });
    
    // Define rows dynamically based on the session_num present in the current config
    const sessionNums = [1, 2]; // Hardcoded — system is permanently 2-shift (Morning/Afternoon)
    const sessionLabels = {
        1: "10:00 - 13:00 <span class=\"list-item-sub\">Morning</span>",
        2: "14:00 - 17:00 <span class=\"list-item-sub\">Afternoon</span>"
    };

    const getShortSessionLabel = (s) => s.session_num === 1 ? 'FN' : 'AN';
    
    // Search filter terms
    const searchTerm = document.getElementById('global-search').value.toLowerCase();
    const filterCat = document.getElementById('filter-category').value;
    const filterFac = document.getElementById('filter-faculty').value;
    const filterDay = document.getElementById('filter-day').value;

    sessionNums.forEach(sessNum => {
        // Find a session with this session_num that has start_time defined
        const representativeSession = activeConfig.sessions.find(s => s.session_num === sessNum && s.start_time !== undefined);
        let timeLabel = "";
        if (representativeSession) {
            const start = representativeSession.start_time;
            const dur = representativeSession.duration_hours || 2.0;
            const end = start + dur * 60;
            const formatTime = (minsTotal) => {
                const h = Math.floor(minsTotal / 60);
                const m = minsTotal % 60;
                return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
            };
            const timeRangeStr = `${formatTime(start)} - ${formatTime(end)}`;
            
            let shiftName = sessNum === 1 ? "Morning" : "Afternoon";
            timeLabel = `${timeRangeStr} <span class="list-item-sub">${shiftName}</span>`;
        } else {
            timeLabel = sessionLabels[sessNum];
        }
        
        let rowHtml = `<tr><td class="time-cell">${timeLabel}</td>`;
        
        days.forEach(dayNum => {
            // Find session matching this day and session number
            const session = activeConfig.sessions.find(s => s.day === dayNum && s.session_num === sessNum);
            
            if (!session) {
                rowHtml += `<td><span class="text-light">—</span></td>`;
            } else {
                // Check if this cell is filtered out by day selector
                if (filterDay !== 'all' && parseInt(filterDay) !== dayNum) {
                    rowHtml += `<td><span class="text-light">Filtered</span></td>`;
                    return;
                }

                // Get assignments for this session from results
                const allocation = activeResult ? activeResult.schedule.find(sa => sa.session_id === session.id) : null;
                const assignedIds = allocation ? allocation.assigned_faculty_ids : [];
                const required = session.required_invigilators;
                
                let cardsHtml = '<div class="allocation-card-wrapper">';
                
                // Loop up to required slots count to show empty/vacant slots individually
                for (let idx = 0; idx < required; idx++) {
                    const facId = assignedIds[idx];
                    
                    if (!facId) {
                        // Vacant slot
                        cardsHtml += `<div class="schedule-card unassigned-bg" style="margin-top: 4px; padding: 6px 8px; display: flex; flex-direction: column; gap: 2px;">
                            <div class="schedule-card-faculty" style="font-weight: 600; font-size: 11.5px; color: var(--color-danger);">VACANT SLOT</div>
                            <div class="schedule-card-room" style="font-size: 10px; color: var(--color-danger); font-weight: 500;">Unfilled duty</div>
                            <div class="schedule-card-subject" style="font-size: 9.5px; font-weight: 500; text-transform: uppercase;">${session.label || (getDayName(session.day) + ' ' + getShortSessionLabel(session))}</div>
                        </div>`;
                        continue;
                    }

                    const faculty = activeConfig.faculty_list.find(f => f.id === facId);
                    if (!faculty) continue;
                    
                    // Apply filters (Category, Faculty Search terms)
                    if (filterCat !== 'all' && faculty.category_name !== filterCat) continue;
                    if (filterFac !== 'all' && facId !== filterFac) continue;
                    if (searchTerm && !faculty.name.toLowerCase().includes(searchTerm) && !session.id.toLowerCase().includes(searchTerm)) continue;

                    const mockDetails = getMockDutyDetails(session, idx, facId);
                    const categoryClass = `${mockDetails.dept}-bg`;
                    
                    cardsHtml += `<div class="schedule-card ${categoryClass}" style="cursor: pointer; padding: 6px 8px; display: flex; flex-direction: column; gap: 2px;" onclick="showFacultyWeeklyReport('${facId}')">
                         <div class="schedule-card-faculty" style="font-weight: 600; font-size: 11px; word-break: break-word; line-height: 1.25;">${faculty.name}</div>
                         <div class="schedule-card-room" style="font-size: 10px; color: rgba(30, 41, 59, 0.85); font-weight: 500;">📞 ${faculty.phone || 'N/A'}</div>
                         <div class="schedule-card-subject" style="font-size: 9.5px; font-weight: 500; opacity: 0.85; text-transform: uppercase;">${session.label || ('Day ' + session.day + ' ' + getShortSessionLabel(session))}</div>
                     </div>`;
                }
                
                cardsHtml += '</div>';
                rowHtml += `<td>${cardsHtml}</td>`;
            }
        });
        
        rowHtml += '</tr>';
        tableBody.innerHTML += rowHtml;
    });
}

function setViewMode(mode) {
    activeViewMode = mode;
    document.getElementById('view-mode-week').classList.toggle('active', mode === 'week');
    document.getElementById('view-mode-day').classList.toggle('active', mode === 'day');
    showToast(`Switched view to ${mode}-level.`, "info");
    renderTimetableGrid();
}

function filterScheduleGrid() {
    renderTimetableGrid();
}

function selectAndFilterFaculty(facId) {
    const filterFacSelect = document.getElementById('filter-faculty');
    if (filterFacSelect) {
        filterFacSelect.value = facId;
        // Make sure the filters panel is visible
        const filters = document.getElementById('timetable-filters');
        if (filters) filters.classList.remove('hidden');
        filterScheduleGrid();
        
        const faculty = activeConfig.faculty_list.find(f => f.id === facId);
        if (faculty) {
            showToast(`Showing assignments for ${faculty.name}`, "success");
        }
    }
}

function toggleFiltersPanel() {
    const filters = document.getElementById('timetable-filters');
    filters.classList.toggle('hidden');
}

// Fairness Metrics Renderer
function renderFairnessMetrics() {
    const jainVal = activeResult.jains_fairness_index;
    const giniVal = activeResult.gini_coefficient;
    
    // Text labels
    document.getElementById('jains-index-val').textContent = jainVal.toFixed(3);
    document.getElementById('gini-coefficient-val').textContent = giniVal.toFixed(3);
    
    // Status badges
    const jainBadge = document.getElementById('jains-index-status');
    const jainBar = document.getElementById('jains-index-bar');
    jainBar.style.width = `${jainVal * 100}%`;
    if (jainVal > 0.94) {
        jainBadge.textContent = "Excellent Fairness";
        jainBadge.className = "metric-badge green-badge";
        jainBar.className = "progress-bar green-bar";
    } else if (jainVal > 0.85) {
        jainBadge.textContent = "Good Fairness";
        jainBadge.className = "metric-badge blue-badge";
        jainBar.className = "progress-bar blue-bar";
    } else {
        jainBadge.textContent = "Imbalanced";
        jainBadge.className = "metric-badge red-badge";
        jainBar.className = "progress-bar red-bar";
    }
    
    const giniBadge = document.getElementById('gini-coefficient-status');
    const giniBar = document.getElementById('gini-coefficient-bar');
    giniBar.style.width = `${(1 - giniVal) * 100}%`; // inverted since lower is better
    if (giniVal < 0.1) {
        giniBadge.textContent = "Very Low Inequality";
        giniBadge.className = "metric-badge green-badge";
        giniBar.className = "progress-bar green-bar";
    } else if (giniVal < 0.25) {
        giniBadge.textContent = "Moderate Inequality";
        giniBadge.className = "metric-badge blue-badge";
        giniBar.className = "progress-bar blue-bar";
    } else {
        giniBadge.textContent = "High Inequality";
        giniBadge.className = "metric-badge red-badge";
        giniBar.className = "progress-bar red-bar";
    }
    
    // Animate Balance scale SVG tilt based on gini inequality
    const scaleCrossbar = document.getElementById('scale-crossbar');
    const scaleLeftBowl = document.getElementById('scale-left-bowl');
    const scaleRightBowl = document.getElementById('scale-right-bowl');
    
    // Map gini to rotation degrees (-15deg to +15deg max)
    const tiltDegrees = (giniVal * 28); // tilt based on inequality size
    if (scaleCrossbar) {
        // Pivot points for calculations
        scaleCrossbar.style.transformOrigin = "60px 28px";
        scaleCrossbar.style.transform = `rotate(${tiltDegrees}deg)`;
        scaleCrossbar.style.transition = "transform 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275)";
        
        // Counter rotate bowls to keep them hanging straight down
        if (scaleLeftBowl && scaleRightBowl) {
            scaleLeftBowl.style.transformOrigin = "20px 54px";
            scaleLeftBowl.style.transform = `rotate(${-tiltDegrees}deg)`;
            scaleLeftBowl.style.transition = "transform 0.6s ease";
            
            scaleRightBowl.style.transformOrigin = "100px 54px";
            scaleRightBowl.style.transform = `rotate(${-tiltDegrees}deg)`;
            scaleRightBowl.style.transition = "transform 0.6s ease";
        }
    }
}

// Render conflicts insights
function renderConflictsList() {
    const listContainer = document.getElementById('conflicts-list-container');
    const badge = document.getElementById('conflict-count-badge');
    
    listContainer.innerHTML = '';
    
    // Check conflicts count
    const conflicts = activeResult.conflict_report || [];
    
    if (!activeResult || activeResult.success) {
        badge.textContent = "0 Conflicts";
        badge.className = "badge green-badge";
        listContainer.innerHTML = `<div class="empty-state-text">🎉 No conflicts detected. The schedule is fully feasible!</div>`;
        return;
    }
    
    // Group and count conflicts by categories
    let unavailCount = 0;
    let roomDoubleCount = 0;
    let overlappingCount = 0;
    
    conflicts.forEach(text => {
        if (text.includes("Availability") || text.includes("override")) {
            unavailCount++;
        } else if (text.includes("Duty Per Day") || text.includes("multiple")) {
            overlappingCount++;
        } else if (text.includes("PG Timetable") || text.includes("Conflict")) {
            overlappingCount++;
        } else {
            roomDoubleCount++; // fallback or other violations
        }
    });
    
    badge.textContent = `${conflicts.length} Conflicts`;
    badge.className = "badge red-badge";
    
    // Draw grouped dashboard-style list matching reference image
    if (unavailCount > 0) {
        listContainer.innerHTML += `<div class="conflict-item">
            <span class="conflict-icon">🛑</span>
            <div class="conflict-details">
                <span class="conflict-title">Faculty Unavailability</span>
                <span class="conflict-desc">${unavailCount} faculty members assigned during marked unavailable sessions.</span>
            </div>
        </div>`;
    }
    
    if (overlappingCount > 0) {
        listContainer.innerHTML += `<div class="conflict-item">
            <span class="conflict-icon">⚠️</span>
            <div class="conflict-details">
                <span class="conflict-title">Overlapping Sessions</span>
                <span class="conflict-desc">${overlappingCount} occurrences of lecture blocks or multiple duties on same day.</span>
            </div>
        </div>`;
    }
    
    if (roomDoubleCount > 0) {
        listContainer.innerHTML += `<div class="conflict-item conflict-item-warning">
            <span class="conflict-icon">⚡</span>
            <div class="conflict-details">
                <span class="conflict-title">Coverage Violations</span>
                <span class="conflict-desc">${roomDoubleCount} sessions have unfilled slots due to shortage of faculty supply.</span>
            </div>
        </div>`;
    }
    
    // Detailed logs toggle button
    const detailedLogsId = "conflicts-detailed-logs";
    let detailEl = document.getElementById(detailedLogsId);
    if (!detailEl) {
        detailEl = document.createElement('div');
        detailEl.id = detailedLogsId;
        detailEl.style.marginTop = "12px";
        detailEl.style.fontSize = "10.5px";
        detailEl.style.maxHeight = "120px";
        detailEl.style.overflowY = "auto";
        detailEl.style.padding = "10px";
        detailEl.style.backgroundColor = "#f8fafc";
        detailEl.style.border = "1px solid #e2e8f0";
        detailEl.style.borderRadius = "8px";
        listContainer.parentNode.insertBefore(detailEl, listContainer.nextSibling);
    }
    
    detailEl.innerHTML = `<strong>Detailed Logs:</strong><ul style="margin-left: 14px; margin-top: 4px;">` + 
        conflicts.map(c => `<li style="margin-bottom:4px; color:var(--text-secondary);">${c}</li>`).join('') + `</ul>`;
}

// Render workload distribution doughnut chart rings
function renderWorkloadDistribution() {
    const totalFac = activeConfig.faculty_list.length;
    document.getElementById('donut-total-faculty').textContent = totalFac;
    
    if (totalFac === 0 || !activeResult) return;
    
    // Categorize workloads
    let light = 0, moderate = 0, high = 0, veryHigh = 0;
    
    activeResult.faculty_summaries.forEach(sum => {
        const duties = sum.assigned_sessions.length;
        if (duties <= 3) light++;
        else if (duties <= 6) moderate++;
        else if (duties <= 9) high++;
        else veryHigh++;
    });
    
    // Percents
    const pctLight = Math.round((light / totalFac) * 100);
    const pctMod = Math.round((moderate / totalFac) * 100);
    const pctHigh = Math.round((high / totalFac) * 100);
    const pctVery = Math.round((veryHigh / totalFac) * 100);
    
    document.getElementById('pct-light').textContent = `${pctLight}%`;
    document.getElementById('pct-moderate').textContent = `${pctMod}%`;
    document.getElementById('pct-high').textContent = `${pctHigh}%`;
    document.getElementById('pct-veryhigh').textContent = `${pctVery}%`;
    
    // Visual indicators rings calculations: Circumference = 2 * PI * r = 2 * 3.14159 * 38 = 238.76
    const circ = 238.76;
    
    const rGreen = document.getElementById('donut-ring-green');
    const rBlue = document.getElementById('donut-ring-blue');
    const rOrange = document.getElementById('donut-ring-orange');
    const rRed = document.getElementById('donut-ring-red');
    
    // Calculate stroke widths
    const lenLight = (light / totalFac) * circ;
    const lenMod = (moderate / totalFac) * circ;
    const lenHigh = (high / totalFac) * circ;
    const lenVery = (veryHigh / totalFac) * circ;
    
    rGreen.style.strokeDasharray = `${lenLight} ${circ}`;
    rGreen.style.strokeDashoffset = `0`;
    
    rBlue.style.strokeDasharray = `${lenMod} ${circ}`;
    rBlue.style.strokeDashoffset = `-${lenLight}`;
    
    rOrange.style.strokeDasharray = `${lenHigh} ${circ}`;
    rOrange.style.strokeDashoffset = `-${lenLight + lenMod}`;
    
    rRed.style.strokeDasharray = `${lenVery} ${circ}`;
    rRed.style.strokeDashoffset = `-${lenLight + lenMod + lenHigh}`;
}

// Sparklines Charts Render
function renderBottomSparklines(totalAllocations) {
    if (!activeResult || activeResult.faculty_summaries.length === 0) return;
    
    const dutiesCounts = activeResult.faculty_summaries.map(s => s.assigned_sessions.length);
    const avg = dutiesCounts.reduce((a,b)=>a+b, 0) / dutiesCounts.length;
    const maxVal = Math.max(...dutiesCounts);
    const minVal = Math.min(...dutiesCounts);
    
    // Find faculty names matching limits
    const maxFac = activeResult.faculty_summaries.find(s => s.assigned_sessions.length === maxVal);
    const minFac = activeResult.faculty_summaries.find(s => s.assigned_sessions.length === minVal);
    
    document.getElementById('metric-avg-duties').textContent = avg.toFixed(1);
    document.getElementById('metric-max-duties').textContent = maxVal;
    document.getElementById('metric-max-name').textContent = maxFac ? maxFac.name.split(" ").slice(1).join(" ") || maxFac.name : "-";
    document.getElementById('metric-min-duties').textContent = minVal;
    document.getElementById('metric-min-name').textContent = minFac ? minFac.name.split(" ").slice(1).join(" ") || minFac.name : "-";
    
    // Unassigned count
    const totalRequired = activeConfig.sessions.reduce((acc, curr) => acc + curr.required_invigilators, 0);
    const missing = totalRequired - totalAllocations;
    document.getElementById('metric-unassigned').textContent = missing;
    
    const unbadge = document.getElementById('metric-unassigned-badge');
    const shield = document.getElementById('unassigned-status-shield');
    if (missing === 0) {
        unbadge.textContent = "All Clear";
        unbadge.className = "badge-mini green-badge";
        shield.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="#38a169" /><path d="M9 11l2 2 4-4" stroke="#fff" stroke-width="2" fill="none" /></svg>`;
    } else {
        unbadge.textContent = `${missing} Vacant`;
        unbadge.className = "badge-mini red-badge";
        shield.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="#e53e3e" /><path d="M12 7v6m0 4h.01" stroke="#fff" stroke-width="2" stroke-linecap="round" fill="none" /></svg>`;
    }
    
    // Draw sparklines graphs
    drawSparklineSvg('sparkline-avg', dutiesCounts, '#0f3ba2');
    drawSparklineSvg('sparkline-max', dutiesCounts.map(v => v === maxVal ? v*1.1 : v), '#ef4444');
    drawSparklineSvg('sparkline-min', dutiesCounts.map(v => v === minVal ? v*0.5 : v), '#10b981');
}

function drawSparklineSvg(svgId, dataPoints, strokeColor) {
    const svg = document.getElementById(svgId);
    if (!svg) return;
    
    const width = 100;
    const height = 30;
    const max = Math.max(...dataPoints, 1);
    const min = Math.min(...dataPoints, 0);
    
    let pathD = '';
    const length = dataPoints.length;
    
    dataPoints.forEach((val, idx) => {
        const x = (idx / (length - 1)) * width;
        const y = height - ((val - min) / (max - min)) * (height - 6) - 3; // buffer top/bottom
        
        if (idx === 0) {
            pathD = `M ${x},${y}`;
        } else {
            pathD += ` L ${x},${y}`;
        }
    });
    
    svg.innerHTML = `<path d="${pathD}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
}

// History load balancing table renderer
function renderHistoryImpactTable() {
    const tbody = document.getElementById('history-impact-tbody');
    tbody.innerHTML = '';
    
    if (!activeResult || activeResult.faculty_summaries.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state-text">No load impact summaries available. Run the solver.</td></tr>`;
        return;
    }
    
    // Sync summary header text
    document.getElementById('history-impact-summary-text').textContent = activeResult.history_impact_report;
    
    activeResult.faculty_summaries.forEach(sum => {
        let prevImb = sum.historical_imbalance;
        let finalImb = sum.cumulative_imbalance;
        let change = finalImb - prevImb;
        
        let statusClass = 'green-badge';
        if (sum.impact_status === 'WORSENED') {
            statusClass = 'red-badge';
        } else if (sum.impact_status === 'NEUTRAL') {
            statusClass = 'blue-badge';
        }
        
        let changeStr = change > 0 ? `+${change.toFixed(1)}` : change.toFixed(1);
        
        tbody.innerHTML += `<tr>
            <td><strong>${sum.faculty_id}</strong></td>
            <td>${sum.name}</td>
            <td><span class="badge-mini ${sum.category_name.includes('Prof') ? 'blue-badge' : 'green-badge'}">${sum.category_name}</span></td>
            <td>${prevImb > 0 ? '+' : ''}${prevImb.toFixed(1)}</td>
            <td>${sum.assigned_sessions.length} duties</td>
            <td>${sum.assigned_hours.toFixed(1)} hrs</td>
            <td><code>${changeStr}</code></td>
            <td><strong>${finalImb > 0 ? '+' : ''}${finalImb.toFixed(1)}</strong></td>
            <td><span class="history-change-tag ${statusClass}">${sum.impact_status}</span></td>
        </tr>`;
    });
}

// CONFIGURATION MODALS INTERACTIVITY
function openSettingsModal(tabName = 'general') {
    document.getElementById('settings-modal').classList.remove('hidden');
    switchModalTab(tabName);
    
    // Sync direct JSON text editor area
    document.getElementById('raw-json-textarea').value = JSON.stringify(activeConfig, null, 4);
}

function closeSettingsModal() {
    document.getElementById('settings-modal').classList.add('hidden');
}

function switchModalTab(tabName) {
    currentModalTab = tabName;
    
    // Toggle active state headers
    const tabs = ['general', 'faculty', 'sessions', 'json'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-btn-${t}`);
        const pane = document.getElementById(`pane-${t}`);
        
        if (btn) btn.classList.toggle('active', t === tabName);
        if (pane) pane.classList.toggle('hidden', t !== tabName);
    });
    
    // Trigger tab specific sub-renders
    if (tabName === 'general') {
        renderGeneralWeightsForm();
    } else if (tabName === 'faculty') {
        renderFacultyTabList();
    } else if (tabName === 'sessions') {
        renderSessionsTabList();
    }
}

// Modal TAB 1: General settings
function renderGeneralWeightsForm() {
    const container = document.getElementById('category-weights-list');
    container.innerHTML = '';
    
    const categories = activeConfig.categories || [];
    
    if (Array.isArray(categories)) {
        categories.forEach((cat, index) => {
            container.innerHTML += `<div class="cat-weight-row" id="cat-weight-row-${index}">
                <input type="text" class="form-group cat-name-input" value="${cat.name}" onchange="updateCategoryName(${index}, this.value)" placeholder="Category Name" required>
                <input type="number" step="0.1" class="form-group cat-weight-input" value="${cat.ratio_weight}" onchange="updateCategoryWeight(${index}, this.value)" placeholder="Ratio Weight" required>
                <button type="button" class="remove-cat-btn" onclick="removeCategoryRow(${index})">✕</button>
            </div>`;
        });
    }
}

function addCategoryRow() {
    activeConfig.categories.push({ name: "New Category", ratio_weight: 1.0 });
    renderGeneralWeightsForm();
    saveConfigToBackend(true);
}

function removeCategoryRow(index) {
    activeConfig.categories.splice(index, 1);
    renderGeneralWeightsForm();
    saveConfigToBackend(true);
}

function updateCategoryName(index, val) {
    activeConfig.categories[index].name = val;
    saveConfigToBackend(true);
}

function updateCategoryWeight(index, val) {
    activeConfig.categories[index].ratio_weight = parseFloat(val);
    saveConfigToBackend(true);
}

function saveGeneralSettings(event) {
    event.preventDefault();
    
    activeConfig.exam_type = document.getElementById('setting-exam-type').value;
    activeConfig.category_ratio_mode = document.getElementById('setting-ratio-mode').value;
    activeConfig.exam_start_date = document.getElementById('setting-exam-start-date').value;
    
    saveConfigToBackend();
    syncUIWithConfig();
    closeSettingsModal();
    
    // Re-run solver silently to update UI
    triggerSolve(true);
}

function applyBulkShiftRequirements() {
    const morningCount = parseInt(document.getElementById('bulk-morning-req').value);
    const afternoonCount = parseInt(document.getElementById('bulk-afternoon-req').value);

    if (isNaN(morningCount) || isNaN(afternoonCount) || morningCount < 0 || afternoonCount < 0) {
        showToast("Enter valid numbers for both Morning and Afternoon.", "error");
        return;
    }

    activeConfig.sessions.forEach(s => {
        if (s.session_num === 1) {
            s.required_invigilators = morningCount;
        } else if (s.session_num === 2) {
            s.required_invigilators = afternoonCount;
        }
    });

    saveConfigToBackend(false).then(() => {
        showToast(`Applied Morning=${morningCount}, Afternoon=${afternoonCount} across all 6 days.`, "success");
        triggerSolve(false);
    });
}

// Modal TAB 2: Faculty list (Master Detail)
function renderFacultyTabList() {
    const listContainer = document.getElementById('faculty-items-list');
    const searchVal = document.getElementById('faculty-list-search').value.toLowerCase();
    
    listContainer.innerHTML = '';
    
    const filtered = activeConfig.faculty_list.filter(f => 
        f.name.toLowerCase().includes(searchVal) || f.id.toLowerCase().includes(searchVal)
    );
    
    if (filtered.length === 0) {
        listContainer.innerHTML = `<div class="empty-state-text">No faculty matching query.</div>`;
        return;
    }
    
    filtered.forEach(fac => {
        let activeClass = fac.id === selectedFacultyId ? 'list-item-row active' : 'list-item-row';
        listContainer.innerHTML += `<div class="${activeClass}" onclick="selectFacultyItem('${fac.id}')">
            <div>
                <strong>${fac.name}</strong>
                <div class="list-item-sub">${fac.id} • ${fac.category_name} • 📞 ${fac.phone || 'N/A'}</div>
            </div>
            <span class="list-item-sub">✏️</span>
        </div>`;
    });
    
    // Auto open first if nothing selected
    if (!selectedFacultyId && filtered.length > 0) {
        selectFacultyItem(filtered[0].id);
    }
}

function selectFacultyItem(facId) {
    selectedFacultyId = facId;
    
    // highlight selected row
    renderFacultyTabList();
    
    const detailPanel = document.getElementById('faculty-detail-panel');
    const faculty = activeConfig.faculty_list.find(f => f.id === facId);
    
    if (!faculty) {
        detailPanel.innerHTML = `<div class="empty-state-text">Faculty not found.</div>`;
        return;
    }
    
    // Find history record if exists
    const histRecord = activeConfig.history.find(h => h.faculty_id === facId);
    const prevImbalance = histRecord ? histRecord.previous_imbalance : 0.0;
    
    // Build options for category select
    const categories = getCategoriesList();
    let catOptions = '';
    categories.forEach(cat => {
        catOptions += `<option value="${cat}" ${cat === faculty.category_name ? 'selected' : ''}>${cat}</option>`;
    });
    
    // Build checkboxes for availability overrides and PG blocks
    let unavailCheckboxes = '';
    let pgCheckboxes = '';
    
    activeConfig.sessions.forEach(sess => {
        const isUnavail = faculty.availability_overrides.includes(sess.id);
        unavailCheckboxes += `<label class="checkbox-item">
            <input type="checkbox" id="unavail-${sess.id}" ${isUnavail ? 'checked' : ''} onchange="toggleFacultyUnavail('${facId}', '${sess.id}', this.checked)">
            ${sess.label} (${sess.id})
        </label>`;
        
        const isPg = faculty.pg_timetable_blocks.includes(sess.id);
        pgCheckboxes += `<label class="checkbox-item">
            <input type="checkbox" id="pgblock-${sess.id}" ${isPg ? 'checked' : ''} onchange="toggleFacultyPgBlock('${facId}', '${sess.id}', this.checked)">
            ${sess.label} (${sess.id})
        </label>`;
    });

    detailPanel.innerHTML = `<div class="detail-header">
        <h4>Edit Faculty: ${faculty.name}</h4>
        <button class="btn btn-secondary btn-small" style="color: var(--color-danger); border-color:#fca5a5;" onclick="deleteFaculty('${facId}')">Delete Faculty</button>
    </div>
    <div class="detail-body">
        <div class="form-row">
            <div class="form-group col-6">
                <label>Faculty Name</label>
                <input type="text" value="${faculty.name}" onchange="updateFacultyField('${facId}', 'name', this.value)">
            </div>
            <div class="form-group col-6">
                <label>Category</label>
                <select onchange="updateFacultyField('${facId}', 'category_name', this.value)">
                    ${catOptions}
                </select>
            </div>
        </div>
        
        <div class="form-row">
            <div class="form-group col-4">
                <label>Faculty ID (Cannot be changed)</label>
                <input type="text" value="${faculty.id}" readonly disabled style="background-color:#edf2f7; color:var(--text-light)">
            </div>
            <div class="form-group col-4">
                <label>Previous Workload Imbalance (Hours)</label>
                <input type="number" step="0.1" value="${prevImbalance}" onchange="updateFacultyHistory('${facId}', this.value)">
            </div>
            <div class="form-group col-4">
                <label>Phone Number</label>
                <input type="text" value="${faculty.phone || ''}" onchange="updateFacultyField('${facId}', 'phone', this.value)">
            </div>
        </div>

        <div class="form-group">
            <label>Availability Overrides (Check if UNAVAILABLE)</label>
            <div class="checkbox-grid">
                ${unavailCheckboxes || '<span class="text-light">No sessions configured</span>'}
            </div>
        </div>

        <div class="form-group">
            <label>PG Timetable Lecture Blocks (Check if teaching/busy during slot)</label>
            <div class="checkbox-grid">
                ${pgCheckboxes || '<span class="text-light">No sessions configured</span>'}
            </div>
        </div>
        
        <div class="form-actions mt-4">
            <button class="btn btn-primary" onclick="saveConfigToBackend()">Save Details</button>
        </div>
    </div>`;
}

function createNewFacultyForm() {
    const detailPanel = document.getElementById('faculty-detail-panel');
    const categories = getCategoriesList();
    let catOptions = '';
    categories.forEach(cat => {
        catOptions += `<option value="${cat}">${cat}</option>`;
    });

    detailPanel.innerHTML = `<div class="detail-header">
        <h4>Create New Faculty Member</h4>
    </div>
    <form onsubmit="handleCreateFaculty(event)" class="detail-body">
        <div class="form-row">
            <div class="form-group col-6">
                <label for="new-fac-name">Faculty Name</label>
                <input type="text" id="new-fac-name" placeholder="e.g. Prof. Ayush Kumar" required>
            </div>
            <div class="form-group col-6">
                <label for="new-fac-cat">Category</label>
                <select id="new-fac-cat" required>
                    ${catOptions}
                </select>
            </div>
        </div>
        <div class="form-row">
            <div class="form-group col-4">
                <label for="new-fac-id">Faculty ID (Unique)</label>
                <input type="text" id="new-fac-id" placeholder="e.g. AP5" required>
            </div>
            <div class="form-group col-4">
                <label for="new-fac-imb">Initial Imbalance Balance (Hours)</label>
                <input type="number" step="0.1" id="new-fac-imb" value="0.0">
            </div>
            <div class="form-group col-4">
                <label for="new-fac-phone">Phone Number</label>
                <input type="text" id="new-fac-phone" placeholder="e.g. +91 9999999999">
            </div>
        </div>
        <div class="form-actions mt-4">
            <button type="submit" class="btn btn-primary">Create Faculty</button>
        </div>
    </form>`;
}

function handleCreateFaculty(event) {
    event.preventDefault();
    const id = document.getElementById('new-fac-id').value.trim();
    const name = document.getElementById('new-fac-name').value.trim();
    const cat = document.getElementById('new-fac-cat').value;
    const imb = parseFloat(document.getElementById('new-fac-imb').value || 0.0);
    const phone = document.getElementById('new-fac-phone').value.trim();
    
    // Check duplicates
    if (activeConfig.faculty_list.some(f => f.id === id)) {
        showToast("Error: Faculty ID already exists.", "error");
        return;
    }
    
    activeConfig.faculty_list.push({
        id: id,
        name: name,
        category_name: cat,
        phone: phone,
        pg_timetable_blocks: [],
        availability_overrides: []
    });
    
    activeConfig.history.push({
        faculty_id: id,
        previous_imbalance: imb
    });
    
    selectedFacultyId = id;
    saveConfigToBackend();
    syncUIWithConfig();
    renderFacultyTabList();
    selectFacultyItem(id);
}

function deleteFaculty(facId) {
    if (!confirm(`Are you sure you want to delete faculty ${facId}?`)) return;
    
    activeConfig.faculty_list = activeConfig.faculty_list.filter(f => f.id !== facId);
    activeConfig.history = activeConfig.history.filter(h => h.faculty_id !== facId);
    
    selectedFacultyId = null;
    saveConfigToBackend();
    syncUIWithConfig();
    renderFacultyTabList();
}

function updateFacultyField(facId, field, value) {
    const faculty = activeConfig.faculty_list.find(f => f.id === facId);
    if (faculty) {
        faculty[field] = value;
        saveConfigToBackend(true);
    }
}

function updateFacultyHistory(facId, value) {
    const record = activeConfig.history.find(h => h.faculty_id === facId);
    const fl_val = parseFloat(value || 0.0);
    if (record) {
        record.previous_imbalance = fl_val;
    } else {
        activeConfig.history.push({ faculty_id: facId, previous_imbalance: fl_val });
    }
    saveConfigToBackend(true);
}

function toggleFacultyUnavail(facId, sessId, checked) {
    const faculty = activeConfig.faculty_list.find(f => f.id === facId);
    if (faculty) {
        if (checked) {
            if (!faculty.availability_overrides.includes(sessId)) {
                faculty.availability_overrides.push(sessId);
            }
        } else {
            faculty.availability_overrides = faculty.availability_overrides.filter(id => id !== sessId);
        }
        saveConfigToBackend(true);
    }
}

function toggleFacultyPgBlock(facId, sessId, checked) {
    const faculty = activeConfig.faculty_list.find(f => f.id === facId);
    if (faculty) {
        if (checked) {
            if (!faculty.pg_timetable_blocks.includes(sessId)) {
                faculty.pg_timetable_blocks.push(sessId);
            }
        } else {
            faculty.pg_timetable_blocks = faculty.pg_timetable_blocks.filter(id => id !== sessId);
        }
        saveConfigToBackend(true);
    }
}

// Modal TAB 3: Sessions config (Master Detail)
function renderSessionsTabList() {
    const listContainer = document.getElementById('sessions-items-list');
    const searchVal = document.getElementById('sessions-list-search').value.toLowerCase();
    
    listContainer.innerHTML = '';
    
    const filtered = activeConfig.sessions.filter(s => 
        s.id.toLowerCase().includes(searchVal) || s.label.toLowerCase().includes(searchVal)
    );
    
    if (filtered.length === 0) {
        listContainer.innerHTML = `<div class="empty-state-text">No sessions matching query.</div>`;
        return;
    }
    
    const dayNamesMap = {
        1: "Monday",
        2: "Tuesday",
        3: "Wednesday",
        4: "Thursday",
        5: "Friday",
        6: "Saturday"
    };
    
    filtered.forEach(sess => {
        let activeClass = sess.id === selectedSessionId ? 'list-item-row active' : 'list-item-row';
        const dayLabel = dayNamesMap[sess.day] || ('Day ' + sess.day);
        listContainer.innerHTML += `<div class="${activeClass}" onclick="selectSessionItem('${sess.id}')">
            <div>
                <strong>${sess.label || (getDayName(sess.day) + ' ' + (sess.session_num === 1 ? 'FN' : 'AN'))} (${sess.id})</strong>
                <div class="list-item-sub">${dayLabel} • Req: ${sess.required_invigilators}</div>
            </div>
            <span class="list-item-sub">✏️</span>
        </div>`;
    });
    
    // Auto open first if nothing selected
    if (!selectedSessionId && filtered.length > 0) {
        selectSessionItem(filtered[0].id);
    }
}

function selectSessionItem(sessId) {
    selectedSessionId = sessId;
    renderSessionsTabList();
    
    const detailPanel = document.getElementById('sessions-detail-panel');
    const session = activeConfig.sessions.find(s => s.id === sessId);
    
    if (!session) {
        detailPanel.innerHTML = `<div class="empty-state-text">Session not found.</div>`;
        return;
    }

    detailPanel.innerHTML = `<div class="detail-header">
        <h4>Edit Session: ${session.id}</h4>
        <button class="btn btn-secondary btn-small" style="color: var(--color-danger); border-color:#fca5a5;" onclick="deleteSession('${sessId}')">Delete Session</button>
    </div>
    <div class="detail-body">
        <div class="form-row">
            <div class="form-group col-6">
                <label>Session Label</label>
                <input type="text" value="${session.label}" onchange="updateSessionField('${sessId}', 'label', this.value)">
            </div>
            <div class="form-group col-6">
                <label>Required Invigilators</label>
                <input type="number" value="${session.required_invigilators}" onchange="updateSessionField('${sessId}', 'required_invigilators', parseInt(this.value))">
            </div>
        </div>
        
        <div class="form-row">
            <div class="form-group col-6">
                <label>Day Number (1 to 6)</label>
                <input type="number" min="1" max="6" value="${session.day}" onchange="updateSessionField('${sessId}', 'day', parseInt(this.value))">
            </div>
            <div class="form-group col-6">
                <label>Session Number (1=Morning, 2=Afternoon)</label>
                <input type="number" min="1" max="2" value="${session.session_num}" onchange="updateSessionField('${sessId}', 'session_num', parseInt(this.value))">
            </div>
        </div>

        <div class="form-row">
            <div class="form-group col-6">
                <label>Day Workload Weight (e.g. 1.5 for Saturdays)</label>
                <input type="number" step="0.1" value="${session.day_weight || 1.0}" onchange="updateSessionField('${sessId}', 'day_weight', parseFloat(this.value))">
            </div>
            <div class="form-group col-6">
                <label>Duration (Hours)</label>
                <input type="number" step="0.5" value="${session.duration_hours || 2.0}" onchange="updateSessionField('${sessId}', 'duration_hours', parseFloat(this.value))">
            </div>
        </div>
        
        <div class="form-actions mt-4">
            <button class="btn btn-primary" onclick="saveConfigToBackend()">Save Details</button>
        </div>
    </div>`;
}

function createNewSessionForm() {
    const detailPanel = document.getElementById('sessions-detail-panel');

    detailPanel.innerHTML = `<div class="detail-header">
        <h4>Create New Exam Session</h4>
    </div>
    <form onsubmit="handleCreateSession(event)" class="detail-body">
        <div class="form-row">
            <div class="form-group col-6">
                <label for="new-sess-id">Session ID (Unique)</label>
                <input type="text" id="new-sess-id" placeholder="e.g. D11" required>
            </div>
            <div class="form-group col-6">
                <label for="new-sess-label">Session Label</label>
                <input type="text" id="new-sess-label" placeholder="e.g. Monday FN" required>
            </div>
        </div>
        <div class="form-row">
            <div class="form-group col-6">
                <label for="new-sess-day">Day Number (1 to 6)</label>
                <input type="number" min="1" max="6" id="new-sess-day" value="1" required>
            </div>
            <div class="form-group col-6">
                <label for="new-sess-num">Session Number (1=Morning, 2=Afternoon)</label>
                <input type="number" min="1" max="2" id="new-sess-num" value="1" required>
            </div>
        </div>
        <div class="form-row">
            <div class="form-group col-6">
                <label for="new-sess-req">Required Invigilators</label>
                <input type="number" min="1" id="new-sess-req" value="2" required>
            </div>
            <div class="form-group col-6">
                <label for="new-sess-weight">Day Weight (1.0 weekday, 1.5 Saturday)</label>
                <input type="number" step="0.1" id="new-sess-weight" value="1.0">
            </div>
        </div>
        <div class="form-actions mt-4">
            <button type="submit" class="btn btn-primary">Create Session</button>
        </div>
    </form>
}`;
}

function handleCreateSession(event) {
    event.preventDefault();
    const id = document.getElementById('new-sess-id').value.trim();
    const label = document.getElementById('new-sess-label').value.trim();
    const day = parseInt(document.getElementById('new-sess-day').value);
    const num = parseInt(document.getElementById('new-sess-num').value);
    const req = parseInt(document.getElementById('new-sess-req').value);
    const weight = parseFloat(document.getElementById('new-sess-weight').value || 1.0);
    
    // Check duplicates
    if (activeConfig.sessions.some(s => s.id === id)) {
        showToast("Error: Session ID already exists.", "error");
        return;
    }
    
    activeConfig.sessions.push({
        id: id,
        day: day,
        session_num: num,
        label: label,
        required_invigilators: req,
        day_weight: weight,
        duration_hours: activeConfig.exam_type === 'midsem' ? 2.0 : 3.0
    });
    
    selectedSessionId = id;
    saveConfigToBackend();
    syncUIWithConfig();
    renderSessionsTabList();
    selectSessionItem(id);
}

function deleteSession(sessId) {
    if (!confirm(`Are you sure you want to delete session ${sessId}?`)) return;
    
    activeConfig.sessions = activeConfig.sessions.filter(s => s.id !== sessId);
    
    // Remove overrides and blocks references in faculty
    activeConfig.faculty_list.forEach(f => {
        f.availability_overrides = f.availability_overrides.filter(id => id !== sessId);
        f.pg_timetable_blocks = f.pg_timetable_blocks.filter(id => id !== sessId);
    });
    
    selectedSessionId = null;
    saveConfigToBackend();
    syncUIWithConfig();
    renderSessionsTabList();
}

function updateSessionField(sessId, field, value) {
    const session = activeConfig.sessions.find(s => s.id === sessId);
    if (session) {
        session[field] = value;
        saveConfigToBackend(true);
    }
}

// Modal TAB 4: Raw JSON editing
function saveRawJson() {
    const textarea = document.getElementById('raw-json-textarea');
    try {
        const parsed = JSON.parse(textarea.value);
        activeConfig = parsed;
        
        saveConfigToBackend();
        syncUIWithConfig();
        closeSettingsModal();
        showToast("Raw JSON config updated and loaded successfully!", "success");
        
        // Re-run solver silently
        triggerSolve(true);
    } catch (err) {
        showToast("JSON syntax error: " + err.message, "error");
    }
}

// Navigation helpers
function scrollToElement(id) {
    const el = document.getElementById(id);
    if (el) {
        el.scrollIntoView({ behavior: 'smooth' });
    }
}

function exportConfig() {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(activeConfig, null, 4));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `invigilation_config_${activeConfig.exam_type}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
    showToast("Configuration JSON exported.", "success");
}

function shiftTimetableRange(offset) {
    activeTimetableWeekOffset += offset;
    
    // Refresh header dates representation
    const startRange = getTimetableRangeLabel(activeTimetableWeekOffset);
    document.getElementById('timetable-range-label').textContent = startRange;
    
    showToast(`Navigated to week page offset ${activeTimetableWeekOffset > 0 ? '+' : ''}${activeTimetableWeekOffset}`, "info");
    renderTimetableGrid();
}

function openHelpModal() {
    document.getElementById('help-modal').classList.remove('hidden');
}

function closeHelpModal() {
    document.getElementById('help-modal').classList.add('hidden');
}

async function resetHistoryData() {
    if (!confirm("Are you sure you want to reset the workload history of all faculty members to 0.0? This will update the server config.")) return;
    
    try {
        if (activeConfig.history) {
            activeConfig.history.forEach(h => {
                h.previous_imbalance = 0.0;
            });
        } else {
            activeConfig.history = [];
        }
        
        // Save the updated configuration to backend
        await saveConfigToBackend(false);
        showToast("Workload history successfully reset to zero!", "success");
        
        // Re-solve silently to update UI metrics
        triggerSolve(true);
    } catch (err) {
        showToast("Error resetting history: " + err.message, "error");
    }
}

async function showFacultyWeeklyReport(facId) {
    try {
        const response = await fetch(`/api/faculty/${facId}/weekly-report`);
        if (!response.ok) throw new Error("Failed to fetch faculty report.");
        const data = await response.json();
        
        const faculty = activeConfig.faculty_list.find(f => f.id === facId);
        const phone = faculty ? (faculty.phone || 'N/A') : 'N/A';
        document.getElementById('faculty-report-title').textContent = `${data.name} (${data.faculty_id}) 📞 ${phone} - Schedule`;
        document.getElementById('fac-rep-category').textContent = data.category_name;
        document.getElementById('fac-rep-hours').textContent = `${data.assigned_hours.toFixed(1)} hrs (${data.assigned_sessions.length} sessions)`;
        document.getElementById('fac-rep-target').textContent = `${data.target_load.toFixed(1)} hrs`;
        document.getElementById('fac-rep-imbalance').textContent = `${data.cumulative_imbalance > 0 ? '+' : ''}${data.cumulative_imbalance.toFixed(1)} hrs`;
        
        const tbody = document.getElementById('faculty-report-tbody');
        tbody.innerHTML = '';
        
        if (data.assigned_sessions.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="empty-state-text">No invigilation duties assigned for this week.</td></tr>`;
        } else {
            // Sort sessions by day_num and start_time
            data.assigned_sessions.sort((a, b) => {
                if (a.day_num !== b.day_num) return a.day_num - b.day_num;
                return a.start_time - b.start_time;
            });
            
            data.assigned_sessions.forEach(sess => {
                tbody.innerHTML += `<tr>
                    <td><strong>${sess.day_name}</strong></td>
                    <td>${sess.shift}</td>
                    <td>${sess.label}</td>
                    <td>
                        <div>Official: <code>${sess.start_time_display}</code> (${sess.duration_hours} hrs)</div>
                        <div style="font-size: 0.85em; margin-top: 4px; color: #4f46e5;">Reporting Time: <code>${sess.display_reporting_time || sess.start_time_display}</code></div>
                    </td>
                </tr>`;
            });
        }
        
        document.getElementById('faculty-report-modal').classList.remove('hidden');
    } catch (err) {
        showToast("Error loading faculty report: " + err.message, "error");
    }
}

function closeFacultyReportModal() {
    document.getElementById('faculty-report-modal').classList.add('hidden');
}

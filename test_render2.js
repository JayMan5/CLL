const fs = require('fs');
const casesData = Object.values(JSON.parse(fs.readFileSync('data/cases.json', 'utf8')));

// Mocks for DOM elements
const document = {
    getElementById: (id) => ({
        innerHTML: '',
        appendChild: () => {},
        classList: { add: () => {}, remove: () => {} },
        style: {}
    }),
    createElement: () => ({ innerHTML: '' })
};

function renderHeatmapTable(cases) {
    const tableBody = document.getElementById("heatmap-table-body");
    tableBody.innerHTML = "";
    const sorted = [...cases].sort((a,b) => b.delay_risk_score - a.delay_risk_score);
    sorted.forEach(c => {
        let badgeHtml = c.risk_flag ? \<span class="badge badge-high badge-pulse">High Risk</span>\ : \<span class="badge badge-low">Normal</span>\;
        const row = document.createElement("tr");
        row.innerHTML = \<td class="py-2.5 px-3 font-mono text-heading">\</td>\;
        tableBody.appendChild(row);
    });
}

function renderDCRTable() {
    const tableBody = document.getElementById("dcr-table-body");
    tableBody.innerHTML = "";
    const pendingOverrides = casesData.filter(c => c.dcr_approval_required);
    pendingOverrides.forEach(c => {
        const row = document.createElement("tr");
        row.innerHTML = \<td>\</td>\;
        tableBody.appendChild(row);
    });
}

function renderJudgeDocketTable() {
    const tableBody = document.getElementById("judge-docket-body");
    tableBody.innerHTML = "";
    // In real code, it filters by logged-in judge. We'll use mock.
    const judgeCases = casesData.filter(c => c.assigned_judge_id === "usr_judge_01");
    judgeCases.forEach(c => {
        const row = document.createElement("tr");
        row.innerHTML = \<td>\</td>\;
        tableBody.appendChild(row);
    });
}

function populateDropdowns() {
    const caseSelects = [document.getElementById("dcr-case-select"), document.getElementById("writ-case-select")];
    caseSelects.forEach(select => {
        select.innerHTML = '<option value="">Select case from table...</option>';
        casesData.forEach(c => {
            select.innerHTML += \<option value="\">\ - \</option>\;
        });
    });
}

try {
    renderHeatmapTable(casesData);
    console.log("Heatmap rendered");
    renderDCRTable();
    console.log("DCR rendered");
    renderJudgeDocketTable();
    console.log("Judge rendered");
    populateDropdowns();
    console.log("Dropdowns populated");
} catch(e) {
    console.error("Error before execution table:", e);
}

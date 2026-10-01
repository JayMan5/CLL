const fs = require('fs');
const casesData = Object.values(JSON.parse(fs.readFileSync('data/cases.json', 'utf8')));

const judgments = casesData.filter(c => c.judgment_status === "Judgment Delivered");
console.log("Judgments count:", judgments.length);

try {
    judgments.forEach(c => {
        let deliveryDate = "N/A";
        const deliveryEvent = (c.execution_log || []).find(e => {
            if (!e.action) console.log("Missing action in event:", e);
            return e.action && e.action.includes("Delivered");
        });
        
        const enforceActions = (c.execution_log || []).filter(e => e.action && !e.action.includes("Delivered"));
        console.log("Passed case:", c.case_id);
    });
} catch(e) {
    console.error("Error:", e);
}

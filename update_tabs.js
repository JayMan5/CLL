const fs = require('fs');
let code = fs.readFileSync('frontend/app.js', 'utf8');

// The line is: document.getElementById(tabId).classList.remove('hidden');
// Change to: const targetTab = document.getElementById(tabId); targetTab.classList.remove('hidden'); targetTab.classList.add('tab-enter');

code = code.replace(/document\.getElementById\(tabId\)\.classList\.remove\('hidden'\);/g, 
"const targetTab = document.getElementById(tabId);\n    targetTab.classList.remove('hidden');\n    targetTab.classList.add('tab-enter');");

fs.writeFileSync('frontend/app.js', code);
console.log("Updated app.js tabs");

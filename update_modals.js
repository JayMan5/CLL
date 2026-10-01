const fs = require('fs');
let code = fs.readFileSync('frontend/app.js', 'utf8');

const helper = 
function animateOpenModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.remove("hidden");
    const panel = m.querySelector('.glass-panel') || m.firstElementChild;
    if (panel) {
        panel.style.animation = "modalSpring 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.2) forwards";
    }
}

function animateCloseModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    const panel = m.querySelector('.glass-panel') || m.firstElementChild;
    if (panel) {
        panel.style.animation = "dropdownFade 0.2s cubic-bezier(0.25, 1, 0.5, 1) reverse forwards";
        setTimeout(() => {
            m.classList.add("hidden");
            panel.style.animation = "";
        }, 180);
    } else {
        m.classList.add("hidden");
    }
}
;

// Prepend helper
code = helper + "\n" + code;

// Replace open calls
code = code.replace(/document\.getElementById\("([^"]+)"\)\.classList\.remove\("hidden"\);/g, 'animateOpenModal("");');

// Replace close calls
code = code.replace(/document\.getElementById\("([^"]+)"\)\.classList\.add\("hidden"\);/g, 'animateCloseModal("");');

fs.writeFileSync('frontend/app.js', code);
console.log("Updated app.js modals");

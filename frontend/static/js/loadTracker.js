async function loadGlobalTracker() {
    try {
        const response = await fetch('../shared/tracker_employee.html');
        const html = await response.text();
        document.getElementById('tracker-container').innerHTML = html;

        // Wait for tracker.js to attach
        setTimeout(() => {
            if (window.Tracker && window.Tracker.refresh) {
                window.Tracker.refresh();
            }
        }, 200);

    } catch (error) {
        console.error("Tracker load failed:", error);
    }
}
window.loadTracker = loadGlobalTracker;
// Auto initialize
document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("tracker-container")) {
        loadGlobalTracker();
    }
});
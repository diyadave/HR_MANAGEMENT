const BASE_URL = "http://127.0.0.1:8000";

async function apiRequest(endpoint, method = "GET", body = null) {
    const token = localStorage.getItem("access_token");

    const headers = {
        "Content-Type": "application/json",
    };

    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${BASE_URL}${endpoint}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : null,
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || "Request failed");
    }

    return response.json();
}

window.API = {
    // Auth
    login: (data) => apiRequest("/auth/login", "POST", data),

    // Tasks
    getMyTasks: () => apiRequest("/tasks/"),
    getActiveTask: () => apiRequest("/tasks/active"),
    startTask: (taskId) => apiRequest(`/tasks/${taskId}/start`, "POST"),
    stopTask: (taskId) => apiRequest(`/tasks/${taskId}/stop`, "POST"),

    // Attendance
    clockIn: () => apiRequest("/attendance/clock-in", "POST"),
    clockOut: () => apiRequest("/attendance/clock-out", "POST"),
    getActiveAttendance: () => apiRequest("/attendance/active"),
    getAttendanceSummary: () => apiRequest("/attendance/summary"),

    // Notices
    getNotices: () => apiRequest("/notices/"),

    // Leaves
    getMyLeaves: () => apiRequest("/leaves/my"),

    // Projects
    getMyProjects: () => apiRequest("/projects/my"),

    // Profile
    getProfile: () => apiRequest("/profile/"),
    updateProfile: (data) => apiRequest("/profile/", "PUT", data),

    uploadProfileImage: async (file) => {
        const token = localStorage.getItem("access_token");

        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(`${BASE_URL}/profile/upload-image`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`
            },
            body: formData
        });

        if (!response.ok) {
            throw new Error("Image upload failed");
        }

        return response.json();
    },

    request: apiRequest
};
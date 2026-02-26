const BASE_URL = "http://127.0.0.1:8000";
window.BASE_URL = BASE_URL;
const nativeAlert = typeof window.alert === "function" ? window.alert.bind(window) : null;

let uiPopupStyleInjected = false;

function ensureUiPopupStyles() {
    if (uiPopupStyleInjected) return;
    const style = document.createElement("style");
    style.id = "uiPopupStyles";
    style.textContent = `
        .ui-popup-wrap {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10060;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: min(92vw, 380px);
        }
        .ui-popup {
            padding: 12px 14px;
            border-radius: 10px;
            color: #0f172a;
            background: #ffffff;
            border: 1px solid #cbd5e1;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.16);
            font-size: 13px;
            line-height: 1.4;
            transform: translateY(-8px);
            opacity: 0;
            transition: opacity 0.2s ease, transform 0.2s ease;
        }
        .ui-popup.show {
            transform: translateY(0);
            opacity: 1;
        }
        .ui-popup-success {
            border-color: #86efac;
            background: #f0fdf4;
            color: #166534;
        }
        .ui-popup-error {
            border-color: #fca5a5;
            background: #fef2f2;
            color: #991b1b;
        }
        .ui-popup-warning {
            border-color: #fcd34d;
            background: #fffbeb;
            color: #92400e;
        }
        .ui-popup-info {
            border-color: #93c5fd;
            background: #eff6ff;
            color: #1e3a8a;
        }
    `;
    document.head.appendChild(style);
    uiPopupStyleInjected = true;
}

function getUiPopupWrap() {
    let wrap = document.getElementById("uiPopupWrap");
    if (wrap) return wrap;
    wrap = document.createElement("div");
    wrap.id = "uiPopupWrap";
    wrap.className = "ui-popup-wrap";
    document.body.appendChild(wrap);
    return wrap;
}

function showUIPopup(message, type = "info", timeoutMs = 3500) {
    const text = String(message || "").trim();
    if (!text) return;

    if (!document.body || !document.head) {
        if (nativeAlert) nativeAlert(text);
        return;
    }

    ensureUiPopupStyles();
    const wrap = getUiPopupWrap();
    const popup = document.createElement("div");
    const safeType = ["success", "error", "warning", "info"].includes(type) ? type : "info";

    popup.className = `ui-popup ui-popup-${safeType}`;
    popup.textContent = text;
    wrap.appendChild(popup);

    requestAnimationFrame(() => popup.classList.add("show"));

    setTimeout(() => {
        popup.classList.remove("show");
        setTimeout(() => popup.remove(), 220);
    }, timeoutMs);
}

window.showUIPopup = showUIPopup;
window.alert = function patchedAlert(message) {
    showUIPopup(message, "info");
};

let refreshPromise = null;

// Respect "Stay logged in":
// - checked: keep tokens in localStorage across restarts
// - unchecked: clear tokens when browser session ends
const rememberMe = localStorage.getItem("remember_me") === "true";
if (!rememberMe && !sessionStorage.getItem("active_session")) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
}

function getAccessToken() {
    return localStorage.getItem("access_token");
}

function getRefreshToken() {
    return localStorage.getItem("refresh_token");
}

function setAuthTokens(accessToken, refreshToken) {
    if (accessToken) localStorage.setItem("access_token", accessToken);
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
}

function saveAuthSession(authData, stayLoggedIn = false) {
    localStorage.setItem("access_token", authData.access_token);
    localStorage.setItem("refresh_token", authData.refresh_token);
    localStorage.setItem("user", JSON.stringify(authData.user || null));
    if (authData.user && authData.user.id !== undefined) localStorage.setItem("user_id", String(authData.user.id));
    if (authData.user && authData.user.role) localStorage.setItem("user_role", String(authData.user.role).toLowerCase());

    if (stayLoggedIn) {
        localStorage.setItem("remember_me", "true");
        sessionStorage.removeItem("active_session");
    } else {
        localStorage.setItem("remember_me", "false");
        sessionStorage.setItem("active_session", "1");
    }
}

function clearAuthState() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
    localStorage.removeItem("user_id");
    localStorage.removeItem("user_role");
    localStorage.removeItem("remember_me");
    sessionStorage.removeItem("active_session");
}

function redirectToLogin() {
    window.location.href = "../auth/login.html";
}

function buildHeaders(token, isJson = true) {
    const headers = {};
    if (isJson) headers["Content-Type"] = "application/json";
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
}

async function refreshAccessToken() {
    if (refreshPromise) return refreshPromise;

    const refreshToken = getRefreshToken();
    if (!refreshToken) throw new Error("Session expired");

    refreshPromise = fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: buildHeaders(null, true),
        body: JSON.stringify({ refresh_token: refreshToken })
    }).then(async (response) => {
        if (!response.ok) {
            throw new Error("Refresh token expired");
        }
        const data = await response.json();
        setAuthTokens(data.access_token, data.refresh_token);
        if (data.user) {
            localStorage.setItem("user", JSON.stringify(data.user));
            if (data.user.id !== undefined) localStorage.setItem("user_id", String(data.user.id));
            if (data.user.role) localStorage.setItem("user_role", String(data.user.role).toLowerCase());
        }
        return data.access_token;
    }).finally(() => {
        refreshPromise = null;
    });

    return refreshPromise;
}

async function apiRequest(endpoint, method = "GET", body = null, options = {}) {
    const url = `${BASE_URL}${endpoint}`;
    let token = getAccessToken();

    const makeRequest = async (bearerToken) => {
        return fetch(url, {
            method,
            headers: buildHeaders(bearerToken, !options.isFormData),
            body: body
                ? (options.isFormData ? body : JSON.stringify(body))
                : null
        });
    };

    let response = await makeRequest(token);

    if (response.status === 401 && !options.skipRefresh) {
        try {
            token = await refreshAccessToken();
            response = await makeRequest(token);
        } catch {
            clearAuthState();
            redirectToLogin();
            throw new Error("Session expired");
        }
    }

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        if (Array.isArray(err.detail)) {
            const message = err.detail
                .map((item) => item?.msg || item?.message)
                .filter(Boolean)
                .join(", ");
            throw new Error(message || "Request failed");
        }
        throw new Error(err.detail || "Request failed");
    }

    if (response.status === 204) return null;
    return response.json();
}

window.apiRequest = apiRequest;

async function safeLogout() {
    try {
        await apiRequest("/auth/logout", "POST");
    } catch (_) {
        // Ignore API failures on logout and clear local auth anyway.
    } finally {
        clearAuthState();
        redirectToLogin();
    }
}

function ensureLogoutModal() {
    if (document.getElementById("logoutConfirmModal")) return;
    const modal = document.createElement("div");
    modal.id = "logoutConfirmModal";
    modal.style.cssText = `
        position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
        display: none; align-items: center; justify-content: center; z-index: 10050;
    `;
    modal.innerHTML = `
        <div style="background:#fff;border-radius:10px;width:min(92vw,360px);padding:18px;border:1px solid #e2e8f0;">
            <div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:10px;">Logout Confirmation</div>
            <div style="font-size:13px;color:#475569;margin-bottom:16px;">Are you sure you want to logout?</div>
            <div style="display:flex;justify-content:flex-end;gap:8px;">
                <button id="logoutCancelBtn" style="padding:8px 12px;border:1px solid #cbd5e1;background:#fff;border-radius:6px;cursor:pointer;">Cancel</button>
                <button id="logoutConfirmBtn" style="padding:8px 12px;border:1px solid #073379;background:#073379;color:#fff;border-radius:6px;cursor:pointer;">Logout</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    const hide = () => { modal.style.display = "none"; };
    modal.addEventListener("click", (e) => {
        if (e.target === modal) hide();
    });
    document.getElementById("logoutCancelBtn").addEventListener("click", hide);
    document.getElementById("logoutConfirmBtn").addEventListener("click", async () => {
        hide();
        await safeLogout();
    });
}

function showLogoutModal() {
    ensureLogoutModal();
    const modal = document.getElementById("logoutConfirmModal");
    if (modal) modal.style.display = "flex";
}

window.toggleSidebar = function toggleSidebar() {
    const sidebar = document.getElementById("adminSidebar");
    if (sidebar) sidebar.classList.toggle("active");
};

window.toggleSubmenu = function toggleSubmenu(event, submenuId) {
    if (event) event.preventDefault();
    const submenu = document.getElementById(submenuId);
    if (!submenu) return;
    submenu.classList.toggle("expanded");
    const parent = submenu.closest(".nav-parent");
    if (parent) parent.classList.toggle("expanded");
};

window.handleLogout = function handleLogout(event) {
    if (event) event.preventDefault();
    showLogoutModal();
};

function applyUserInfo() {
    const raw = localStorage.getItem("user");
    if (!raw) return;
    let user = null;
    try {
        user = JSON.parse(raw);
    } catch {
        return;
    }
    if (!user) return;

    document.querySelectorAll("[data-user-name]").forEach((el) => {
        el.textContent = user.name || "User";
    });
    document.querySelectorAll("[data-user-greeting]").forEach((el) => {
        el.textContent = `Hi ${user.name || "User"}`;
    });
}

document.addEventListener("DOMContentLoaded", () => {
    applyUserInfo();
    ensureLogoutModal();
});

let userApplied = false;

function safeApplyUserInfo() {
    if (userApplied) return;
    applyUserInfo();
    userApplied = true;
}

document.addEventListener("DOMContentLoaded", safeApplyUserInfo);

window.saveAuthSession = saveAuthSession;

window.API = {
    // Auth
    login: (data) => apiRequest("/auth/login", "POST", data, { skipRefresh: true }),
    forgotPassword: (data) => apiRequest("/auth/forgot-password", "POST", data, { skipRefresh: true }),
    refresh: () => refreshAccessToken(),
    logout: () => safeLogout(),

    // Tasks
    getActiveTask: () => apiRequest("/tasks/active"),
    getMyTasks: (limit = 15, includeCompleted = false) =>
        apiRequest(`/tasks/?limit=${limit}&include_completed=${includeCompleted}`),
    getTaskHistory: (limit = 50) => apiRequest(`/tasks/history?limit=${limit}`),
    startTask: (taskId) => apiRequest(`/tasks/${taskId}/start`, "POST"),
    stopTask: (taskId) => apiRequest(`/tasks/${taskId}/stop`, "POST"),
    completeTask: (taskId) => apiRequest(`/tasks/${taskId}/complete`, "POST"),

    // Attendance
    clockIn: () => apiRequest("/attendance/clock-in", "POST"),
    clockOut: () => apiRequest("/attendance/clock-out", "POST"),
    getActiveAttendance: () => apiRequest("/attendance/active"),
    getAttendanceSummary: () => apiRequest("/attendance/summary"),
    getAttendanceHistory: (month, year) => apiRequest(`/attendance/history?month=${month}&year=${year}`),

    // Notices
    getNotices: () => apiRequest("/notices/"),

    // Leaves
    getMyLeaves: () => apiRequest("/leaves/my"),
    getLeaves: (status = null) => apiRequest(status ? `/leaves?status=${encodeURIComponent(status)}` : "/leaves"),
    approveLeave: (leaveId) => apiRequest(`/leaves/${leaveId}/approve`, "PUT"),
    rejectLeave: (leaveId) => apiRequest(`/leaves/${leaveId}/reject`, "PUT"),

    // Projects
    getMyProjects: () => apiRequest("/projects/my"),

    // Admin
    getAdminEmployees: () => apiRequest("/admin/employees"),
    getAdminTasks: () => apiRequest("/admin/tasks"),
    createAdminTask: (data) => apiRequest("/admin/tasks", "POST", data),
    getAdminProjects: () => apiRequest("/admin/projects/"),
    getAdminAttendance: (month, year) => apiRequest(`/admin/attendance?month=${month}&year=${year}`),
    getAdminAttendanceDetails: (userId, date) =>
        apiRequest(`/admin/attendance/details?user_id=${userId}&date=${encodeURIComponent(date)}`),
    markAdminAttendance: (payload) => apiRequest("/admin/attendance/mark", "POST", payload),
    deleteAdminAttendance: (attendanceId, reason = "") =>
        apiRequest(`/admin/attendance/${attendanceId}${reason ? `?reason=${encodeURIComponent(reason)}` : ""}`, "DELETE"),
    bulkMarkAdminAttendance: (payload) => apiRequest("/admin/attendance/bulk-mark", "POST", payload),
    getAdminProfile: () => apiRequest("/admin/profile"),
    getAdminList: () => apiRequest("/admin/list"),
    createAdmin: (data) => apiRequest("/admin/create", "POST", data),
    toggleAdminStatus: (adminId) => apiRequest(`/admin/toggle-status/${adminId}`, "POST"),

    // Profile
    getProfile: () => apiRequest("/profile/"),
    updateProfile: (data) => apiRequest("/profile/", "PUT", data),

    // Chat
    getChatUsers: () => apiRequest("/chat/users"),
    getChatConversations: () => apiRequest("/chat/conversations"),
    getChatMessages: (conversationId, limit = 50) =>
        apiRequest(`/chat/conversations/${conversationId}/messages?limit=${limit}`),
    createPrivateChat: (userId) => apiRequest("/chat/conversations/private", "POST", { user_id: userId }),
    createGroupChat: (data) => apiRequest("/chat/conversations/group", "POST", data),
    sendChatMessage: (conversationId, message) =>
        apiRequest("/chat/messages", "POST", { conversation_id: conversationId, message }),
    markChatRead: (conversationId) => apiRequest(`/chat/conversations/${conversationId}/read`, "PUT"),

    updateAdminProfile: (formData) =>
        apiRequest("/admin/profile", "PUT", formData, { isFormData: true }),

    uploadAdminProfileImage: (file) => {
        const formData = new FormData();
        formData.append("file", file);
        return apiRequest("/admin/profile/upload-image", "POST", formData, { isFormData: true });
    },

    uploadProfileImage: (file) => {
        const formData = new FormData();
        formData.append("file", file);
        return apiRequest("/profile/upload-image", "POST", formData, { isFormData: true });
    },

    request: apiRequest
};

function normalizePath(path) {
    const clean = String(path || "").split("?")[0].split("#")[0];
    return clean.replace(/\/+$/, "");
}

function highlightSidebarActive() {
    const container = document.getElementById("sidebar-container");
    if (!container) return;

    const currentPath = normalizePath(window.location.pathname);
    const items = container.querySelectorAll(".nav-item[href], .submenu-item[href]");

    items.forEach((item) => item.classList.remove("active"));
    container.querySelectorAll(".submenu.expanded, .nav-parent.expanded").forEach((el) => {
        el.classList.remove("expanded");
    });

    let activeItem = null;
    items.forEach((item) => {
        const href = item.getAttribute("href");
        if (!href || href === "#") return;
        try {
            const targetPath = normalizePath(new URL(href, window.location.href).pathname);
            if (targetPath && targetPath === currentPath) {
                activeItem = item;
            }
        } catch {
            // Ignore malformed URLs in sidebar links.
        }
    });

    if (!activeItem) return;
    activeItem.classList.add("active");

    if (activeItem.classList.contains("submenu-item")) {
        const submenu = activeItem.closest(".submenu");
        const parent = activeItem.closest(".nav-parent");
        if (submenu) submenu.classList.add("expanded");
        if (parent) {
            parent.classList.add("expanded");
            const trigger = parent.querySelector(".nav-item");
            if (trigger) trigger.classList.add("active");
        }
    }
}

window.highlightSidebarActive = highlightSidebarActive;

document.addEventListener("DOMContentLoaded", () => {
    highlightSidebarActive();

    const container = document.getElementById("sidebar-container");
    if (!container) return;

    const observer = new MutationObserver(() => {
        highlightSidebarActive();
    });
    observer.observe(container, { childList: true, subtree: true });
});

window.addEventListener("popstate", highlightSidebarActive);

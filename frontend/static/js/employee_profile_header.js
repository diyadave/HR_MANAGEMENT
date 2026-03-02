(function () {
  function toInitials(name) {
    return String(name || "Employee")
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => (part[0] ? part[0].toUpperCase() : ""))
      .join("") || "EM";
  }

  function imageUrl(path) {
    if (!path) return "";
    if (path.startsWith("http://") || path.startsWith("https://")) return path;
    var base = (window.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
    var normalized = String(path).replace(/\\/g, "/").replace(/^\/+/, "");
    if (normalized.indexOf("profile_images/") === 0) normalized = "uploads/" + normalized;
    return base + "/" + normalized;
  }

  function ensureStyles() {
    if (document.getElementById("globalEmployeeProfileStyles")) return;
    var style = document.createElement("style");
    style.id = "globalEmployeeProfileStyles";
    style.textContent = [
      ".global-employee-profile{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:inherit;padding:6px 8px;border-radius:10px;transition:background-color .15s;}",
      ".global-employee-profile:hover{background:#f1f5f9;}",
      ".global-employee-avatar{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#073379,#1e40af);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;overflow:hidden;}",
      ".global-employee-avatar img{width:100%;height:100%;object-fit:cover;display:none;}",
      ".global-employee-meta{display:flex;flex-direction:column;line-height:1.1;}",
      ".global-employee-name{font-size:14px;font-weight:600;color:#0f172a;}",
      ".global-employee-role{font-size:12px;color:#64748b;}",
      ".global-employee-chevron{font-size:12px;color:#334155;line-height:1;}",
      ".global-employee-profile.floating{position:fixed;top:16px;right:16px;background:#fff;border:1px solid #e2e8f0;box-shadow:0 4px 16px rgba(15,23,42,.08);z-index:1200;}",
      ".employee-corner-actions{position:fixed;top:20px;right:24px;z-index:950;display:flex;align-items:center;gap:12px;}",
      "@media (max-width:1200px){.employee-corner-actions{position:static;top:auto;right:auto;z-index:auto;}}",
      "@media (max-width:768px){.global-employee-meta,.global-employee-chevron{display:none;}.global-employee-profile{padding:4px;border-radius:999px;}}"
    ].join("");
    document.head.appendChild(style);
  }

  function buildChip() {
    var a = document.createElement("a");
    a.className = "global-employee-profile";
    a.href = "profile.html";
    a.title = "Open profile";
    a.innerHTML = [
      '<span class="global-employee-avatar">',
      '  <img id="globalEmployeeProfileImg" alt="Employee profile photo">',
      '  <span id="globalEmployeeProfileInitials">EM</span>',
      "</span>",
      '<span class="global-employee-meta">',
      '  <span id="globalEmployeeProfileName" class="global-employee-name">Employee</span>',
      '  <span id="globalEmployeeProfileRole" class="global-employee-role">employee</span>',
      "</span>",
      '<span class="global-employee-chevron">⌄</span>'
    ].join("");
    return a;
  }

  async function getProfileData() {
    var fallback = { name: "Employee", role: "employee", profile_image: "" };
    try {
      if (window.API && typeof window.API.getProfile === "function") {
        var profile = await window.API.getProfile();
        return {
          name: profile && profile.name ? profile.name : fallback.name,
          role: (profile && (profile.designation || profile.role)) ? (profile.designation || profile.role) : fallback.role,
          profile_image: profile && profile.profile_image ? profile.profile_image : ""
        };
      }
    } catch (err) {
      console.warn("Employee header profile via API failed:", err);
    }

    try {
      var token = localStorage.getItem("access_token");
      if (token) {
        var base = (window.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
        var resp = await fetch(base + "/profile/", {
          method: "GET",
          headers: { Authorization: "Bearer " + token }
        });
        if (resp.ok) {
          var profileData = await resp.json();
          return {
            name: profileData && profileData.name ? profileData.name : fallback.name,
            role: (profileData && (profileData.designation || profileData.role)) ? (profileData.designation || profileData.role) : fallback.role,
            profile_image: profileData && profileData.profile_image ? profileData.profile_image : ""
          };
        }
      }
    } catch (errFetch) {
      console.warn("Employee header profile direct fetch failed:", errFetch);
    }

    try {
      var raw = localStorage.getItem("user");
      if (raw) {
        var user = JSON.parse(raw);
        return {
          name: user && user.name ? user.name : fallback.name,
          role: user && (user.designation || user.role) ? (user.designation || user.role) : fallback.role,
          profile_image: user && user.profile_image ? user.profile_image : ""
        };
      }
    } catch (err2) {
      console.warn("Employee header profile local fallback failed:", err2);
    }

    return fallback;
  }

  function placeChip(chip) {
    var existing = document.querySelector("#employeeProfileBtn, #employeeProfileLink, #employeeTopProfileChip");
    if (existing && existing.parentElement) {
      existing.replaceWith(chip);
      return;
    }

    var host = document.querySelector(".header-actions, .page-header .header-right, .top-header .header-actions, .topbar-right");
    if (!host) {
      var header = document.querySelector(".page-header, .main-content .header, .top-header, .topbar");
      if (header) {
        host = document.createElement("div");
        host.className = "header-actions";
        header.appendChild(host);
      }
    }
    if (host) {
      host.classList.add("employee-corner-actions");
      host.appendChild(chip);
      return;
    }

    chip.classList.add("floating");
    document.body.appendChild(chip);
  }

  async function init() {
    if (!/\/employee\//.test(window.location.pathname)) return;
    ensureStyles();

    var chip = buildChip();
    placeChip(chip);

    var nameEl = chip.querySelector("#globalEmployeeProfileName");
    var roleEl = chip.querySelector("#globalEmployeeProfileRole");
    var imgEl = chip.querySelector("#globalEmployeeProfileImg");
    var initialsEl = chip.querySelector("#globalEmployeeProfileInitials");

    var data = await getProfileData();
    var initials = toInitials(data.name);
    nameEl.textContent = data.name || "Employee";
    roleEl.textContent = data.role || "employee";
    initialsEl.textContent = initials;

    var src = imageUrl(data.profile_image || "");
    if (src) {
      imgEl.src = src;
      imgEl.style.display = "block";
      initialsEl.style.display = "none";
      imgEl.onerror = function () {
        imgEl.style.display = "none";
        initialsEl.style.display = "inline";
      };
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

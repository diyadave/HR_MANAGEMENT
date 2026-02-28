(function () {
  function toInitials(name) {
    return String(name || "Admin")
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0] ? part[0].toUpperCase() : "")
      .join("") || "AD";
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
    if (document.getElementById("globalAdminProfileStyles")) return;
    var style = document.createElement("style");
    style.id = "globalAdminProfileStyles";
    style.textContent = [
      ".global-admin-profile{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:inherit;padding:6px 8px;border-radius:10px;transition:background-color .15s;}",
      ".global-admin-profile:hover{background:#f1f5f9;}",
      ".global-admin-avatar{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#073379,#1e40af);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;overflow:hidden;}",
      ".global-admin-avatar img{width:100%;height:100%;object-fit:cover;display:none;}",
      ".global-admin-meta{display:flex;flex-direction:column;line-height:1.1;}",
      ".global-admin-name{font-size:14px;font-weight:600;color:#0f172a;}",
      ".global-admin-role{font-size:12px;color:#64748b;}",
      ".global-admin-chevron{font-size:12px;color:#334155;line-height:1;}",
      ".global-admin-profile.floating{position:fixed;top:16px;right:16px;background:#fff;border:1px solid #e2e8f0;box-shadow:0 4px 16px rgba(15,23,42,.08);z-index:1200;}",
      "@media (max-width:768px){.global-admin-meta,.global-admin-chevron{display:none;}.global-admin-profile{padding:4px;border-radius:999px;}}"
    ].join("");
    document.head.appendChild(style);
  }

  function buildChip() {
    var a = document.createElement("a");
    a.className = "global-admin-profile";
    a.href = "admin_profile.html";
    a.title = "Open admin profile";
    a.innerHTML = [
      '<span class="global-admin-avatar">',
      '  <img id="globalAdminProfileImg" alt="Admin profile photo">',
      '  <span id="globalAdminProfileInitials">AD</span>',
      "</span>",
      '<span class="global-admin-meta">',
      '  <span id="globalAdminProfileName" class="global-admin-name">Admin</span>',
      '  <span id="globalAdminProfileRole" class="global-admin-role">admin</span>',
      "</span>",
      '<span class="global-admin-chevron">⌄</span>'
    ].join("");
    return a;
  }

  async function getProfileData() {
    var fallback = { name: "Admin", role: "admin", profile_image: "" };
    try {
      if (window.API && typeof window.API.getAdminProfile === "function") {
        var profile = await window.API.getAdminProfile();
        return {
          name: profile && profile.name ? profile.name : fallback.name,
          role: (profile && (profile.designation || profile.role)) ? (profile.designation || profile.role) : fallback.role,
          profile_image: profile && profile.profile_image ? profile.profile_image : ""
        };
      }
    } catch (err) {
      console.warn("Admin header profile via API failed:", err);
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
      console.warn("Admin header profile local fallback failed:", err2);
    }

    return fallback;
  }

  function placeChip(chip) {
    var existing = document.querySelector("#adminProfileBtn, #adminProfileLink");
    if (existing && existing.parentElement) {
      existing.replaceWith(chip);
      return;
    }

    var host = document.querySelector(".header-actions, .page-header .header-right, .top-header .header-actions, .topbar-right");
    if (host) {
      host.appendChild(chip);
      return;
    }

    chip.classList.add("floating");
    document.body.appendChild(chip);
  }

  async function init() {
    if (!/\/admin\//.test(window.location.pathname)) return;
    ensureStyles();

    var chip = buildChip();
    placeChip(chip);

    var nameEl = chip.querySelector("#globalAdminProfileName");
    var roleEl = chip.querySelector("#globalAdminProfileRole");
    var imgEl = chip.querySelector("#globalAdminProfileImg");
    var initialsEl = chip.querySelector("#globalAdminProfileInitials");

    var data = await getProfileData();
    var initials = toInitials(data.name);
    nameEl.textContent = data.name || "Admin";
    roleEl.textContent = data.role || "admin";
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

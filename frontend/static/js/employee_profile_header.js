(function () {
  const path = (window.location.pathname || '').toLowerCase();
  if (path.endsWith('/profile.html')) return;
  if (document.getElementById('employeeTopProfileChip')) return;

  const style = document.createElement('style');
  style.id = 'employeeTopProfileChipStyle';
  style.textContent = `
    .employee-top-header-normalized {
      display: flex !important;
      justify-content: space-between !important;
      align-items: center !important;
      gap: 16px !important;
      flex-wrap: wrap;
    }

    .employee-top-profile-actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-left: auto;
      flex-shrink: 0;
    }

    .employee-top-profile-chip {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      min-width: 126px;
      max-width: 250px;
      padding: 8px 12px;
      border-radius: 11px;
      background: #ffffff;
      border: 1px solid #d5dee9;
      box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
      text-decoration: none;
      color: #0f172a;
      transition: box-shadow 0.18s ease, transform 0.18s ease;
    }

    .employee-top-profile-chip:hover {
      transform: translateY(-1px);
      box-shadow: 0 10px 22px rgba(15, 23, 42, 0.12);
    }

    .employee-top-profile-avatar,
    .employee-top-profile-initials {
      width: 36px;
      height: 36px;
      border-radius: 999px;
      flex: 0 0 36px;
      border: 1px solid #dbe3ee;
      object-fit: cover;
      overflow: hidden;
    }

    .employee-top-profile-initials {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-weight: 700;
      color: #ffffff;
      background: #315ca8;
    }

    .employee-top-profile-meta {
      min-width: 0;
      display: flex;
      flex-direction: column;
      line-height: 1.2;
    }

    .employee-top-profile-name {
      font-size: 14px;
      font-weight: 700;
      color: #0f172a;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .employee-top-profile-role {
      font-size: 13px;
      color: #64748b;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    @media (max-width: 768px) {
      .employee-top-header-normalized {
        align-items: flex-start !important;
      }
      .employee-top-profile-actions {
        width: 100%;
        margin-left: 0;
      }
      .employee-top-profile-chip {
        display: none;
      }
    }
  `;
  document.head.appendChild(style);

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function parseUser() {
    try {
      const raw = localStorage.getItem('user');
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  }

  function getImageUrl(pathOrUrl) {
    const value = String(pathOrUrl || '').trim();
    if (!value) return '';
    if (/^https?:\/\//i.test(value)) return value;
    return `http://127.0.0.1:8000/${value.replace(/^\/+/, '')}`;
  }

  function createChip(name, role, profileImage) {
    const chip = document.createElement('a');
    chip.id = 'employeeTopProfileChip';
    chip.className = 'employee-top-profile-chip';
    chip.href = '../employee/profile.html';
    chip.setAttribute('aria-label', 'Open profile');

    const safeName = escapeHtml(name || 'Employee');
    const safeRole = escapeHtml(role || 'employee');
    const imageUrl = getImageUrl(profileImage);

    let avatarHtml = '';
    if (imageUrl) {
      avatarHtml = `<img class="employee-top-profile-avatar" src="${imageUrl}" alt="Profile">`;
    } else {
      const initials = String(name || 'Employee')
        .split(' ')
        .map((part) => part[0])
        .filter(Boolean)
        .slice(0, 2)
        .join('')
        .toUpperCase() || 'E';
      avatarHtml = `<span class="employee-top-profile-initials">${escapeHtml(initials)}</span>`;
    }

    chip.innerHTML = `${avatarHtml}<span class="employee-top-profile-meta"><span class="employee-top-profile-name">${safeName}</span><span class="employee-top-profile-role">${safeRole}</span></span>`;
    return chip;
  }

  async function resolveProfileData() {
    const user = parseUser();
    let name = user?.name || 'Employee';
    let role = user?.role || 'employee';
    let profileImage = user?.profile_image || '';

    if (window.API && typeof window.API.getProfile === 'function') {
      try {
        const profile = await window.API.getProfile();
        if (profile && typeof profile === 'object') {
          name = profile.name || name;
          role = profile.role || role;
          profileImage = profile.profile_image || profileImage;
        }
      } catch (_) {
        // Keep local fallback data
      }
    }

    return { name, role, profileImage };
  }

  async function init() {
    const profile = await resolveProfileData();
    const chip = createChip(profile.name, profile.role, profile.profileImage);
    const header = document.querySelector(
      '.main-content .page-header, .main-container .page-header, .main-wrapper .page-header, .main-content .header, .main-wrapper .header'
    );

    if (header) {
      header.classList.add('employee-top-header-normalized');
      let actions = header.querySelector('.header-actions');
      if (!actions) {
        actions = document.createElement('div');
        actions.className = 'header-actions employee-top-profile-actions';
        header.appendChild(actions);
      } else {
        actions.classList.add('employee-top-profile-actions');
      }
      actions.appendChild(chip);
      return;
    }

    document.body.appendChild(chip);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

(function () {
  const path = (window.location.pathname || '').toLowerCase();
  if (path.endsWith('/profile.html')) return;
  if (document.getElementById('employeeTopProfileChip')) return;

  const style = document.createElement('style');
  style.id = 'employeeTopProfileChipStyle';
  style.textContent = `
    .employee-top-profile-chip {
      position: fixed;
      top: 18px;
      right: 24px;
      z-index: 1200;
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

    .employee-top-profile-chevron {
      font-size: 12px;
      color: #64748b;
      line-height: 1;
      margin-left: 2px;
      flex: 0 0 auto;
    }

    @media (max-width: 992px) {
      .employee-top-profile-chip {
        display: none;
      }
    }
  `;
  document.head.appendChild(style);

  function parseUser() {
    try {
      const raw = localStorage.getItem('user');
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  const user = parseUser();
  const displayName = String(user?.name || 'Employee');
  const displayRole = String(user?.role || 'employee');
  const safeName = escapeHtml(displayName);
  const safeRole = escapeHtml(displayRole);

  const chip = document.createElement('a');
  chip.id = 'employeeTopProfileChip';
  chip.className = 'employee-top-profile-chip';
  chip.href = '../employee/profile.html';
  chip.setAttribute('aria-label', 'Open profile');

  const profileImage = typeof user?.profile_image === 'string' ? user.profile_image.trim() : '';
  let avatarHtml = '';
  if (profileImage) {
    const imageUrl = profileImage.startsWith('http') ? profileImage : `http://127.0.0.1:8000/${profileImage.replace(/^\/+/, '')}`;
    avatarHtml = `<img class="employee-top-profile-avatar" src="${imageUrl}" alt="Profile">`;
  } else {
    const initials = displayName
      .split(' ')
      .map((p) => p[0])
      .filter(Boolean)
      .slice(0, 2)
      .join('')
      .toUpperCase() || 'E';
    avatarHtml = `<span class="employee-top-profile-initials">${escapeHtml(initials)}</span>`;
  }

  chip.innerHTML = `${avatarHtml}<span class="employee-top-profile-meta"><span class="employee-top-profile-name">${safeName}</span><span class="employee-top-profile-role">${safeRole}</span></span><span class="employee-top-profile-chevron">v</span>`;
  document.body.appendChild(chip);

  function updatePosition() {
    const tracker = document.getElementById('tracker-container');
    if (!tracker) {
      chip.style.right = '24px';
      return;
    }

    const trackerStyle = window.getComputedStyle(tracker);
    const hidden = trackerStyle.display === 'none' || trackerStyle.visibility === 'hidden';
    if (hidden) {
      chip.style.right = '24px';
      return;
    }

    const width = Math.round(tracker.getBoundingClientRect().width || parseFloat(trackerStyle.width) || 0);
    chip.style.right = width > 0 ? `${width + 16}px` : '24px';
  }

  updatePosition();
  window.addEventListener('resize', updatePosition);
  setTimeout(updatePosition, 250);
  setTimeout(updatePosition, 1000);
})();



function animateCards() {
    const cards = document.querySelectorAll('.summary-card, .dashboard-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 50);
    });
}

/**
 * Initialize tooltips for better UX
 */
function initializeTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', showTooltip);
        element.addEventListener('mouseleave', hideTooltip);
    });
}

function showTooltip(event) {
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = event.target.getAttribute('data-tooltip');
    document.body.appendChild(tooltip);
    
    const rect = event.target.getBoundingClientRect();
    tooltip.style.top = `${rect.top - tooltip.offsetHeight - 8}px`;
    tooltip.style.left = `${rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2)}px`;
}

function hideTooltip() {
    const tooltip = document.querySelector('.tooltip');
    if (tooltip) {
        tooltip.remove();
    }
}

    // ============================================
    // Badge Updates
    // ============================================
    
    /**
     * Update badge count dynamically
     */
    function updateBadge(pageName, count) {
        const link = document.querySelector(`[data-page="${pageName}"]`);
        if (!link) return;
        
        let badge = link.querySelector('.nav-badge');
        
        if (count > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'nav-badge';
                link.appendChild(badge);
            }
            badge.textContent = count;
            
            // Animate badge update
            badge.style.transform = 'scale(1.2)';
            setTimeout(() => {
                badge.style.transform = 'scale(1)';
            }, 200);
        } else if (badge) {
            badge.remove();
        }
    }
    
   
   
    
    // ============================================
    // System Status Updates
    // ============================================
    
    /**
     * Update system status bar
     */
    
    
    // ============================================
    // Public API
    // ============================================
    
    /**
     * Expose public API for external use
        */
    
    // ============================================
    // Auto-Initialize
    // ============================================
    
  


// ============================================
// Header Functionality
// ============================================
function initializeHeader() {
    // Search functionality
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        searchInput.addEventListener('input', handleSearch);
        searchInput.addEventListener('focus', function() {
            this.parentElement.style.transform = 'scale(1.02)';
        });
        searchInput.addEventListener('blur', function() {
            this.parentElement.style.transform = 'scale(1)';
        });
    }
    
    // Notification bell
    const notificationBell = document.querySelector('.notification-bell');
    if (notificationBell) {
        notificationBell.addEventListener('click', showNotifications);
    }
    
    // Profile dropdown
    const profileDropdown = document.querySelector('.admin-profile');
    if (profileDropdown) {
        profileDropdown.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }
    
    // Logout functionality
    const logoutBtn = document.querySelector('.dropdown-item.logout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', handleLogout);
    }
}

/**
 * Handle search input
 */
function handleSearch(event) {
    const query = event.target.value.toLowerCase().trim();
    
    if (query.length === 0) {
        clearSearchResults();
        return;
    }
    
    if (query.length < 2) return;
    
    // Debounce search
    clearTimeout(window.searchTimeout);
    window.searchTimeout = setTimeout(() => {
        performSearch(query);
    }, 300);
}

/**
 * Perform search across dashboard data
 */
function performSearch(query) {
    console.log('Searching for:', query);
    
    // In a real application, this would make an API call
    // For now, we'll just highlight matching rows in the table
    const tableRows = document.querySelectorAll('.data-table tbody tr');
    let matchCount = 0;
    
    tableRows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(query)) {
            row.style.display = '';
            row.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
            matchCount++;
        } else {
            row.style.display = 'none';
        }
    });
    
    console.log(`Found ${matchCount} matches`);
}

/**
 * Clear search results
 */
function clearSearchResults() {
    const tableRows = document.querySelectorAll('.data-table tbody tr');
    tableRows.forEach(row => {
        row.style.display = '';
        row.style.backgroundColor = '';
    });
}

/**
 * Show notifications dropdown
 */
function showNotifications() {
    console.log('Showing notifications...');
    
    // Create notification panel
    const existingPanel = document.querySelector('.notification-panel');
    if (existingPanel) {
        existingPanel.remove();
        return;
    }
    
    const panel = document.createElement('div');
    panel.className = 'notification-panel';
    panel.innerHTML = `
        <div class="notification-header">
            <h3>Notifications</h3>
            <button class="mark-all-read">Mark all as read</button>
        </div>
        <div class="notification-list">
            <div class="notification-item unread">
                <div class="notification-icon blue">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M8 2V8L11 11" stroke="currentColor" stroke-width="1.5"/>
                        <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                </div>
                <div class="notification-content">
                    <p><strong>New leave request</strong> from John Davis</p>
                    <span>2 hours ago</span>
                </div>
            </div>
            <div class="notification-item unread">
                <div class="notification-icon orange">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M8 2V8L11 11" stroke="currentColor" stroke-width="1.5"/>
                        <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                </div>
                <div class="notification-content">
                    <p><strong>Overtime alert</strong> for Sarah Parker</p>
                    <span>4 hours ago</span>
                </div>
            </div>
            <div class="notification-item">
                <div class="notification-icon green">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M13 5L6 12L3 9" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                </div>
                <div class="notification-content">
                    <p><strong>Task completed:</strong> Q3 Report</p>
                    <span>1 day ago</span>
                </div>
            </div>
        </div>
        <div class="notification-footer">
            <a href="#">View all notifications</a>
        </div>
    `;
    
    const notificationBell = document.querySelector('.notification-bell');
    notificationBell.parentElement.appendChild(panel);
    
    // Close on outside click
    setTimeout(() => {
        document.addEventListener('click', function closePanel(e) {
            if (!panel.contains(e.target) && !notificationBell.contains(e.target)) {
                panel.remove();
                document.removeEventListener('click', closePanel);
            }
        });
    }, 100);
}

/**
 * Handle logout
 */
function handleLogout(event) {
    event.preventDefault();
    
    if (confirm('Are you sure you want to logout?')) {
        console.log('Logging out...');
        // In production, this would redirect to logout endpoint
        window.location.href = '/login';
    }
}

// ============================================
// Real-time Updates
// ============================================
function setupRealtimeUpdates() {
    // Simulate real-time updates every 30 seconds
    setInterval(updateDashboardStats, 30000);
    
    // Update time-based elements
    setInterval(updateTimeElements, 60000);
}

/**
 * Update dashboard statistics
 */
function updateDashboardStats() {
    console.log('Updating dashboard statistics...');
    
    // In production, this would fetch from API
    // For now, we'll just add a subtle pulse animation
    const summaryCards = document.querySelectorAll('.summary-card');
    summaryCards.forEach(card => {
        card.style.animation = 'pulse 0.5s ease';
        setTimeout(() => {
            card.style.animation = '';
        }, 500);
    });
}

/**
 * Update time-based elements (e.g., "2 hours ago" → "3 hours ago")
 */
function updateTimeElements() {
    const timeElements = document.querySelectorAll('[data-time]');
    timeElements.forEach(element => {
        const timestamp = element.getAttribute('data-time');
        element.textContent = formatRelativeTime(timestamp);
    });
}

/**
 * Format timestamp as relative time
 */
function formatRelativeTime(timestamp) {
    const now = new Date();
    const time = new Date(timestamp);
    const diff = Math.floor((now - time) / 1000);
    
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
    return `${Math.floor(diff / 86400)} days ago`;
}

// ============================================
// Filters and Sorting
// ============================================
function initializeFilters() {
    // Export button functionality
    const exportButtons = document.querySelectorAll('.btn-secondary');
    exportButtons.forEach(button => {
        if (button.textContent.includes('Export')) {
            button.addEventListener('click', handleExport);
        }
    });
    
    // View all buttons
    const viewAllButtons = document.querySelectorAll('.footer-link');
    viewAllButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const targetSection = this.textContent.trim();
            console.log(`Navigating to: ${targetSection}`);
        });
    });
}

/**
 * Handle data export
 */
function handleExport(event) {
    event.preventDefault();
    console.log('Exporting data...');
    
    // Show export options
    const options = ['CSV', 'Excel', 'PDF'];
    const choice = prompt(`Export as:\n${options.join('\n')}\n\nEnter format:`);
    
    if (choice && options.map(o => o.toLowerCase()).includes(choice.toLowerCase())) {
        console.log(`Exporting as ${choice}...`);
        // In production, this would trigger actual export
        alert(`Data will be exported as ${choice.toUpperCase()}`);
    }
}

// ============================================
// Table Interactions
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(() => {
        initializeTableInteractions();
    }, 100);
});

function initializeTableInteractions() {
    const tableRows = document.querySelectorAll('.data-table tbody tr');
    
    tableRows.forEach(row => {
        row.style.cursor = 'pointer';
        
        row.addEventListener('click', function() {
            const employeeName = this.querySelector('.employee-name')?.textContent;
            if (employeeName) {
                console.log(`Viewing details for: ${employeeName}`);
                // In production, this would open employee details modal
            }
        });
        
        // Add hover effect
        row.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.005)';
            this.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.05)';
        });
        
        row.addEventListener('mouseleave', function() {
            this.style.transform = '';
            this.style.boxShadow = '';
        });
    });
}

// ============================================
// Alert Management
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(() => {
        initializeAlertManagement();
    }, 100);
});

function initializeAlertManagement() {
    const alertItems = document.querySelectorAll('.alert-item');
    
    alertItems.forEach(item => {
        item.addEventListener('click', function() {
            const title = this.querySelector('.alert-title')?.textContent;
            console.log(`Viewing alert: ${title}`);
            // In production, this would open alert details
        });
    });
    
    // Review all alerts button
    const reviewButton = document.querySelector('.alert-card .btn-primary');
    if (reviewButton) {
        reviewButton.addEventListener('click', function() {
            console.log('Opening alerts management page...');
            // In production, navigate to alerts page
        });
    }
}

// ============================================
// Utility Functions
// ============================================

/**
 * Format number with commas
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Calculate percentage
 */
function calculatePercentage(value, total) {
    return ((value / total) * 100).toFixed(1);
}

/**
 * Debounce function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ============================================
// Keyboard Shortcuts
// ============================================


// ============================================
// Console Branding
// ============================================
console.log('%cWorkHub Admin Dashboard', 'font-size: 24px; font-weight: bold; color: #3B82F6;');
console.log('%cPowered by WorkHub HR & Workforce Management', 'font-size: 12px; color: #64748B;');
console.log('%cVersion 1.0.0', 'font-size: 10px; color: #94A3B8;');
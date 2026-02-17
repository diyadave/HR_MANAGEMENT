/**
 * Employees Management Page - JavaScript
 * Handles search, filtering, sorting, pagination, and employee actions
 */

(function() {
    'use strict';
    
    // ============================================
    // State Management
    // ============================================
    
    const state = {
        employees: [],
        filteredEmployees: [],
        currentPage: 1,
        itemsPerPage: 10,
        sortColumn: null,
        sortDirection: 'asc',
        filters: {
            search: '',
            department: '',
            designation: '',
            status: ''
        }
    };
    
    // ============================================
    // Initialization
    // ============================================
    
    function init() {
        loadEmployees();
        setupEventListeners();
        setupSearch();
        setupFilters();
        setupSelectAll();
        setupTableActions();
        console.log('Employees page initialized');
    }
    
    // ============================================
    // Data Loading
    // ============================================
    async function loadEmployees() {
        try {
            const employees = await apiRequest("/admin/employees");

            state.employees = employees.map(emp => ({
                id: emp.employee_id,
                name: emp.name,
                email: emp.email,
                role: emp.role,
                department: emp.department || "-",
                designation: emp.designation || "-",
                status: emp.is_active ? "Active" : "Inactive",
                raw: emp
            }));

            state.filteredEmployees = [...state.employees];
            // Build DOM elements for each employee to use in renderTable
            state.filteredEmployees.forEach(emp => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><input type="checkbox" class="checkbox"></td>
                    <td class="emp-id">${emp.id}</td>
                    <td class="employee-name">${emp.name}</td>
                    <td>${emp.email}</td>
                    <td>${emp.role}</td>
                    <td>${emp.department}</td>
                    <td>${emp.designation}</td>
                    <td><span class="status-badge ${emp.status === 'Active' ? 'status-active' : 'status-inactive'}">${emp.status}</span></td>
                    <td class="actions-cell">
                        <button class="action-btn">View</button>
                        <button class="action-btn">Edit</button>
                        <button class="action-btn btn-danger">Disable</button>
                    </td>
                `;
                emp.element = tr;
            });

            renderTable();
            updatePagination();
            updateStats();

        } catch (err) {
            console.error("Failed to load employees:", err.message);
        }
    }
    
    document.addEventListener("DOMContentLoaded", () => {
    loadEmployeeNotices();
});

    async function loadEmployeeNotices() {
        try {
            const notices = await apiRequest("/notices");
            const list = document.getElementById("noticeList");
            list.innerHTML = "";

            notices.forEach(n => {
                const item = document.createElement("div");
                item.className = "notice-card";
                item.innerHTML = `
                    <h4>${n.title}</h4>
                    <p>${n.description}</p>
                    <small>${new Date(n.created_at).toLocaleDateString()}</small>
                `;
                list.appendChild(item);
            });
        } catch (err) {
            console.error(err.message);
        }
    }

    // ============================================
    // Search Functionality
    // ============================================
    
    function setupSearch() {
        const searchInput = document.querySelector('.search-input');
        if (!searchInput) return;
        
        let searchTimeout;
        searchInput.addEventListener('input', function(e) {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                state.filters.search = e.target.value.toLowerCase().trim();
                applyFilters();
            }, 300);
        });
        
        // Keyboard shortcut: Ctrl/Cmd + K
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                searchInput.focus();
            }
        });
    }
    
    // ============================================
    // Filter Functionality
    // ============================================
    
    function setupFilters() {
        const departmentFilter = document.getElementById('departmentFilter');
        const designationFilter = document.getElementById('designationFilter');
        const statusFilter = document.getElementById('statusFilter');
        
        if (departmentFilter) {
            departmentFilter.addEventListener('change', function(e) {
                state.filters.department = e.target.value.toLowerCase();
                applyFilters();
            });
        }
        
        if (designationFilter) {
            designationFilter.addEventListener('change', function(e) {
                state.filters.designation = e.target.value.toLowerCase();
                applyFilters();
            });
        }
        
        if (statusFilter) {
            statusFilter.addEventListener('change', function(e) {
                state.filters.status = e.target.value.toLowerCase();
                applyFilters();
            });
        }
    }
    
    function applyFilters() {
        state.filteredEmployees = state.employees.filter(emp => {
            const searchMatch = !state.filters.search || 
                emp.name.toLowerCase().includes(state.filters.search) ||
                emp.email.toLowerCase().includes(state.filters.search) ||
                emp.id.toLowerCase().includes(state.filters.search);
            
            const departmentMatch = !state.filters.department || 
                emp.department.toLowerCase() === state.filters.department;
            
            const designationMatch = !state.filters.designation || 
                emp.designation.toLowerCase().includes(state.filters.designation);
            
            const statusMatch = !state.filters.status || 
                emp.status.toLowerCase() === state.filters.status;
            
            return searchMatch && departmentMatch && designationMatch && statusMatch;
        });
        
        state.currentPage = 1;
        renderTable();
        updatePagination();
    }
    
    // ============================================
    // Sorting Functionality
    // ============================================
    
    function setupTableSorting() {
        const sortableHeaders = document.querySelectorAll('.sortable');
        
        sortableHeaders.forEach(header => {
            header.addEventListener('click', function() {
                const columnIndex = Array.from(header.parentElement.children).indexOf(header);
                sortTable(columnIndex);
            });
        });
    }
    
    function sortTable(columnIndex) {
        const direction = state.sortColumn === columnIndex && state.sortDirection === 'asc' 
            ? 'desc' : 'asc';
        
        state.sortColumn = columnIndex;
        state.sortDirection = direction;
        
        state.filteredEmployees.sort((a, b) => {
            let aVal, bVal;
            
            switch(columnIndex) {
                case 1: // Employee ID
                    aVal = a.id;
                    bVal = b.id;
                    break;
                case 2: // Name
                    aVal = a.name;
                    bVal = b.name;
                    break;
                case 3: // Email
                    aVal = a.email;
                    bVal = b.email;
                    break;
                case 5: // Department
                    aVal = a.department;
                    bVal = b.department;
                    break;
                case 6: // Designation
                    aVal = a.designation;
                    bVal = b.designation;
                    break;
                default:
                    return 0;
            }
            
            if (direction === 'asc') {
                return aVal > bVal ? 1 : -1;
            } else {
                return aVal < bVal ? 1 : -1;
            }
        });
        
        renderTable();
    }
    
    // ============================================
    // Table Rendering
    // ============================================
    
   function renderEmployees(employees) {
  const tbody = document.getElementById("employeesBody");
  tbody.innerHTML = "";

  employees.forEach(emp => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <div class="employee-cell">
          <div class="employee-avatar">${emp.name.slice(0,2).toUpperCase()}</div>
          <div class="employee-info">
            <div class="employee-name">${emp.name}</div>
            <div class="employee-id">${emp.employee_id || "EMP-" + emp.id}</div>
          </div>
        </div>
      </td>
      <td>${emp.department || "-"}</td>
      <td>${emp.designation || "-"}</td>
      <td>
        <span class="status-badge ${emp.is_active ? "status-active" : "status-inactive"}">
          ${emp.is_active ? "Active" : "Inactive"}
        </span>
      </td>
      <td>
        <button class="toggle-btn">Task & Project Permissions</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

    function updateShowingText() {
        const showingText = document.querySelector('.showing-text');
        const paginationInfo = document.querySelector('.pagination-info');
        
        if (state.filteredEmployees.length === 0) {
            if (showingText) showingText.textContent = 'No employees';
            if (paginationInfo) paginationInfo.innerHTML = 'No employees to display';
            return;
        }
        
        const start = (state.currentPage - 1) * state.itemsPerPage + 1;
        const end = Math.min(start + state.itemsPerPage - 1, state.filteredEmployees.length);
        
        if (showingText) {
            showingText.textContent = `Showing ${start}-${end} of ${state.filteredEmployees.length}`;
        }
        
        if (paginationInfo) {
            paginationInfo.innerHTML = `Showing <strong>${start}-${end}</strong> of <strong>${state.filteredEmployees.length}</strong> employees`;
        }
    }
    
    // ============================================
    // Pagination
    // ============================================
    
    function updatePagination() {
        const totalPages = Math.ceil(state.filteredEmployees.length / state.itemsPerPage);
        const pagination = document.querySelector('.pagination');
        
        if (!pagination) return;
        
        pagination.innerHTML = '';
        
        // Previous button
        const prevBtn = createPaginationButton('prev', state.currentPage === 1);
        prevBtn.addEventListener('click', () => changePage(state.currentPage - 1));
        pagination.appendChild(prevBtn);
        
        // Page numbers
        const pagesToShow = getPageNumbers(state.currentPage, totalPages);
        pagesToShow.forEach(page => {
            if (page === '...') {
                const dots = document.createElement('span');
                dots.className = 'pagination-dots';
                dots.textContent = '...';
                pagination.appendChild(dots);
            } else {
                const pageBtn = createPaginationButton(page, false, page === state.currentPage);
                pageBtn.addEventListener('click', () => changePage(page));
                pagination.appendChild(pageBtn);
            }
        });
        
        // Next button
        const nextBtn = createPaginationButton('next', state.currentPage === totalPages);
        nextBtn.addEventListener('click', () => changePage(state.currentPage + 1));
        pagination.appendChild(nextBtn);
    }
    
    function createPaginationButton(content, disabled = false, active = false) {
        const button = document.createElement('button');
        button.className = 'pagination-btn';
        
        if (disabled) button.disabled = true;
        if (active) button.classList.add('active');
        
        if (content === 'prev') {
            button.innerHTML = `
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M7.5 9L4.5 6L7.5 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
        } else if (content === 'next') {
            button.innerHTML = `
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M4.5 3L7.5 6L4.5 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
        } else {
            button.textContent = content;
        }
        
        return button;
    }
    
    function getPageNumbers(current, total) {
        if (total <= 7) {
            return Array.from({ length: total }, (_, i) => i + 1);
        }
        
        if (current <= 3) {
            return [1, 2, 3, 4, '...', total];
        }
        
        if (current >= total - 2) {
            return [1, '...', total - 3, total - 2, total - 1, total];
        }
        
        return [1, '...', current - 1, current, current + 1, '...', total];
    }
    
    function changePage(page) {
        const totalPages = Math.ceil(state.filteredEmployees.length / state.itemsPerPage);
        
        if (page < 1 || page > totalPages) return;
        
        state.currentPage = page;
        renderTable();
        updatePagination();
        
        // Scroll to top of table
        document.querySelector('.table-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    
    // ============================================
    // Select All Checkbox
    // ============================================
    
    function setupSelectAll() {
        const selectAllCheckbox = document.getElementById('selectAll');
        if (!selectAllCheckbox) return;
        
        selectAllCheckbox.addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('.employees-table tbody .checkbox, .employee-table tbody .checkbox');
            checkboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
        });
    }
    
    // ============================================
    // Table Actions
    // ============================================
    
    function setupTableActions() {
        // View buttons
        document.querySelectorAll('.action-btn:nth-child(1)').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const row = this.closest('tr');
                const empId = row.querySelector('.emp-id').textContent;
                const empName = row.querySelector('.employee-name').textContent;
                viewEmployee(empId, empName);
            });
        });
        
        // Edit buttons
        document.querySelectorAll('.action-btn:nth-child(2)').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const row = this.closest('tr');
                const empId = row.querySelector('.emp-id').textContent;
                const empName = row.querySelector('.employee-name').textContent;
                editEmployee(empId, empName);
            });
        });
        
        // Disable/Enable buttons
        document.querySelectorAll('.action-btn:nth-child(3)').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const row = this.closest('tr');
                const empId = row.querySelector('.emp-id').textContent;
                const empName = row.querySelector('.employee-name').textContent;
                const statusBadge = row.querySelector('.status-badge');
                const isActive = statusBadge.textContent === 'Active';
                
                if (isActive) {
                    disableEmployee(empId, empName, row);
                } else {
                    enableEmployee(empId, empName, row);
                }
            });
        });
        
        // Row click to view
        document.querySelectorAll('.employees-table tbody tr, .employee-table tbody tr').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.type === 'checkbox' || e.target.closest('.action-btn')) return;
                
                const empId = this.querySelector('.emp-id').textContent;
                const empName = this.querySelector('.employee-name').textContent;
                viewEmployee(empId, empName);
            });
        });
    }
    
    function viewEmployee(empId, empName) {
        console.log(`Viewing employee: ${empName} (${empId})`);
        // In production, navigate to employee detail page
        alert(`View Employee: ${empName}\nID: ${empId}\n\nThis would open the employee detail page.`);
    }
    
    function editEmployee(empId, empName) {
        console.log(`Editing employee: ${empName} (${empId})`);
        // In production, open edit modal or navigate to edit page
        alert(`Edit Employee: ${empName}\nID: ${empId}\n\nThis would open the employee edit form.`);
    }
    
    function disableEmployee(empId, empName, row) {
        if (!confirm(`Are you sure you want to disable ${empName}?\n\nThey will no longer have access to the system.`)) {
            return;
        }
        
        console.log(`Disabling employee: ${empName} (${empId})`);
        
        // Update UI
        const statusBadge = row.querySelector('.status-badge');
        statusBadge.textContent = 'Inactive';
        statusBadge.className = 'status-badge status-inactive';
        
        // Update action button
        const actionBtn = row.querySelector('.action-btn:nth-child(3)');
        actionBtn.className = 'action-btn btn-success';
        actionBtn.title = 'Enable';
        actionBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M13 5L6 12L3 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        `;
        
        updateStats();
        
        // Show success message
        showNotification('Employee disabled successfully', 'success');
    }
    
    function enableEmployee(empId, empName, row) {
        console.log(`Enabling employee: ${empName} (${empId})`);
        
        // Update UI
        const statusBadge = row.querySelector('.status-badge');
        statusBadge.textContent = 'Active';
        statusBadge.className = 'status-badge status-active';
        
        // Update action button
        const actionBtn = row.querySelector('.action-btn:nth-child(3)');
        actionBtn.className = 'action-btn btn-danger';
        actionBtn.title = 'Disable';
        actionBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
                <path d="M11 5L5 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
        `;
        
        updateStats();
        
        // Show success message
        showNotification('Employee enabled successfully', 'success');
    }
    
    // ============================================
    // Top Action Buttons
    // ============================================
    
    document.addEventListener("DOMContentLoaded", () => {
    const addEmployeeBtn = document.getElementById("addEmployeeBtn");

    if (addEmployeeBtn) {
        addEmployeeBtn.addEventListener("click", function () {
            window.location.href = "create_employee.html";
        });
    }
});


        
    
    // ============================================
    // Stats Update
    // ============================================
    
    function updateStats() {
        const allRows = document.querySelectorAll('.employees-table tbody tr, .employee-table tbody tr');
        let activeCount = 0;
        let inactiveCount = 0;
        
        allRows.forEach(row => {
            const status = row.querySelector('.status-badge');
            if (status) {
                if (status.textContent === 'Active') {
                    activeCount++;
                } else {
                    inactiveCount++;
                }
            }
        });
        
        // Update stat cards
        const statCards = document.querySelectorAll('.stat-card');
        if (statCards[1]) {
            statCards[1].querySelector('.stat-value').textContent = activeCount;
        }
        if (statCards[2]) {
            statCards[2].querySelector('.stat-value').textContent = inactiveCount;
        }
    }
    
    // ============================================
    // Notifications
    // ============================================
    
    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 16px 20px;
            background: ${type === 'success' ? '#10B981' : '#3B82F6'};
            color: white;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            z-index: 10000;
            font-weight: 600;
            animation: slideIn 0.3s ease-out;
        `;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
    
    // Add notification animations
    if (!document.querySelector('#notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideIn {
                from {
                    transform: translateX(400px);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            @keyframes slideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(400px);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    // ============================================
    // Initialize on DOM Ready
    // ============================================
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
    console.log('%cEmployees Management Module Loaded', 'color: #10B981; font-weight: bold;');
    
})();
// =============================================
// research.js — Role-aware version
// Admin: full control (all existing behaviour unchanged)
// Employee: view/edit only what permissions allow
// =============================================

let currentFileId   = null;
let allFiles        = [];
let currentFilter   = 'all';
let currentUserRole = null;   // resolved on first loadFile() response

// ── ROLE HELPER ───────────────────────────────────────────────────────────────
function isAdmin() {
    return currentUserRole === "admin";
}

// ── INIT ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {

    loadFiles();

    const modal = document.getElementById("newFileModal");

    document.getElementById("openNewFileBtn")?.addEventListener("click", () => {
        modal?.classList.add("show");
    });

    document.getElementById("openNewFileBtn2")?.addEventListener("click", () => {
        modal?.classList.add("show");
    });

    document.getElementById("closeModalBtn")?.addEventListener("click", () => {
        modal?.classList.remove("show");
    });

    modal?.addEventListener("click", function (e) {
        if (e.target === modal) modal.classList.remove("show");
    });

    // Radio toggle: show correct options block in modal
    document.querySelectorAll("input[name='fileType']").forEach(radio => {
        radio.addEventListener("change", () => {
            const isExcel = radio.value === "excel";
            document.getElementById("excelOptions").style.display = isExcel ? "block" : "none";
            document.getElementById("docOptions").style.display   = isExcel ? "none"  : "block";
        });
    });

    document.getElementById("generateTableBtn")?.addEventListener("click", generatePreviewTable);
    document.getElementById("saveFileBtn")?.addEventListener("click", saveFile);

    // Filter tabs
    document.querySelectorAll(".filter-tab").forEach(btn => {
        btn.addEventListener("click", () => {
            const filter = btn.dataset.filter;
            setFilter(filter);
        });
    });

    // Version History button (in info bar)
    document.getElementById("versionHistoryBtn")?.addEventListener("click", toggleVersionDrawer);
});

// ── FILTER ────────────────────────────────────────────────────────────────────
function setFilter(filter) {
    currentFilter = filter;

    // Update tab active states
    document.querySelectorAll(".filter-tab").forEach(btn => {
        btn.classList.remove("tab-active-all", "tab-active-xlsx", "tab-active-docx");
    });
    const activeTab = document.querySelector(`.filter-tab[data-filter="${filter}"]`);
    if (activeTab) {
        const cls = filter === 'all' ? 'tab-active-all'
                  : filter === 'xlsx' ? 'tab-active-xlsx' : 'tab-active-docx';
        activeTab.classList.add(cls);
    }

    renderFileList(allFiles);
}

// ── LOAD FILES ────────────────────────────────────────────────────────────────
async function loadFiles() {
    try {
        const files = await API.request("/research/files");

        allFiles = files || [];

        updateStatsStrip(allFiles);
        renderFileList(allFiles);

        // Auto-load first file
        if (allFiles.length > 0) {
            loadFile(allFiles[0].id);
        }

    } catch (err) {
        console.error("LoadFiles error:", err);
    }
}

function updateStatsStrip(files) {
    const total   = files.length;
    const excel   = files.filter(f => f.type === "excel").length;
    const docs    = files.filter(f => f.type === "document").length;

    const strip = document.querySelector(".stats-strip");
    if (!strip) return;

    strip.innerHTML = `
        <div class="stat-chip"><i class="fas fa-folder"></i> <strong>${total}</strong> Files</div>
        <div class="stat-chip"><i class="fas fa-table"></i> <strong>${excel}</strong> Spreadsheets</div>
        <div class="stat-chip"><i class="fas fa-file-alt"></i> <strong>${docs}</strong> Documents</div>
    `;
}

function renderFileList(files) {
    const fileList = document.getElementById("fileList");
    if (!fileList) return;

    // Filter
    const filtered = files.filter(f => {
        if (currentFilter === 'all')  return true;
        if (currentFilter === 'xlsx') return f.type === "excel";
        if (currentFilter === 'docx') return f.type === "document";
        return true;
    });

    // Update tab counts
    const allCount   = files.length;
    const xlsxCount  = files.filter(f => f.type === "excel").length;
    const docxCount  = files.filter(f => f.type === "document").length;

    const tabAll  = document.querySelector('.filter-tab[data-filter="all"] .tab-count');
    const tabXlsx = document.querySelector('.filter-tab[data-filter="xlsx"] .tab-count');
    const tabDocx = document.querySelector('.filter-tab[data-filter="docx"] .tab-count');
    if (tabAll)  tabAll.textContent  = allCount;
    if (tabXlsx) tabXlsx.textContent = xlsxCount;
    if (tabDocx) tabDocx.textContent = docxCount;

    fileList.innerHTML = "";

    if (filtered.length === 0) {
        fileList.innerHTML = `<div class="empty-state"><i class="fas fa-folder-open"></i><p>No files found</p></div>`;
        return;
    }

    filtered.forEach(file => {
        const isExcel = file.type === "excel";
        const extCls  = isExcel ? "xlsx" : "docx";
        const extTxt  = isExcel ? ".xlsx" : ".docx";
        const iconCls = isExcel
            ? "fas fa-table\" style=\"color:#16a34a;width:16px;font-size:0.82rem;flex-shrink:0;"
            : "fas fa-file-word\" style=\"color:#2563eb;width:16px;font-size:0.82rem;flex-shrink:0;";

        const div = document.createElement("div");
        div.className = "file-item" + (file.id === currentFileId ? " active" : "");
        div.dataset.type = extCls;
        div.dataset.id   = file.id;
        div.innerHTML = `
            <div class="file-item-left">
                <i class="${iconCls}"></i>
                <span>${file.name}</span>
            </div>
            <span class="file-ext ${extCls}">${extTxt}</span>
        `;
        div.onclick = () => loadFile(file.id);
        fileList.appendChild(div);
    });
}

// ── LOAD SINGLE FILE ──────────────────────────────────────────────────────────
async function loadFile(fileId) {
    if (!fileId) return;

    currentFileId = fileId;

    // Highlight active item in sidebar
    document.querySelectorAll(".file-item").forEach(el => {
        el.classList.toggle("active", parseInt(el.dataset.id) === fileId);
    });

    try {
        const data = await API.request(`/research/files/${fileId}`);

        // Resolve role on first response — stays set for the session
        if (data.role && !currentUserRole) {
            currentUserRole = data.role;
        }

        updateInfoBar(data);
        loadVersionHistory(fileId);

        const content = document.getElementById("contentArea");
        content.innerHTML = "";

        if (data.type === "excel") {
            renderExcel(data);
        } else {
            renderDocumentView(data);
        }
    } catch (err) {
        if (err.status === 403) {
            document.getElementById("contentArea").innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-lock"></i>
                    <p>You don't have permission to view this file.</p>
                </div>`;
        } else {
            console.error("loadFile error:", err);
        }
    }
}

// ── INFO BAR ──────────────────────────────────────────────────────────────────
function updateInfoBar(data) {
    const fileObj = allFiles.find(f => f.id === data.id) || {};

    const nameEl    = document.getElementById("fileName");
    const creatorEl = document.getElementById("fileCreator");
    const dateEl    = document.getElementById("fileDate");

    if (nameEl)    nameEl.textContent    = data.name || "";
    if (creatorEl) creatorEl.textContent = fileObj.created_by_name || "Admin";
    if (dateEl)    dateEl.textContent    = fileObj.created_at
        ? formatDate(fileObj.created_at) : "";
}

// ── VERSION HISTORY ───────────────────────────────────────────────────────────
function toggleVersionDrawer() {
    const drawer = document.querySelector(".version-drawer");
    if (!drawer) return;
    drawer.style.display = drawer.style.display === "none" ? "block" : "none";
}

async function loadVersionHistory(fileId) {
    const vhEl = document.getElementById("versionHistory");
    if (!vhEl) return;

    try {
        const data = await API.request(`/research/files/${fileId}`);
        const fileObj = allFiles.find(f => f.id === fileId) || {};

        vhEl.innerHTML = "";

        const versions = [];

        if (fileObj.updated_at && fileObj.updated_at !== fileObj.created_at) {
            versions.push({
                label: "Last edited",
                by: fileObj.updated_by_name || "Admin",
                date: fileObj.updated_at
            });
        }

        versions.push({
            label: "Created",
            by: fileObj.created_by_name || "Admin",
            date: fileObj.created_at
        });

        if (versions.length === 0) {
            vhEl.innerHTML = `<div class="version-item"><i class="fas fa-circle"></i><div>No history available</div></div>`;
            return;
        }

        versions.forEach((v, idx) => {
            const div = document.createElement("div");
            div.className = "version-item";
            div.innerHTML = `
                <i class="fas fa-circle"></i>
                <div>
                    <strong>${v.label}</strong> by ${v.by}
                    &nbsp;<span class="text-small">${v.date ? formatDate(v.date, true) : ""}</span>
                </div>
            `;
            vhEl.appendChild(div);
        });

    } catch (err) {
        console.error("Version history error:", err);
    }
}

// ── EXCEL RENDER ──────────────────────────────────────────────────────────────
function renderExcel(data) {
    const contentArea = document.getElementById("contentArea");
    contentArea.innerHTML = "";

    // Action bar — admin only
    if (isAdmin()) {
        const actionBar = document.createElement("div");
        actionBar.style.cssText = "display:flex;gap:10px;margin-bottom:12px;align-items:center;flex-wrap:wrap;";
        actionBar.innerHTML = `
            <button class="btn-secondary" id="addRowBtn"><i class="fas fa-plus"></i> Add Row</button>
            <button class="btn-secondary" id="addColBtn"><i class="fas fa-columns"></i> Add Column</button>
        `;
        contentArea.appendChild(actionBar);

        actionBar.querySelector("#addRowBtn").onclick = () => addRow(data.id);
        actionBar.querySelector("#addColBtn").onclick = () => addColumn(data.id);
    }

    const tableCard = document.createElement("div");
    tableCard.className = "table-card";

    const table = document.createElement("table");

    // Head
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    const numberHeader = document.createElement("th");
    numberHeader.textContent = "#";
    numberHeader.className = "row-number-header";
    headerRow.appendChild(numberHeader);

    data.columns.forEach(col => {
        const th = document.createElement("th");
        const wrapper = document.createElement("div");
        wrapper.className = "th-content";

        const title = document.createElement("span");
        title.textContent = col.name;
        wrapper.appendChild(title);

        // Column menu chevron — admin only
        if (isAdmin()) {
            const icon = document.createElement("i");
            icon.className = "fas fa-chevron-down";
            icon.onclick = (e) => {
                e.stopPropagation();
                showColumnMenu(col.id, col.name);
            };
            wrapper.appendChild(icon);
        }

        th.appendChild(wrapper);
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Body
    const tbody = document.createElement("tbody");

    data.rows.forEach(row => {
        const tr = document.createElement("tr");

        const numberCell = document.createElement("td");
        numberCell.textContent = row.row_number;
        numberCell.className = "row-number-cell";
        tr.appendChild(numberCell);

        // Index cells by column_id for correct alignment
        const cellByColId = {};
        row.cells.forEach(c => { cellByColId[c.column_id] = c; });

        data.columns.forEach(col => {
            const cell = cellByColId[col.id];
            const td   = document.createElement("td");

            if (!cell) {
                tr.appendChild(td);
                return;
            }

            const canEdit = isAdmin() ? true : !!cell.can_edit;

            if (canEdit) {
                td.contentEditable = "true";
                td.textContent = cell.value || "";
                td.onblur = async () => {
                    await updateCell(cell.cell_id, td.textContent);
                };
            } else {
                td.contentEditable = "false";
                td.textContent = cell.value || "";
                td.classList.add("readonly-cell");
            }

            tr.appendChild(td);
        });

        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    tableCard.appendChild(table);
    contentArea.appendChild(tableCard);
}

// ── ADD ROW ───────────────────────────────────────────────────────────────────
async function addRow(fileId) {
    try {
        await API.request(`/research/files/${fileId}/rows`, "POST", {});
        loadFile(fileId);
    } catch (err) {
        console.error("Add row error:", err);
    }
}

// ── ADD COLUMN ────────────────────────────────────────────────────────────────
async function addColumn(fileId) {
    const name = prompt("Enter column name:");
    if (!name) return;
    try {
        await API.request(`/research/files/${fileId}/columns`, "POST", { name });
        loadFile(fileId);
    } catch (err) {
        console.error("Add column error:", err);
    }
}

// ── UPDATE CELL ───────────────────────────────────────────────────────────────
async function updateCell(cellId, value) {
    try {
        await API.request(`/research/cells/${cellId}`, "PUT", { value });
    } catch (err) {
        console.error("Update cell error:", err);
    }
}

// ── COLUMN MENU ───────────────────────────────────────────────────────────────
async function showColumnMenu(columnId, columnName) {
    // Remove any existing overlay
    document.getElementById("columnMenuOverlay")?.remove();

    const overlay = document.createElement("div");
    overlay.id = "columnMenuOverlay";
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center;z-index:9999;";

    const box = document.createElement("div");
    box.style.cssText = "background:white;padding:24px;border-radius:14px;width:380px;max-width:92%;box-shadow:0 20px 60px rgba(0,0,0,0.18);";

    box.innerHTML = `
        <h3 style="margin-bottom:14px;font-size:1rem;color:var(--text-primary);">Column Settings</h3>
        <label style="font-size:0.8rem;color:var(--text-secondary);font-weight:600;">Column Name</label>
        <input id="renameInput" value="${columnName}" style="width:100%;padding:10px 12px;border:1.5px solid var(--border);border-radius:8px;margin:6px 0 14px;font-size:0.875rem;font-family:'Sora',sans-serif;outline:none;" />
        <label style="font-size:0.8rem;color:var(--text-secondary);font-weight:600;">User Permissions</label>
        <div id="userList" style="max-height:180px;overflow:auto;margin:8px 0 10px;border:1.5px solid var(--border);border-radius:8px;padding:6px 0;"></div>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:0.875rem;padding:8px 0;">
            <input type="checkbox" id="everyoneCheck" style="accent-color:var(--navy);" />
            <strong>Everyone can view & edit</strong>
        </label>
        <div style="display:flex;gap:10px;margin-top:18px;">
            <button id="saveColumn" class="btn-primary" style="flex:1;border-radius:10px;justify-content:center;">Save</button>
            <button id="deleteColumn" style="background:#fee2e2;color:#dc2626;border:1.5px solid #fecaca;padding:10px 18px;border-radius:10px;font-weight:600;cursor:pointer;font-family:'Sora',sans-serif;font-size:0.85rem;">Delete</button>
            <button id="closeBox" class="btn-cancel" style="border-radius:10px;">Cancel</button>
        </div>
    `;

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    // Load users
    try {
        const users = await API.getAdminEmployees();
        const userList = box.querySelector("#userList");
        users.forEach(user => {
            const div = document.createElement("div");
            div.style.cssText = "padding:8px 14px;border-bottom:1px solid var(--border-light);";
            div.innerHTML = `
                <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:0.875rem;color:var(--text-primary);">
                    <input type="checkbox" value="${user.id}" style="accent-color:var(--navy);" />
                    ${user.name}
                </label>
            `;
            userList.appendChild(div);
        });
    } catch (e) {
        box.querySelector("#userList").innerHTML = `<p style="padding:10px;font-size:0.8rem;color:var(--text-muted);">Could not load users</p>`;
    }

    box.querySelector("#saveColumn").onclick = async () => {
        const newName      = box.querySelector("#renameInput").value;
        const everyone     = box.querySelector("#everyoneCheck").checked;
        const selectedUsers = [...box.querySelectorAll("#userList input:checked")]
            .map(cb => parseInt(cb.value));

        await API.request(`/research/columns/${columnId}`, "PUT", { name: newName });
        await API.request(`/research/columns/${columnId}/permissions`, "POST", {
            user_ids: everyone ? [] : selectedUsers,
            everyone
        });

        overlay.remove();
        loadFile(currentFileId);
    };

    box.querySelector("#deleteColumn").onclick = async () => {
        if (!confirm("Delete this column and all its data?")) return;
        await API.request(`/research/columns/${columnId}`, "DELETE");
        overlay.remove();
        loadFile(currentFileId);
    };

    box.querySelector("#closeBox").onclick = () => overlay.remove();
    overlay.addEventListener("click", e => { if (e.target === overlay) overlay.remove(); });
}

// ── DOCUMENT VIEW ─────────────────────────────────────────────────────────────
async function renderDocumentView(data) {
    const contentArea = document.getElementById("contentArea");
    contentArea.innerHTML = "";

    const docWrapper = document.createElement("div");
    docWrapper.className = "doc-view-wrapper";

    // Visibility badge
    const visLabel = {
        admin:    '<span class="doc-vis-badge admin"><i class="fas fa-shield-alt" style="margin-right:4px;font-size:0.6rem;"></i>Admin Only</span>',
        everyone: '<span class="doc-vis-badge everyone"><i class="fas fa-globe" style="margin-right:4px;font-size:0.6rem;"></i>Everyone</span>',
        selected: '<span class="doc-vis-badge restricted"><i class="fas fa-users" style="margin-right:4px;font-size:0.6rem;"></i>Selected Users</span>'
    }[data.visibility] || '';

    // Edit button: show for admin always, show for employee only if data.can_edit === true
    const showEdit = isAdmin() || data.can_edit === true;

    const toolbar = document.createElement("div");
    toolbar.style.cssText = "display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap;";
    toolbar.innerHTML = `
        ${visLabel}
        <div style="flex:1;"></div>
        ${showEdit ? '<button class="btn-secondary" id="editDocBtn"><i class="fas fa-pen"></i> Edit</button>' : ''}
    `;
    docWrapper.appendChild(toolbar);

    // Document body (read mode)
    const docCard = document.createElement("div");
    docCard.className = "document-card";
    docCard.style.cursor = "default";
    docCard.innerHTML = `
        <div class="document-title" id="docTitle">${data.title || ""}</div>
        <div class="document-content" id="docContent" style="max-height:none;overflow:auto;">${data.content || "<em style='color:var(--text-muted)'>No content yet.</em>"}</div>
    `;
    docWrapper.appendChild(docCard);
    contentArea.appendChild(docWrapper);

    // Edit button → open editor
    if (showEdit) {
        toolbar.querySelector("#editDocBtn").onclick = () => openDocumentEditor(data);
    }
}

// ── DOCUMENT EDITOR ───────────────────────────────────────────────────────────
async function openDocumentEditor(data) {
    const contentArea = document.getElementById("contentArea");
    contentArea.innerHTML = "";

    // Load users only if admin (employee never sees permissions panel)
    let userCheckboxes = "";
    if (isAdmin()) {
        let users = [];
        try { users = await API.getAdminEmployees(); } catch (e) {}

        userCheckboxes = users.map(u => `
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;padding:6px 0;font-size:0.875rem;">
                <input type="checkbox" class="doc-user-perm" value="${u.id}" style="accent-color:var(--navy);" />
                ${u.name}
            </label>
        `).join("");
    }

    // Permissions panel — admin only
    const permissionsPanel = isAdmin() ? `
        <div style="background:var(--surface);border:1.5px solid var(--border);border-radius:var(--radius);padding:20px;">
            <div style="font-size:0.8rem;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:var(--text-secondary);margin-bottom:12px;"><i class="fas fa-shield-alt" style="color:var(--navy);margin-right:6px;"></i>Document Visibility</div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;">
                <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:0.875rem;font-weight:500;">
                    <input type="radio" name="docVisibility" value="everyone" ${data.visibility === 'everyone' ? 'checked' : ''} style="accent-color:var(--navy);" /> Everyone
                </label>
                <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:0.875rem;font-weight:500;">
                    <input type="radio" name="docVisibility" value="admin" ${data.visibility === 'admin' ? 'checked' : ''} style="accent-color:var(--navy);" /> Admin Only
                </label>
                <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:0.875rem;font-weight:500;">
                    <input type="radio" name="docVisibility" value="selected" ${data.visibility === 'selected' ? 'checked' : ''} style="accent-color:var(--navy);" /> Selected Users
                </label>
            </div>
            <div id="selectedUsersList" style="display:${data.visibility === 'selected' ? 'block' : 'none'};padding:10px 14px;border:1.5px solid var(--border);border-radius:8px;">
                ${userCheckboxes || '<p style="font-size:0.8rem;color:var(--text-muted);">No users available</p>'}
            </div>
        </div>
    ` : "";

    const editorHtml = `
        <div style="display:flex;flex-direction:column;gap:14px;">
            <!-- Toolbar -->
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                <input id="editorTitle" type="text" class="input-field" value="${data.title || ""}" placeholder="Document Title" style="font-size:1rem;font-weight:700;width:auto;flex:1;min-width:200px;" />
                <button class="btn-primary" id="saveDocBtn" style="border-radius:10px;"><i class="fas fa-save"></i> Save Changes</button>
                <button class="btn-secondary" id="cancelEditBtn"><i class="fas fa-times"></i> Cancel</button>
            </div>

            <!-- Rich text toolbar -->
            <div style="background:var(--surface);border:1.5px solid var(--border);border-radius:10px;padding:8px 12px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
                <button onclick="document.execCommand('bold')"      title="Bold"          style="background:none;border:none;cursor:pointer;padding:4px 8px;border-radius:6px;font-weight:700;font-size:0.9rem;color:var(--text-primary);" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'"><b>B</b></button>
                <button onclick="document.execCommand('italic')"    title="Italic"        style="background:none;border:none;cursor:pointer;padding:4px 8px;border-radius:6px;font-style:italic;font-size:0.9rem;color:var(--text-primary);" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'"><i>I</i></button>
                <button onclick="document.execCommand('underline')" title="Underline"     style="background:none;border:none;cursor:pointer;padding:4px 8px;border-radius:6px;text-decoration:underline;font-size:0.9rem;color:var(--text-primary);" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'"><u>U</u></button>
                <div style="width:1px;height:20px;background:var(--border);margin:0 4px;"></div>
                <button onclick="document.execCommand('insertUnorderedList')" title="Bullet List" style="background:none;border:none;cursor:pointer;padding:4px 8px;border-radius:6px;font-size:0.9rem;color:var(--text-primary);" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'"><i class="fas fa-list-ul"></i></button>
                <button onclick="document.execCommand('insertOrderedList')"   title="Numbered List" style="background:none;border:none;cursor:pointer;padding:4px 8px;border-radius:6px;font-size:0.9rem;color:var(--text-primary);" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'"><i class="fas fa-list-ol"></i></button>
                <div style="width:1px;height:20px;background:var(--border);margin:0 4px;"></div>
                <button onclick="document.execCommand('formatBlock', false, 'h2')" title="Heading" style="background:none;border:none;cursor:pointer;padding:4px 8px;border-radius:6px;font-size:0.9rem;color:var(--text-primary);font-weight:700;" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'">H</button>
                <button onclick="document.execCommand('formatBlock', false, 'p')"  title="Paragraph" style="background:none;border:none;cursor:pointer;padding:4px 8px;border-radius:6px;font-size:0.9rem;color:var(--text-primary);" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'">¶</button>
            </div>

            <!-- Editor body -->
            <div id="docEditorBody" contenteditable="true" style="
                background:var(--surface);
                border:1.5px solid var(--border);
                border-radius:var(--radius);
                padding:40px 48px;
                min-height:500px;
                font-size:0.9375rem;
                line-height:1.8;
                color:var(--text-primary);
                box-shadow:var(--shadow-md);
                outline:none;
                font-family:'Sora',sans-serif;
            ">${data.content || ""}</div>

            ${permissionsPanel}
        </div>
    `;

    contentArea.innerHTML = editorHtml;

    // Toggle selected users panel (admin only — element won't exist for employees)
    contentArea.querySelectorAll("input[name='docVisibility']").forEach(r => {
        r.addEventListener("change", () => {
            const sel = contentArea.querySelector("#selectedUsersList");
            if (sel) sel.style.display = r.value === "selected" ? "block" : "none";
        });
    });

    // Save
    contentArea.querySelector("#saveDocBtn").onclick = async () => {
        const title   = contentArea.querySelector("#editorTitle").value;
        const content = contentArea.querySelector("#docEditorBody").innerHTML;

        // Admin sends visibility + user_ids; employee sends only title + content
        const payload = { title, content };

        if (isAdmin()) {
            payload.visibility = contentArea.querySelector("input[name='docVisibility']:checked")?.value || "admin";
            payload.user_ids   = [...contentArea.querySelectorAll(".doc-user-perm:checked")].map(cb => parseInt(cb.value));
        }

        try {
            await API.request(`/research/documents/${data.doc_id}`, "PUT", payload);
            loadFile(currentFileId);
        } catch (err) {
            alert("Save failed. Please try again.");
            console.error("Save doc error:", err);
        }
    };

    // Cancel
    contentArea.querySelector("#cancelEditBtn").onclick = () => loadFile(currentFileId);
}

// ── MODAL: GENERATE PREVIEW TABLE ─────────────────────────────────────────────
function generatePreviewTable() {
    const rows = parseInt(document.querySelectorAll("#excelOptions input[type='number']")[0].value);
    const cols = parseInt(document.querySelectorAll("#excelOptions input[type='number']")[1].value);

    const content = document.getElementById("contentArea");
    content.innerHTML = "";

    const tableCard = document.createElement("div");
    tableCard.className = "table-card";

    const table = document.createElement("table");

    const headerRow = document.createElement("tr");
    const emptyHeader = document.createElement("th");
    emptyHeader.textContent = "#";
    headerRow.appendChild(emptyHeader);

    for (let c = 0; c < cols; c++) {
        const th = document.createElement("th");
        th.textContent = `Column ${c + 1}`;
        headerRow.appendChild(th);
    }
    table.appendChild(headerRow);

    for (let r = 0; r < rows; r++) {
        const tr = document.createElement("tr");
        const rowNumber = document.createElement("td");
        rowNumber.textContent = r + 1;
        rowNumber.style.fontWeight = "600";
        rowNumber.style.background = "#f1f5f9";
        tr.appendChild(rowNumber);

        for (let c = 0; c < cols; c++) {
            const td = document.createElement("td");
            td.style.border = "1px solid #e2e8f0";
            td.style.minHeight = "40px";
            td.style.height = "40px";
            td.contentEditable = true;
            td.innerHTML = "&nbsp;";
            tr.appendChild(td);
        }
        table.appendChild(tr);
    }

    tableCard.appendChild(table);
    content.appendChild(tableCard);
}

// ── MODAL: SAVE FILE ──────────────────────────────────────────────────────────
async function saveFile() {
    const type = document.querySelector("input[name='fileType']:checked").value;

    try {
        if (type === "excel") {
            const name    = document.querySelector("#excelOptions input[type='text']").value;
            const numberInputs = document.querySelectorAll("#excelOptions input[type='number']");
            const rows    = parseInt(numberInputs[0].value);
            const columns = parseInt(numberInputs[1].value);

            const file = await API.request("/research/files", "POST", {
                name, type: "excel", rows, columns
            });

            document.getElementById("newFileModal").classList.remove("show");
            await loadFiles();
            loadFile(file.id);
        }

        if (type === "doc") {
            const title   = document.querySelector("#docOptions input[type='text']").value;
            const content = document.querySelector("#docOptions textarea").value;
            const visEl   = document.querySelector("#docOptions select");
            const visMap  = { 0: "everyone", 1: "admin", 2: "selected" };
            const visibility = visMap[visEl?.selectedIndex] || "admin";

            const file = await API.request("/research/files", "POST", {
                name: title, type: "document", title, content, visibility
            });

            document.getElementById("newFileModal").classList.remove("show");
            await loadFiles();
            loadFile(file.id);
        }

    } catch (err) {
        console.error("Save file error:", err);
        alert("Failed to create file. Please try again.");
    }
}

// ── HELPERS ───────────────────────────────────────────────────────────────────
function formatDate(isoString, withTime = false) {
    if (!isoString) return "";
    const d = new Date(isoString);
    const date = d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    if (!withTime) return date;
    const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    return `${date} · ${time}`;
}
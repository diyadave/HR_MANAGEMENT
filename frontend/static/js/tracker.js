
(function() {
  // Ensure API is available
  if (!window.API) {
    console.error("API helper not loaded. Please ensure ../../static/js/api.js is included.");
    return;
  }

  // ==================== STATE ====================
  let ws = null;
  let taskInterval = null;
  let renderInterval = null;
  
  let lastServerSeconds = 0;
  let lastSyncTime = 0;
  let attendanceSeconds = 0;
  let taskSeconds = 0;
  
  let isClockedIn = false;
  let activeTask = null;
  // ==================== DOM ELEMENTS ====================
let elements = {};

function initTrackerElements() {
  elements = {
    status: document.getElementById('trackerStatus'),
    attendanceTimer: document.getElementById('trackerTimer'),
    clockBtn: document.getElementById('clockBtn'),
    taskName: document.getElementById('activeTaskName'),
    taskTimer: document.getElementById('taskTimer'),
    taskBtn: document.getElementById('taskBtn')
  };

  // If any element missing → do nothing
  if (!elements.clockBtn) return false;

  elements.clockBtn.addEventListener('click', handleClock);
  elements.taskBtn.addEventListener('click', handleTaskAction);

  return true;
}

  // ==================== UTILITY FUNCTIONS ====================
  function formatTime(seconds) {
    if (!seconds || seconds < 0) seconds = 0;
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  function getIstHourMinute() {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Kolkata",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    }).formatToParts(new Date());

    const hourPart = parts.find((p) => p.type === "hour");
    const minutePart = parts.find((p) => p.type === "minute");
    const hour = Number(hourPart?.value || 0);
    const minute = Number(minutePart?.value || 0);
    return { hour, minute };
  }

  function isIstBreakNow() {
    const { hour, minute } = getIstHourMinute();
    const totalMinutes = (hour * 60) + minute;
    return totalMinutes >= (13 * 60) && totalMinutes < (14 * 60);
  }

  function stopAllIntervals() {
    if (taskInterval) {
      clearInterval(taskInterval);
      taskInterval = null;
    }
    if (renderInterval) {
      clearInterval(renderInterval);
      renderInterval = null;
    }
  }

  // ==================== TIMER CONTROLS ====================
  async function syncAttendance() {
    const data = await API.getActiveAttendance();
    lastServerSeconds = data.worked_seconds || 0;
    lastSyncTime = Date.now();
    isClockedIn = data.is_running || false;
    attendanceSeconds = lastServerSeconds;
    elements.attendanceTimer.textContent = formatTime(attendanceSeconds);
    updateClockButtonState();
    emitStateChange();
  }

  function startRendering() {
    if (renderInterval) clearInterval(renderInterval);
    renderInterval = setInterval(() => {
      if (!isClockedIn) {
        attendanceSeconds = lastServerSeconds;
        elements.attendanceTimer.textContent = formatTime(attendanceSeconds);
        return;
      }
      const elapsed = Math.floor((Date.now() - lastSyncTime) / 1000);
      const displaySeconds = lastServerSeconds + elapsed;
      attendanceSeconds = displaySeconds;
      elements.attendanceTimer.textContent = formatTime(displaySeconds);
    }, 1000);
  }

  function getCurrentUserId() {
    const rawId = localStorage.getItem("user_id");
    if (rawId && !Number.isNaN(Number(rawId))) return Number(rawId);
    try {
      const rawUser = localStorage.getItem("user");
      const parsed = rawUser ? JSON.parse(rawUser) : null;
      if (parsed && parsed.id !== undefined && !Number.isNaN(Number(parsed.id))) {
        return Number(parsed.id);
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  function connectAttendanceSocket(userId) {
    if (!userId) return;

    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.close();
    }

    ws = new WebSocket(`ws://localhost:8000/ws/attendance/${userId}`);

    ws.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "attendance_update") {
          await syncAttendance();
          updateUI();
        }
      } catch (error) {
        console.error("Attendance socket message error:", error);
      }
    };

    ws.onclose = () => {
      setTimeout(() => connectAttendanceSocket(userId), 3000);
    };

    ws.onerror = (error) => {
      console.error("Attendance socket error:", error);
    };
  }

  function startTaskTimer(initialSeconds) {
    if (taskInterval) {
      clearInterval(taskInterval);
    }
    
    taskSeconds = initialSeconds || 0;
    elements.taskTimer.textContent = formatTime(taskSeconds);
    
    taskInterval = setInterval(() => {
      taskSeconds++;
      elements.taskTimer.textContent = formatTime(taskSeconds);
    }, 1000);
  }

  function stopTaskTimer() {
    if (taskInterval) {
      clearInterval(taskInterval);
      taskInterval = null;
    }
    taskSeconds = 0;
    elements.taskTimer.textContent = formatTime(0);
  }

  // ==================== UPDATE UI ====================
  function updateUI() {
    const breakTime = isIstBreakNow();

    // Update attendance UI
    if (isClockedIn) {
      elements.status.textContent = "Clocked In";
      elements.status.classList.add("clocked-in");
      elements.clockBtn.textContent = "Clock Out";
      elements.clockBtn.classList.add("clock-out");
    } else {
      elements.status.textContent = "Clocked Out";
      elements.status.classList.remove("clocked-in");
      elements.clockBtn.textContent = "Clock In";
      elements.clockBtn.classList.remove("clock-out");
    }

    // Update task UI
    if (activeTask) {
      elements.taskName.textContent = activeTask.title || activeTask.task_title || "Unknown Task";
      elements.taskBtn.textContent = "Stop Task";
      elements.taskBtn.classList.add("running");
      elements.taskBtn.disabled = false;
    } else {
      elements.taskName.textContent = "No task running";
      elements.taskBtn.textContent = "Start Task";
      elements.taskBtn.classList.remove("running");
      elements.taskBtn.disabled = !isClockedIn; // Disable if not clocked in
    }

    if (breakTime) {
      elements.status.textContent = "Break Time (IST)";
      elements.taskBtn.disabled = true;
    }
    updateClockButtonState();
  }

  function updateClockButtonState() {
    const { hour } = getIstHourMinute();

    if (hour >= 13 && hour < 14) {
      elements.clockBtn.disabled = true;
      elements.clockBtn.textContent = "Break Time";
    } else if (hour >= 18) {
      elements.clockBtn.disabled = true;
      elements.clockBtn.textContent = "Office Closed";
    } else {
      elements.clockBtn.disabled = false;
      elements.clockBtn.textContent = isClockedIn ? "Clock Out" : "Clock In";
    }
  }

  function emitStateChange() {
    window.dispatchEvent(new CustomEvent("tracker:state-changed", {
      detail: {
        isClockedIn,
        activeTask,
        attendanceSeconds,
        taskSeconds
      }
    }));
  }

  // ==================== LOAD STATE FROM BACKEND ====================
  async function loadState() {
    try {
      // Load attendance state
      await syncAttendance();

      // Load active task
      // Load active task
    try {
      activeTask = await API.getActiveTask();

      if (activeTask) {
        activeTask.id = activeTask.id || activeTask.task_id;
        activeTask.title = activeTask.title || activeTask.task_title;

        if (activeTask.start_time) {
          const startTime = new Date(activeTask.start_time).getTime();
          const now = new Date().getTime();
          const runningSeconds = Math.floor((now - startTime) / 1000);
          const totalSeconds = activeTask.total_seconds || runningSeconds;
          taskSeconds = Math.max(totalSeconds, runningSeconds);

          if (!taskInterval) {
            startTaskTimer(taskSeconds);
          }
        } else {
          taskSeconds = activeTask.worked_seconds || 0;
          elements.taskTimer.textContent = formatTime(taskSeconds);
        }
      } else {
        activeTask = null;
        stopTaskTimer();
      }

    } catch (e) {
      activeTask = null;
      stopTaskTimer();
    }
      updateUI();
      emitStateChange();

    } catch (error) {

        if (error.message.toLowerCase().includes("session expired")) {
            window.location.href = "../auth/login.html";
            return;
        }

        console.error("Failed to load tracker state:", error);
        }
    }
      

  // ==================== ATTENDANCE ACTIONS ====================
  async function handleClock() {
    elements.clockBtn.disabled = true;
    
    try {
      if (isClockedIn) {
        // CLOCK OUT
        await API.clockOut();

        // Stop any running task
        if (activeTask) {
          try {
            await API.stopTask(activeTask.id || activeTask.task_id);
            activeTask = null;
            stopTaskTimer();
          } catch (e) {
            console.error("Failed to stop task on clock out:", e);
          }
        }
        
        // Reset state
        isClockedIn = false;
        lastServerSeconds = 0;
        attendanceSeconds = 0;
        elements.attendanceTimer.textContent = formatTime(0);
        
      } else {
        // CLOCK IN
        await API.clockIn();
      }
      
      // Reload full state to ensure sync
      await loadState();
      
    } catch (error) {
      console.error("Clock action failed:", error);
      alert(error.message || "Failed to clock in/out. Please try again.");
    } finally {
      elements.clockBtn.disabled = false;
    }
  }

  // ==================== TASK ACTIONS ====================
  async function handleTaskAction() {
    elements.taskBtn.disabled = true;
    
    try {
      if (activeTask) {
        // STOP TASK
        await API.stopTask(activeTask.id || activeTask.task_id);
        
        // Stop task timer
        stopTaskTimer();
        activeTask = null;
        
      } else {
        if (!isClockedIn) {
          alert("Clock in first to start task timer.");
          return;
        }
        // START TASK - Redirect to tasks page to select a task
        window.location.href = "../employee/tasks.html";
        return;
      }
      
      // Reload state
      await loadState();
      
    } catch (error) {
      console.error("Task action failed:", error);
      alert(error.message || "Failed to manage task. Please try again.");
    } finally {
      elements.taskBtn.disabled = false;
    }
  }
async function startTask(taskId, title) {
    try {
        await API.startTask(taskId);
        activeTask = { id: taskId, title: title };
        startTaskTimer(0);
        updateUI();
        return true;
    } catch (err) {
        alert(err.message);
        return false;
    }
}

async function stopTask() {
    if (!activeTask) return false;

    try {
        await API.stopTask(activeTask.id);
        activeTask = null;
        stopTaskTimer();
        updateUI();
        return true;
    } catch (err) {
        alert(err.message);
        return false;
    }
}
  // ==================== PUBLIC API FOR OTHER PAGES ====================
 
window.Tracker = {
    startTask,
    stopTask,
    getState: () => ({
        isClockedIn,
        activeTask,
        attendanceSeconds,
        taskSeconds
    }),
    refresh: loadState
};

  // ==================== INITIALIZATION ====================
  
  // Load initial state
function safeInit() {
  if (initTrackerElements()) {
    loadState().then(() => {
      startRendering();
      const currentUserId = getCurrentUserId();
      if (currentUserId) {
        connectAttendanceSocket(currentUserId);
      }
    }).catch((err) => {
      console.error("Tracker init failed:", err);
    });
    setInterval(updateClockButtonState, 60000);
    setInterval(() => {
      const { hour, minute } = getIstHourMinute();
      if (hour === 0 && minute === 0) {
        location.reload();
      }
    }, 60000);
  } else {
    // retry if DOM not ready yet
    setTimeout(safeInit, 100);
  }
}

safeInit();
  
  // Re-check state when page becomes visible (navigation with bfcache)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      loadState();
    }
  });

  // Listen for storage events (if multiple tabs)
  window.addEventListener('storage', (e) => {
    if (e.key === 'access_token') {
      loadState();
    }
  });

})();


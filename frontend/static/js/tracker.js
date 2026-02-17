
(function() {
  // Ensure API is available
  if (!window.API) {
    console.error("API helper not loaded. Please ensure ../../static/js/api.js is included.");
    return;
  }

  // ==================== STATE ====================
  let attendanceInterval = null;
  let taskInterval = null;
  
  let attendanceSeconds = 0;
  let taskSeconds = 0;
  
  let isClockedIn = false;
  let activeTask = null;
  let taskStartTime = null;
  // ==================== RESTORE STATE FROM LOCAL STORAGE ====================
const savedState = localStorage.getItem("tracker_state");
if (savedState) {
  try {
    const parsed = JSON.parse(savedState);
    isClockedIn = parsed.isClockedIn || false;
    activeTask = parsed.activeTask || null;
  } catch (e) {
    console.warn("Failed to parse saved tracker state");
  }
}

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

  function stopAllIntervals() {
    if (attendanceInterval) {
      clearInterval(attendanceInterval);
      attendanceInterval = null;
    }
    if (taskInterval) {
      clearInterval(taskInterval);
      taskInterval = null;
    }
  }

  // ==================== TIMER CONTROLS ====================
  function startAttendanceTimer(initialSeconds) {
    stopAllIntervals();
    
    attendanceSeconds = initialSeconds || 0;
    elements.attendanceTimer.textContent = formatTime(attendanceSeconds);
    
    attendanceInterval = setInterval(() => {
      attendanceSeconds++;
      elements.attendanceTimer.textContent = formatTime(attendanceSeconds);
    }, 1000);
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
  }

  // ==================== LOAD STATE FROM BACKEND ====================
  async function loadState() {
    try {
      // Load attendance state
      const attendance = await API.getActiveAttendance();
      isClockedIn = attendance.is_running || false;
      attendanceSeconds = attendance.worked_seconds || 0;
      
      elements.attendanceTimer.textContent = formatTime(attendanceSeconds);
      
      if (isClockedIn) {
        startAttendanceTimer(attendanceSeconds);
      } else {
        if (attendanceInterval) {
          clearInterval(attendanceInterval);
          attendanceInterval = null;
        }
      }

      // Load active task
      try {
        activeTask = await API.getActiveTask();
        if (activeTask) {
        activeTask.id = activeTask.id || activeTask.task_id;
        activeTask.title = activeTask.title || activeTask.task_title;
        }
        
        if (activeTask) {
          // Calculate task duration if task is running
          if (activeTask.start_time) {
            const startTime = new Date(activeTask.start_time).getTime();
            const now = new Date().getTime();
            taskSeconds = Math.floor((now - startTime) / 1000);
            startTaskTimer(taskSeconds);
          } else {
            taskSeconds = activeTask.worked_seconds || 0;
            elements.taskTimer.textContent = formatTime(taskSeconds);
          }
        } else {
          activeTask = null;
          stopTaskTimer();
        }
      } catch (e) {
        // No active task is fine
        activeTask = null;
        stopTaskTimer();
      }

      updateUI();
      // ==================== SAVE STATE TO LOCAL STORAGE ====================
localStorage.setItem("tracker_state", JSON.stringify({
  isClockedIn,
  activeTask
}));

      // Store state in window for other pages to access
    

    } catch (error) {

        if (error.message.toLowerCase().includes("unauthorized")) {
            localStorage.removeItem("access_token");
            window.location.href = "/login.html";
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
        
        // Stop attendance timer
        if (attendanceInterval) {
          clearInterval(attendanceInterval);
          attendanceInterval = null;
        }
        
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
        attendanceSeconds = 0;
        elements.attendanceTimer.textContent = formatTime(0);
        
      } else {
        // CLOCK IN
        const response = await API.clockIn();
        isClockedIn = true;
        attendanceSeconds = response.worked_seconds || 0;
        startAttendanceTimer(attendanceSeconds);
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
    loadState();
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


document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("loginForm");
    const submitBtn = document.getElementById("submitBtn");
    const btnText = submitBtn.querySelector(".btn-text");
    const btnLoader = submitBtn.querySelector(".btn-loader");
    const errorMessage = document.getElementById("errorMessage");

    const passwordInput = document.getElementById("password");
    const togglePasswordBtn = document.querySelector(".toggle-password");
    const eyeIcon = document.querySelector(".eye-icon");
    const eyeOffIcon = document.querySelector(".eye-off-icon");

    /* -----------------------------
       Password show / hide
    ------------------------------ */
    togglePasswordBtn.addEventListener("click", () => {
        const isPassword = passwordInput.type === "password";
        passwordInput.type = isPassword ? "text" : "password";

        eyeIcon.classList.toggle("hidden", isPassword);
        eyeOffIcon.classList.toggle("hidden", !isPassword);
    });

    /* -----------------------------
       Login submit
    ------------------------------ */
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        hideError();
        setLoading(true);

        const employee_id = document.getElementById("employee_id").value.trim();
        const password = passwordInput.value;
        const stayLoggedIn = document.getElementById("stayLoggedIn")?.checked === true;

        if (!employee_id || !password) {
            showError("Employee ID and password are required");
            setLoading(false);
            return;
        }
        if (/\s/.test(employee_id)) {
            showError("Employee ID cannot contain spaces");
            setLoading(false);
            return;
        }

        try {
            const data = await API.login({
                employee_id,
                password
            });

            if (typeof window.saveAuthSession === "function") {
                window.saveAuthSession(data, stayLoggedIn);
            } else {
                localStorage.setItem("access_token", data.access_token);
                localStorage.setItem("refresh_token", data.refresh_token);
                localStorage.setItem("user", JSON.stringify(data.user));
            }


            // 🔐 FORCE PASSWORD CHANGE (FIRST LOGIN)
            if (data.force_password_change) {
                window.location.href = "../auth/change_password.html";
                return;
            }

            // Role-based redirect
            if (data.user.role === "admin") {
                window.location.href = "../admin/dashboard.html";
            } else {
                window.location.href = "../employee/dashboard.html";
            }

        } catch (err) {
            showError(err.message || "Login failed");
        } finally {
            setLoading(false);
        }
    });

    /* -----------------------------
       Helpers
    ------------------------------ */
    function setLoading(isLoading) {
        submitBtn.disabled = isLoading;
        btnText.classList.toggle("hidden", isLoading);
        btnLoader.classList.toggle("hidden", !isLoading);
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.classList.remove("hidden");
    }

    function hideError() {
        errorMessage.textContent = "";
        errorMessage.classList.add("hidden");
    }
});

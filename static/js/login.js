document.addEventListener("DOMContentLoaded", () => {
  const registrationForm = document.querySelector("[data-registration-form]");
  if (registrationForm) {
    const registrationPassword = registrationForm.querySelector("#password");
    const confirmPassword = registrationForm.querySelector("#confirm-password");
    const setRegistrationError = (field, message) => {
      const error = document.querySelector(`#${field.id}-error`);
      if (!error) return;
      error.textContent = message;
      field.setAttribute("aria-invalid", message ? "true" : "false");
    };

    registrationForm.addEventListener("submit", (event) => {
      if (!registrationPassword || !confirmPassword) return;
      const minimumLength = Number(registrationPassword.minLength) || 0;
      const maximumLength = registrationPassword.maxLength;
      const passwordLength = registrationPassword.value.length;
      const passwordValid = passwordLength >= minimumLength
        && (maximumLength < 0 || passwordLength <= maximumLength);
      const confirmationValid = confirmPassword.value === registrationPassword.value;
      setRegistrationError(
        registrationPassword,
        passwordValid
          ? ""
          : registrationForm.dataset.passwordError || `Password must be at least ${minimumLength} characters long.`
      );
      setRegistrationError(
        confirmPassword,
        confirmationValid ? "" : "Passwords do not match."
      );
      if (!passwordValid || !confirmationValid) event.preventDefault();
    });
  }

  const form = document.querySelector("[data-login-form]");
  const roleInput = document.querySelector("[data-login-role-input]");
  const title = document.querySelector("[data-login-title]");
  const subtitle = document.querySelector("[data-login-subtitle]");
  const eyebrow = document.querySelector("[data-login-eyebrow]");
  const submitLabel = document.querySelector("[data-submit-label]");
  const registerLink = document.querySelector("[data-register-link]");
  const adminRegisterLink = document.querySelector("[data-admin-register-link]");
  const forgotLink = document.querySelector("[data-forgot-link]");
  const googleButton = document.querySelector("[data-google-sign-in]");
  const googleMessage = document.querySelector("[data-google-message]");
  const email = document.querySelector("#email");
  const password = document.querySelector("#password");

  const updateRole = (role) => {
    if (!roleInput || !title || !subtitle || !submitLabel) return;
    const isAdmin = role === "admin";
    roleInput.value = role;
    title.textContent = isAdmin ? "Admin panel" : "Welcome back";
    subtitle.textContent = isAdmin ? "Authorized admins only" : "Log in to your user account";
    submitLabel.textContent = isAdmin ? "Log in as admin" : "Log in as user";
    if (eyebrow) eyebrow.textContent = isAdmin ? "Admin access" : "Your workspace";
    if (registerLink) registerLink.hidden = isAdmin;
    if (adminRegisterLink) adminRegisterLink.hidden = !isAdmin;
    if (forgotLink) {
      const url = new URL(forgotLink.href);
      url.searchParams.set("role", role);
      forgotLink.href = url.toString();
    }
    document.querySelectorAll("[data-role-choice]").forEach((button) => {
      const active = button.dataset.roleChoice === role;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("role", role);
    window.history.replaceState({}, "", currentUrl);
  };

  document.querySelectorAll("[data-role-choice]").forEach((button) => {
    button.addEventListener("click", () => updateRole(button.dataset.roleChoice));
  });

  const setFieldError = (field, message) => {
    const error = document.querySelector(`#${field.id}-error`);
    if (!error) return;
    error.textContent = message;
    field.setAttribute("aria-invalid", message ? "true" : "false");
  };

  if (form && email && password) {
    form.addEventListener("submit", (event) => {
      const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim());
      const passwordValid = password.value.length > 0;
      setFieldError(email, emailValid ? "" : "Enter a valid email address.");
      setFieldError(password, passwordValid ? "" : "Enter your password.");
      if (!emailValid || !passwordValid) {
        event.preventDefault();
        return;
      }

      const submit = form.querySelector("[data-login-submit]");
      if (submit) {
        submit.disabled = true;
        submit.setAttribute("aria-busy", "true");
        const label = submit.querySelector("[data-submit-label]");
        const loading = submit.querySelector("[data-loading-label]");
        if (label) label.hidden = true;
        if (loading) loading.hidden = false;
      }
    });
  }

  if (googleButton && googleMessage) {
    googleButton.addEventListener("click", () => {
      googleMessage.textContent = "Google sign-in is not configured for this app yet.";
    });
  }

  const startingRole = document.querySelector(".login-screen")?.dataset.loginRole;
  updateRole(startingRole === "admin" ? "admin" : "user");
});

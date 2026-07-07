// Bootstrap validation for the login form
const loginForm = document.querySelector("#loginModal form");
if (loginForm) {
  loginForm.addEventListener("submit", function (event) {
    if (!loginForm.checkValidity()) {
      event.preventDefault();
      event.stopPropagation();
    }
    loginForm.classList.add("was-validated");
  });
}

// Toggle password visibility for the login modal
const togglePassword = document.querySelector("#togglePassword");
const passwordInput = document.querySelector("#loginModal #password");
if (togglePassword && passwordInput) {
  togglePassword.addEventListener("click", function () {
    const type =
      passwordInput.getAttribute("type") === "password" ? "text" : "password";
    passwordInput.setAttribute("type", type);

    // Toggle icons to show/hide password
    this.querySelector("i").classList.toggle("fa-eye");
    this.querySelector("i").classList.toggle("fa-eye-slash");
  });
}

// Function to validate file count
function validateFileCount(input) {
  const fileCount = input.files.length;

  if (fileCount > 10) {
    if (window.showToast) {
      window.showToast(
        "Vous pouvez télécharger jusqu'à 10 fichiers maximum.",
        "warning",
      );
    } else {
      alert("Vous pouvez télécharger jusqu'à 10 fichiers maximum.");
    }
    input.value = ""; // Reset file input
    return;
  }
}

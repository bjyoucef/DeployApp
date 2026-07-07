/**
 * Modern Toast Notifications
 * This script provides a premium notification UI and overrides the global Toastify
 * to ensure backward compatibility across the application without changing existing calls.
 */

const modernToastIcons = {
  success: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`,
  error: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`,
  danger: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`,
  info: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`,
  warning: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>`,
};

function initModernToastContainer() {
  let container = document.getElementById("modern-toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "modern-toast-container";
    document.body.appendChild(container);
  }
  return container;
}

function showModernToast(message, type = "info", durationOptions = 4000) {
  const container = initModernToastContainer();
  const toast = document.createElement("div");

  // Normalize type (some parts of the app might use bootstrap class names like 'danger', 'warning', 'success', 'info')
  let normalizedType = type.toLowerCase().replace("alert-", "");
  if (!modernToastIcons[normalizedType]) {
    if (
      normalizedType.includes("err") ||
      normalizedType.includes("fail") ||
      normalizedType === "danger"
    )
      normalizedType = "error";
    else if (normalizedType.includes("warn")) normalizedType = "warning";
    else if (normalizedType.includes("succ")) normalizedType = "success";
    else normalizedType = "info";
  }

  toast.classList.add("modern-toast", normalizedType);

  // Structure HTML de la notification
  toast.innerHTML = `
        <div class="modern-toast-content">
            <div class="icon">${modernToastIcons[normalizedType]}</div>
            <div class="message">${message}</div>
            <button class="close-btn" onclick="closeModernToast(this.parentElement.parentElement)">&times;</button>
        </div>
        <div class="progress"></div>
    `;

  container.appendChild(toast);

  // Apparition animée
  // Request animation frame allows the browser to compute styles before applying 'active'
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      toast.classList.add("active");
    });
  });

  // Lancer l'animation de la barre de progression si la durée n'est pas infinie (0 ou indéfinie)
  let duration = parseInt(durationOptions);
  if (isNaN(duration) || duration <= 0) {
    duration = 4000; // Default duration
  }

  if (duration > 0) {
    const progressBar = toast.querySelector(".progress");
    progressBar.style.animation = `modernToastShrinkProgress ${duration / 1000}s linear forwards`;

    // L'astuce magique : On écoute la fin de l'animation CSS !
    // Si l'utilisateur survole la div, l'animation CSS est en pause,
    // donc cet événement attendra naturellement que la souris quitte la div.
    progressBar.addEventListener("animationend", () => {
      closeModernToast(toast);
    });
  }
}

// Fonction pour fermer proprement une notification
function closeModernToast(toastElement) {
  toastElement.classList.remove("active");
  toastElement.classList.add("closing"); // Animation de sortie

  // Attendre la fin de l'animation CSS (0.4s) pour supprimer du DOM
  setTimeout(() => {
    if (toastElement.parentNode) {
      toastElement.remove();
    }
  }, 400);
}

// ============================================================================
// GLOBAL OVERRIDE FOR TOASTIFY COMPATIBILITY
// ============================================================================
// We override the global Toastify function so we don't need to rewrite
// all the JavaScript code in the application that currently uses it.

(function () {
  // ========== GLOBALS & OVERRIDES ==========

  // Override Toastify
  window.Toastify = function (options) {
    let type = "info"; // Default

    // Determine type from background matching
    if (options.style && options.style.background) {
      if (
        options.style.background.includes("d32f2f") ||
        options.style.background.includes("f44336") ||
        options.style.background.includes("error")
      )
        type = "error";
      else if (
        options.style.background.includes("388e3c") ||
        options.style.background.includes("4caf50") ||
        options.style.background.includes("success")
      )
        type = "success";
      else if (
        options.style.background.includes("f57c00") ||
        options.style.background.includes("ff9800") ||
        options.style.background.includes("warning") ||
        options.style.background.includes(
          "linear-gradient(to right, #f7971e, #ffd200)",
        )
      )
        type = "warning";
    } else if (options.className) {
      if (options.className.includes("error")) type = "error";
      else if (options.className.includes("success")) type = "success";
      else if (options.className.includes("warning")) type = "warning";
    }

    // Extract text, potentially parsing simple HTML or object properties
    let text = options.text || "";
    if (typeof options.node === "object") {
      text =
        options.node.innerText || options.node.textContent || "Notification";
    }

    const duration = options.duration !== undefined ? options.duration : 4000;

    return {
      showToast: function () {
        showModernToast(text, type, duration);
      },
    };
  };

  // Also attach the direct function to window for backward compatibility or direct calls
  window.showToast = showModernToast;
  window.closeToast = closeModernToast;
})();

/**
 * Custom Confirmation Modal to replace native window.confirm()
 *
 * @param {string} title - Title of the modal
 * @param {string} message - Message to display
 * @param {function} onConfirm - Callback when user clicks Confirm
 * @param {function} onCancel - Callback when user clicks Cancel
 */
window.showConfirm = function (title, message, onConfirm, onCancel = null) {
  // Check if overlay already exists, remove it
  let existingOverlay = document.getElementById("custom-confirm-overlay");
  if (existingOverlay) {
    existingOverlay.remove();
  }

  // Create the overlay elements
  const overlay = document.createElement("div");
  overlay.className = "custom-confirm-overlay";
  overlay.id = "custom-confirm-overlay";

  overlay.innerHTML = `
        <div class="custom-confirm-modal">
            <div class="custom-confirm-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" class="warning-icon"><path d="M12 9V14M12 17.5V18M12 3L2 21H22L12 3Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="custom-confirm-title">${title || "Confirmation"}</div>
            <div class="custom-confirm-message">${message || "Êtes-vous sûr de vouloir continuer ?"}</div>
            <div class="custom-confirm-actions">
                <button class="custom-confirm-btn btn-cancel" id="custom-confirm-cancel">Annuler</button>
                <button class="custom-confirm-btn btn-confirm" id="custom-confirm-accept">Confirmer</button>
            </div>
        </div>
    `;

  document.body.appendChild(overlay);

  // Force reflow to enable transition
  requestAnimationFrame(() => {
    overlay.classList.add("show");
  });

  // Close function
  const closeModal = () => {
    overlay.classList.remove("show");
    setTimeout(() => overlay.remove(), 300);
  };

  // Event Listeners
  document
    .getElementById("custom-confirm-cancel")
    .addEventListener("click", () => {
      closeModal();
      if (onCancel) onCancel();
    });

  document
    .getElementById("custom-confirm-accept")
    .addEventListener("click", () => {
      closeModal();
      if (onConfirm) onConfirm();
    });
};

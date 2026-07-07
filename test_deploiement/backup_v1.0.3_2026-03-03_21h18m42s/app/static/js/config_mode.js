/**
 * Logic for Dynamic Permission Configuration Mode
 */

const ConfigMode = {
  active: false,
  selectedElement: null,
  bootstrapModal: null,

  init: function () {
    this.injectStyles();
    this.createModal();
    this.setupEventListeners();

    // Check if config mode was active (persist across reloads?)
    // For now, manual activation via console or UI button
  },

  toggle: function () {
    this.active = !this.active;
    document.body.classList.toggle("config-mode-active", this.active);

    if (this.active) {
      this.refreshVisuals(); // Apply highlights
      Toastify({
        text: "Mode Configuration Activé",
        style: { background: "#450A54" },
      }).showToast();
    } else {
      this.clearVisuals();
      Toastify({
        text: "Mode Configuration Désactivé",
        style: { background: "gray" },
      }).showToast();
    }
  },

  refreshVisuals: function () {
    // Identify all potential targets
    const targets = document.querySelectorAll(
      "button, a, input, select, .btn, .clickable, .card",
    );
    targets.forEach((el) => {
      el.classList.add("selectable-element");
      // Check if PermissionGuard marked it
      if (el.hasAttribute("data-protected-by")) {
        el.setAttribute("data-has-permission", "true");
        el.title = `🔒 Protégé par : ${el.getAttribute("data-protected-by")}`;
      } else {
        el.setAttribute("data-has-permission", "false");
        el.title = "🔓 Non protégé (Cliquez pour configurer)";
      }
    });
  },

  clearVisuals: function () {
    const targets = document.querySelectorAll(".selectable-element");
    targets.forEach((el) => {
      el.classList.remove("selectable-element");
      el.removeAttribute("data-has-permission");
      el.removeAttribute("title");
    });
  },

  injectStyles: function () {
    const style = document.createElement("style");
    style.textContent = `
            .config-mode-active * {
                cursor: crosshair !important;
            }
            .config-mode-active .selectable-element {
                transition: outline 0.2s;
            }
            .config-mode-active .selectable-element:hover {
                outline: 3px solid #450A54 !important;
                position: relative;
                z-index: 1000;
                box-shadow: 0 0 15px rgba(69, 10, 84, 0.5);
            }
            /* Configured = GREEN */
            .config-mode-active .selectable-element[data-has-permission="true"] {
                outline: 2px solid #2ecc71;
                background: rgba(46, 204, 113, 0.05);
            }
            /* Not Configured = RED DASHED */
            .config-mode-active .selectable-element[data-has-permission="false"] {
                outline: 2px dashed #e74c3c;
            }
            /* Visual badge for protected elements */
            .config-mode-active .selectable-element[data-has-permission="true"]::after {
                content: "🔒 " attr(data-protected-by);
                position: absolute;
                top: -5px;
                right: 0;
                font-size: 10px;
                background: #2ecc71;
                color: white;
                border-radius: 12px;
                padding: 4px 8px;
                white-space: nowrap;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                z-index: 5001;
                font-weight: bold;
                pointer-events: none;
            }
            /* Force show hidden elements */
            .config-mode-active [data-hidden-by-guard="true"] {
                display: block !important; /* Try to unhide */
                opacity: 0.5;
                filter: grayscale(100%);
                cursor: not-allowed; /* Visual cue */
            }
            .config-mode-active [data-hidden-by-guard="true"]:hover {
                cursor: crosshair !important;
                opacity: 0.8;
            }
        `;
    document.head.appendChild(style);
  },

  createModal: function () {
    // Modal HTML structure
    const modalHTML = `
        <div class="modal fade" id="permissionConfigModal" tabindex="-1" aria-hidden="true" style="z-index: 10000;">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header bg-primary text-white">
                        <h5 class="modal-title">Configurer Permission UI</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <form id="permConfigForm">
                            <div class="mb-3">
                                <label class="form-label">Page Route</label>
                                <input type="text" class="form-control" id="permConfigRoute" readonly>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Sélecteur Élément</label>
                                <input type="text" class="form-control" id="permConfigSelector" readonly>
                                <small class="text-muted">ID ou Chemin unique</small>
                            </div>
                            <input type="hidden" id="permConfigTargetUrl"> <!-- Hidden field for URL -->
                            <div class="mb-3">
                                <label class="form-label">Privilège Requis</label>
                                <select class="form-select" id="permConfigPrivilege" required>
                                    <option value="">-- Sélectionner --</option>
                                    <!-- Options loaded via AJAX -->
                                </select>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-danger me-auto" id="btnDeletePermission">Supprimer Config</button>
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuler</button>
                        <button type="button" class="btn btn-primary" id="btnSavePermission">Enregistrer</button>
                    </div>
                </div>
            </div>
        </div>`;

    document.body.insertAdjacentHTML("beforeend", modalHTML);
    this.bootstrapModal = new bootstrap.Modal(
      document.getElementById("permissionConfigModal"),
    );

    // Load Privileges List
    fetch("/api/privileges/list")
      .then((r) => r.json())
      .then((list) => {
        const select = document.getElementById("permConfigPrivilege");
        list.forEach((p) => {
          const opt = document.createElement("option");
          opt.value = p;
          opt.textContent = p;
          select.appendChild(opt);
        });
      });

    // Save Action
    document
      .getElementById("btnSavePermission")
      .addEventListener("click", () => this.savePermission());
    document
      .getElementById("btnDeletePermission")
      .addEventListener("click", () => this.deletePermission());
  },

  setupEventListeners: function () {
    // Intercept clicks on ALL elements when active
    document.addEventListener(
      "click",
      (e) => {
        if (!this.active) return;

        // Ignore clicks inside the modal itself
        if (e.target.closest("#permissionConfigModal")) return;

        // Only reliable targets (buttons, links, inputs, cards)
        const target = e.target.closest(
          "button, a, input, select, .btn, .clickable, .card",
        );

        if (target) {
          e.preventDefault();
          e.stopImmediatePropagation();
          this.openConfigModal(target);
        }
      },
      true,
    ); // Use capture phase to intercept early

    // Add visual cues on hover? managed via CSS
  },

  openConfigModal: function (element) {
    this.selectedElement = element;

    // Determine Selector
    let selector = this.getUniqueSelector(element);

    // Determine Page Route (approximate via URL path, ideally injected via backend)
    const pageRoute = window.location.pathname.substring(1) || "index";

    // Detect Target URL if it's a link
    let targetUrl = "";
    if (element.tagName === "A" && element.getAttribute("href")) {
      // Use relative path or full? Use pathname
      try {
        const url = new URL(element.href, window.location.origin);
        targetUrl = url.pathname;
      } catch (e) {}
    }
    // Also support buttons wrapped in forms or with data-url? for now just A tags.

    // Populate Form
    document.getElementById("permConfigRoute").value = pageRoute;
    document.getElementById("permConfigSelector").value = selector;
    document.getElementById("permConfigTargetUrl").value = targetUrl;

    // Pre-select existing config
    const existingPrivilege = element.getAttribute("data-protected-by");
    const select = document.getElementById("permConfigPrivilege");

    if (existingPrivilege) {
      select.value = existingPrivilege;
    } else {
      select.value = "";
    }

    this.bootstrapModal.show();
  },

  getUniqueSelector: function (el) {
    if (el.id) return "#" + el.id;
    // Fallback generator
    let path = [];
    while (el.nodeType === Node.ELEMENT_NODE) {
      let selector = el.nodeName.toLowerCase();
      if (el.id) {
        selector = "#" + el.id;
        path.unshift(selector);
        break;
      } else {
        let sib = el,
          nth = 1;
        while ((sib = sib.previousElementSibling)) {
          if (sib.nodeName.toLowerCase() == selector) nth++;
        }
        if (nth != 1) selector += ":nth-of-type(" + nth + ")";
      }
      path.unshift(selector);
      el = el.parentNode;
      if (el.id === "main-content" || el === document.body) break;
    }
    return path.join(" > ");
  },

  savePermission: function () {
    const route = document.getElementById("permConfigRoute").value;
    const selector = document.getElementById("permConfigSelector").value;
    const privilege = document.getElementById("permConfigPrivilege").value;
    const targetUrl = document.getElementById("permConfigTargetUrl").value;

    fetch("/api/config/dynamic_permissions/ui", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_route: route,
        element_selector: selector,
        privilege_name: privilege,
        target_url: targetUrl, // Send target URL
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          this.bootstrapModal.hide();
          Toastify({
            text: "Permission Enregistrée",
            style: { background: "green" },
          }).showToast();
          // Update UI state immediately?
        } else {
          alert("Erreur: " + data.error);
        }
      });
  },

  deletePermission: function () {
    const route = document.getElementById("permConfigRoute").value;
    const selector = document.getElementById("permConfigSelector").value;

    fetch("/api/config/dynamic_permissions/ui", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_route: route,
        element_selector: selector,
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          this.bootstrapModal.hide();
          Toastify({
            text: "Permission Supprimée",
            style: { background: "orange" },
          }).showToast();
        }
      });
  },
};

// Auto-init on load if user has permission (check server var?)
document.addEventListener("DOMContentLoaded", () => {
  // We can expose it globally to be triggered by a button in layout
  window.ConfigMode = ConfigMode;
  ConfigMode.init();
});

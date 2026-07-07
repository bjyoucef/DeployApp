document.addEventListener("DOMContentLoaded", function () {
  let currentEndpoint = "";

  if (window.current_endpoint) {
    currentEndpoint = window.current_endpoint;
  }

  const btnOpenDoc = document.getElementById("btn-open-doc");
  const docBadge = document.getElementById("doc-badge");
  const docPanel = document.getElementById("docOffcanvasPanel");
  const docBackdrop = document.getElementById("docOffcanvasBackdrop");
  const closeBtn = document.getElementById("closeDocOffcanvasBtn");
  const dragHandle = document.getElementById("docDragHandle");
  const btnEditDoc = document.getElementById("btn-edit-doc");
  const btnCancelEditDoc = document.getElementById("btn-cancel-edit-doc");
  const docViewContainer = document.getElementById("doc-view-container");
  const docEditContainer = document.getElementById("doc-edit-container");
  const docContentDisplay = document.getElementById("doc-content-display");
  const docEmptyState = document.getElementById("doc-empty-state");
  const docLoading = document.getElementById("doc-loading");
  const docForm = document.getElementById("doc-form");

  let docData = null;
  let choicesInstance = null;
  let editorInitialized = false;
  let isDocOpen = false;

  // ━━━ Drag-to-close state ━━━
  let dragStartY = 0;
  let dragCurrentY = 0;
  let isDragging = false;

  // ━━━ Open / Close Logic ━━━
  function openDocOffcanvas() {
    if (!docPanel || !docBackdrop) return;
    isDocOpen = true;
    docPanel.classList.add("active");
    docBackdrop.classList.add("active");
    document.body.style.overflow = "hidden";
    if (closeBtn) closeBtn.focus();
  }

  function closeDocOffcanvas() {
    if (!docPanel || !docBackdrop) return;
    isDocOpen = false;
    docPanel.classList.remove("active");
    docBackdrop.classList.remove("active");
    document.body.style.overflow = "";
  }

  // Expose globally for other scripts
  window.openDocOffcanvas = openDocOffcanvas;
  window.closeDocOffcanvas = closeDocOffcanvas;

  // Close via backdrop click
  if (docBackdrop) {
    docBackdrop.addEventListener("click", closeDocOffcanvas);
  }

  // Close via X button
  if (closeBtn) {
    closeBtn.addEventListener("click", closeDocOffcanvas);
  }

  // Close via Escape key
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && isDocOpen) {
      closeDocOffcanvas();
    }
  });

  // ━━━ Drag-to-Close (Touch + Mouse) ━━━
  if (dragHandle) {
    // Touch events
    dragHandle.addEventListener(
      "touchstart",
      function (e) {
        isDragging = true;
        dragStartY = e.touches[0].clientY;
        docPanel.style.transition = "none";
      },
      { passive: true },
    );

    document.addEventListener(
      "touchmove",
      function (e) {
        if (!isDragging) return;
        dragCurrentY = e.touches[0].clientY;
        const diff = dragCurrentY - dragStartY;
        if (diff > 0) {
          docPanel.style.transform = "translateY(" + diff + "px)";
        }
      },
      { passive: true },
    );

    document.addEventListener("touchend", function () {
      if (!isDragging) return;
      isDragging = false;
      docPanel.style.transition = "";
      docPanel.style.transform = "";
      const diff = dragCurrentY - dragStartY;
      if (diff > 100) {
        closeDocOffcanvas();
      }
      dragStartY = 0;
      dragCurrentY = 0;
    });

    // Mouse events for desktop drag
    dragHandle.addEventListener("mousedown", function (e) {
      isDragging = true;
      dragStartY = e.clientY;
      docPanel.style.transition = "none";
      e.preventDefault();
    });

    document.addEventListener("mousemove", function (e) {
      if (!isDragging) return;
      dragCurrentY = e.clientY;
      const diff = dragCurrentY - dragStartY;
      if (diff > 0) {
        docPanel.style.transform = "translateY(" + diff + "px)";
      }
    });

    document.addEventListener("mouseup", function () {
      if (!isDragging) return;
      isDragging = false;
      docPanel.style.transition = "";
      docPanel.style.transform = "";
      const diff = dragCurrentY - dragStartY;
      if (diff > 100) {
        closeDocOffcanvas();
      }
      dragStartY = 0;
      dragCurrentY = 0;
    });
  }

  // ━━━ Documentation Data Fetch ━━━
  if (currentEndpoint && btnOpenDoc) {
    checkDocumentation(currentEndpoint);
  }

  function checkDocumentation(endpoint) {
    fetch("/api/documentation/" + endpoint)
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        if (data.success && data.data) {
          if (docBadge) docBadge.style.display = "block";
          docData = data.data;
        } else {
          if (docBadge) docBadge.style.display = "none";
          docData = null;
        }
      })
      .catch(function (error) {
        console.error("Error fetching documentation:", error);
      });
  }

  if (btnOpenDoc) {
    btnOpenDoc.addEventListener("click", function () {
      if (!currentEndpoint) {
        Toastify({
          text: "Impossible de déterminer l'interface courante",
          style: { background: "red" },
        }).showToast();
        return;
      }
      openDocView();
      openDocOffcanvas();
    });
  }

  // ━━━ View Mode ━━━
  function openDocView() {
    if (docViewContainer) docViewContainer.style.display = "block";
    if (docEditContainer) docEditContainer.style.display = "none";
    if (btnEditDoc) btnEditDoc.style.display = "inline-block";

    if (docData) {
      if (docEmptyState) docEmptyState.style.display = "none";
      if (docContentDisplay) {
        docContentDisplay.style.display = "block";
        docContentDisplay.innerHTML = docData.content;
      }
      var titleEl = document.getElementById("docOffcanvasLabel");
      if (titleEl) {
        titleEl.innerHTML = '<i class="fas fa-book me-2"></i> ' + docData.titre;
      }
    } else {
      if (docEmptyState) docEmptyState.style.display = "block";
      if (docContentDisplay) docContentDisplay.style.display = "none";
      var titleEl2 = document.getElementById("docOffcanvasLabel");
      if (titleEl2) {
        titleEl2.innerHTML =
          '<i class="fas fa-book me-2"></i> Documentation Contextuelle';
      }
    }
  }

  // ━━━ Edit Mode ━━━
  if (btnEditDoc) {
    btnEditDoc.addEventListener("click", function () {
      enterEditMode();
    });
  }

  if (btnCancelEditDoc) {
    btnCancelEditDoc.addEventListener("click", function () {
      openDocView();
    });
  }

  function initTinyMCE() {
    if (editorInitialized) return;

    tinymce.init({
      selector: "#doc-editor",
      height: 600,
      skin:
        document.documentElement.getAttribute("data-theme") === "dark"
          ? "oxide-dark"
          : "oxide",
      content_css:
        document.documentElement.getAttribute("data-theme") === "dark"
          ? "dark"
          : "default",
      branding: false,
      promotion: false,
      plugins: [
        "advlist",
        "autolink",
        "lists",
        "link",
        "image",
        "charmap",
        "preview",
        "anchor",
        "searchreplace",
        "visualblocks",
        "code",
        "fullscreen",
        "insertdatetime",
        "media",
        "table",
        "help",
        "wordcount",
        "pagebreak",
        "autoresize",
        "directionality",
        "emoticons",
        "hr",
        "nonbreaking",
        "print",
        "template",
        "visualchars",
        "paste",
        "save",
      ],
      toolbar_mode: "floating",
      toolbar:
        "save visualchars fullscreen code preview | undo redo | blocks | bold italic underline backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | link image table emoticons | removeformat | pagebreak",
      images_upload_url: "/api/documentation/upload_image",
      automatic_uploads: true,
      images_reuse_filename: true,
      file_picker_types: "image",
      setup: function (editor) {
        editor.on("change", function () {
          tinymce.triggerSave();
        });
      },
    });
    editorInitialized = true;
  }

  function loadRoutesList(selectedRoutes) {
    var routeSelect = document.getElementById("doc-routes");
    if (choicesInstance) {
      choicesInstance.destroy();
    }

    fetch("/api/documentation/routes")
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        routeSelect.innerHTML = "";
        if (data.success) {
          data.routes.forEach(function (r) {
            var opt = document.createElement("option");
            opt.value = r;
            opt.text = r;
            if (selectedRoutes.includes(r)) {
              opt.setAttribute("selected", "selected");
            }
            routeSelect.appendChild(opt);
          });

          choicesInstance = new Choices(routeSelect, {
            removeItemButton: true,
            searchEnabled: true,
            itemSelectText: "",
            placeholderValue: "Sélectionner des routes...",
          });
        }
      })
      .catch(function (error) {
        console.error("Error loading routes:", error);
      });
  }

  function enterEditMode() {
    if (docViewContainer) docViewContainer.style.display = "none";
    if (docEditContainer) docEditContainer.style.display = "block";
    if (btnEditDoc) btnEditDoc.style.display = "none";

    var titleEl = document.getElementById("docOffcanvasLabel");
    if (titleEl) {
      titleEl.innerHTML =
        '<i class="fas fa-edit me-2"></i> Édition de la documentation';
    }

    var idInput = document.getElementById("doc-id");
    var titreInput = document.getElementById("doc-titre");

    if (typeof tinymce === "undefined") {
      console.error("TinyMCE not loaded");
      return;
    }

    initTinyMCE();

    if (docData) {
      idInput.value = docData.id_doc;
      titreInput.value = docData.titre;
      setTimeout(function () {
        if (tinymce.get("doc-editor"))
          tinymce.get("doc-editor").setContent(docData.content);
      }, 200);
      loadRoutesList(docData.routes || [currentEndpoint]);
    } else {
      idInput.value = "";
      titreInput.value = "Description de l'interface";
      setTimeout(function () {
        if (tinymce.get("doc-editor")) tinymce.get("doc-editor").setContent("");
      }, 200);
      loadRoutesList([currentEndpoint]);
    }
  }

  // ━━━ Save Form ━━━
  if (docForm) {
    docForm.addEventListener("submit", function (e) {
      e.preventDefault();

      tinymce.triggerSave();

      var btnSave = document.getElementById("btn-save-doc");
      var originalText = btnSave.innerHTML;
      btnSave.innerHTML =
        '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Enregistrement...';
      btnSave.disabled = true;

      var formData = {
        id_doc: document.getElementById("doc-id").value,
        titre: document.getElementById("doc-titre").value,
        content: document.getElementById("doc-editor").value,
        routes: choicesInstance ? choicesInstance.getValue(true) : [],
      };

      if (formData.routes.length === 0) {
        Toastify({
          text: "Veuillez sélectionner au moins une route.",
          style: { background: "red" },
        }).showToast();
        btnSave.innerHTML = originalText;
        btnSave.disabled = false;
        return;
      }

      fetch("/api/documentation", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          btnSave.innerHTML = originalText;
          btnSave.disabled = false;

          if (data.success) {
            Toastify({
              text: data.message,
              style: { background: "green" },
            }).showToast();

            // Re-fetch current doc
            checkDocumentation(currentEndpoint);

            setTimeout(function () {
              openDocView();
            }, 500);
          } else {
            Toastify({
              text: data.message || "Erreur lors de l'enregistrement.",
              style: { background: "red" },
            }).showToast();
          }
        })
        .catch(function (error) {
          console.error("Error saving doc:", error);
          btnSave.innerHTML = originalText;
          btnSave.disabled = false;
          Toastify({
            text: "Erreur réseau.",
            style: { background: "red" },
          }).showToast();
        });
    });
  }
});

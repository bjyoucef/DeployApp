/**
 * Runtime Permission Guard
 * Hides elements based on injected configuration.
 */

const PermissionGuard = {
  init: function () {
    // window.uiPermissions is injected in layout.html
    // window.userPrivileges is injected in layout.html (list of strings)

    if (!window.uiPermissions || !window.userPrivileges) return;

    console.log("Applying Permission Guard...", window.uiPermissions);

    window.uiPermissions.forEach((rule) => {
      const selector = rule.selector;
      const requiredPrivilege = rule.privilege;

      // Use querySelectorAll to handle ALL elements matching the selector (IDs or Classes)
      const elements = document.querySelectorAll(selector);

      elements.forEach((element) => {
        // Check if user has privilege
        element.setAttribute("data-protected-by", requiredPrivilege);

        const hasAccess = window.userPrivileges.includes(requiredPrivilege);

        // Find potential fallback elements for this selector
        // We search for elements having data-fallback-for="selector"
        const fallbacks = document.querySelectorAll(
          `[data-fallback-for="${selector}"]`,
        );

        if (!hasAccess) {
          // console.warn(`Hiding element ${selector} (Required: ${requiredPrivilege})`);
          element.style.setProperty("display", "none", "important");
          element.setAttribute("data-hidden-by-guard", "true");

          // Show fallbacks
          fallbacks.forEach((fb) => {
            fb.style.display = ""; // Reset display to default (block/flex/etc)
            fb.setAttribute("data-shown-by-guard", "true");
          });
        } else {
          // Access granted: Ensure element is visible (default)
          // And ensure fallbacks are HIDDEN
          fallbacks.forEach((fb) => {
            fb.style.display = "none";
            fb.setAttribute("data-hidden-by-guard-fallback", "true");
          });
        }
      });
    });

    // 2. Check Route-Based Protections (Links)
    if (window.protectedRoutes) {
      document.querySelectorAll("a[href]").forEach((link) => {
        // Resolve absolute path or relative?
        // href might be full URL or relative.
        // We compare using pathname.
        try {
          const url = new URL(link.href, window.location.origin);
          const path = url.pathname;

          if (window.protectedRoutes.hasOwnProperty(path)) {
            const requiredPrivilege = window.protectedRoutes[path];

            // Mark as protected
            link.setAttribute("data-protected-by", requiredPrivilege);
            link.setAttribute("data-route-protected", "true"); // Helper attr

            const hasAccess = window.userPrivileges.includes(requiredPrivilege);
            if (!hasAccess) {
              console.warn(
                `Hiding link to ${path} (Required: ${requiredPrivilege})`,
              );
              link.style.setProperty("display", "none", "important");
              link.setAttribute("data-hidden-by-guard", "true");
            }
          }
        } catch (e) {
          // Ignore invalid URLs
        }
      });
    }
  },
};

document.addEventListener("DOMContentLoaded", () => {
  PermissionGuard.init();
});

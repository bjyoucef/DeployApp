/**
 * Gestionnaire du modal d'informations médecin
 * Nécessite: jQuery, Bootstrap 5, FontAwesome
 */

const MedecinInfoModal = {
  init: function () {
    // Initialisation si nécessaire
  },

  open: function (id_doctor) {
    const modal = new bootstrap.Modal(
      document.getElementById("modalMedecinInfo"),
    );
    const $content = $("#medecinInfoContent");
    const $loading = $("#medecinInfoLoading");
    const $error = $("#medecinInfoError");

    // Reset display
    $content.hide();
    $error.hide();
    $loading.show();
    modal.show();

    // Fetch Data
    $.ajax({
      url: `/api/get_medecin_full_info/${id_doctor}`,
      method: "GET",
      success: function (response) {
        if (response.success) {
          MedecinInfoModal.populate(response);
          $loading.hide();
          $content.fadeIn();
        } else {
          $loading.hide();
          $error.show();
        }
      },
      error: function () {
        $loading.hide();
        $error.show();
      },
    });
  },

  populate: function (data) {
    const m = data.medecin;
    const s = data.stats;
    const a = data.activity;

    // Basic Info
    $("#infoMedecinName").text(`Dr. ${m.first_name} ${m.last_name}`);
    $("#infoMedecinSpecialty").text(m.name_specialty || "Généraliste");
    $("#infoMedecinPhone").text(m.telephone || "Non renseigné");
    $("#infoMedecinType").html(
      m.est_interne
        ? '<span class="badge bg-info text-dark"><i class="fas fa-hospital-user me-1"></i>Médecin Interne</span>'
        : '<span class="badge bg-success"><i class="fas fa-user-md me-1"></i>Médecin Externe</span>',
    );

    const initials = (m.first_name[0] + m.last_name[0]).toUpperCase();
    $("#infoMedecinInitials").text(initials);

  },
};

// Expose globally
window.MedecinInfoModal = MedecinInfoModal;
window.openMedecinInfoModal = MedecinInfoModal.open;

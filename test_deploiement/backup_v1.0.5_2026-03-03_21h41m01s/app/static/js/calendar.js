document.addEventListener('DOMContentLoaded', function () {
    const calendarEl = document.getElementById('calendar');

    if (!calendarEl) {
        console.error('Élément avec id="calendar" introuvable.');
        return;
    }

    // Récupération des événements depuis Flask
    const events = {{ events | tojson | safe }};
    console.log(events); // Vérifiez les données dans la console

    const selectedEmployee = "{{ selected_employee }}";
    const selectedService = "{{ selected_service }}";
    const selectedShift = "{{ selected_shift }}";

    // Initialisation du calendrier FullCalendar
    const calendar = new FullCalendar.Calendar(calendarEl, {
        locale: 'fr',
        themeSystem: 'bootstrap5',
        initialView: 'dayGridMonth',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay,list'
        },
        editable: true, // Active le glisser-déposer
        weekends: true, // Inclure les week-ends
        dayCellDidMount: function (info) {
            const day = info.date.getDay(); // Récupérer le jour (0 = dimanche, 1 = lundi, etc.)

            if (day === 5) { // Vendredi
                info.el.style.backgroundColor = '#f0e68c'; // Couleur jaune clair
                info.el.style.color = '#000'; // Couleur du texte
            } else if (day === 6) { // Samedi
                info.el.style.backgroundColor = '#ffa07a'; // Couleur saumon
                info.el.style.color = '#fff'; // Couleur du texte
            }
        },
        dayCellDidMount: function (info) {
            const day = info.date.getDay();

            if (day === 5) { // Vendredi
                info.el.classList.add('friday-style');
            } else if (day === 6) { // Samedi
                info.el.classList.add('saturday-style');
            }
        },

        buttonText: {
            today: "Aujourd'hui",
            month: "Mois",
            week: "Semaine",
            day: "Jour",
            list: "Liste"
        },
        events: events, // Charge les événements récupérés
        dateClick: function (info) {
            if (selectedService === "all" || selectedShift === "all" || selectedEmployee === "all") {
                alert("Veuillez sélectionner un service, un employé et un shift.");
            } else {
                openModal(info.dateStr);
            }
        },
        eventDrop: function(info) {
            const eventId = info.event.id;
            const newDate = info.event.start.toISOString().slice(0, 10); // Format YYYY-MM-DD

            // Vérification des valeurs avant la soumission
            console.log('Event ID:', eventId);  // Cela devrait afficher l'ID de l'événement
            console.log('New Date:', newDate);  // Cela devrait afficher la nouvelle date

            // Vérification pour s'assurer que l'ID et la date sont définis
            if (!eventId || !newDate) {
                console.error("L'ID de l'événement ou la date ne sont pas définis.");
                return;
            }

            // Remplir le formulaire avec les données
            document.getElementById('eventId').value = eventId;
            document.getElementById('eventStart').value = newDate;

            // Affichage des valeurs avant soumission pour déboguer
            console.log('Valeur de eventId dans le formulaire:', document.getElementById('eventId').value);
            console.log('Valeur de eventStart dans le formulaire:', document.getElementById('eventStart').value);

            // Soumettre le formulaire
            document.getElementById('updateEventForm').submit();
        },
        eventDblClick: function(info) {
            const eventId = info.event.id;
            const confirmDelete = confirm('Voulez-vous vraiment supprimer cet événement ?');

            if (confirmDelete) {
                // Crée un lien pour envoyer la requête de suppression
                window.location.href = `/delete-event/${eventId}`;
            }
        }
    });

    calendar.render();

    // Fonction pour ouvrir la modal
    function openModal(date) {
        const dateInput = document.getElementById('date');
        if (dateInput) {
            dateInput.value = date;
        } else {
            console.error('Champ "date" introuvable dans le formulaire.');
        }

        const modalEl = document.getElementById('addShiftModal');
        if (modalEl) {
            const modal = new bootstrap.Modal(modalEl);
            modal.show();
        } else {
            console.error('Modal avec id="addShiftModal" introuvable.');
        }
    }
});

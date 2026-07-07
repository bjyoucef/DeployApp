# hospitalisations/models.py
import logging
from decimal import Decimal
from threading import local

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Thread local pour stocker l'utilisateur actuel
_thread_local = local()


def get_current_user():
    """Récupère l'utilisateur actuel depuis le thread local"""
    return getattr(_thread_local, 'user', None)


def set_current_user(user):
    """Définit l'utilisateur actuel dans le thread local"""
    _thread_local.user = user


class TraceableManager(models.Manager):
    """Manager personnalisé pour gérer la traçabilité automatiquement"""

    def create_with_user(self, user, **kwargs):
        """Crée un objet en définissant automatiquement cree_par"""
        if user:
            kwargs['cree_par'] = user
            kwargs['mis_a_jour_par'] = user
        return self.create(**kwargs)


class Chambre(models.Model):
    """Modèle pour les chambres d'hospitalisation"""

    TYPES_CHAMBRE = [
        ("single", "Chambre individuelle"),
        ("double", "Chambre double"),
        ("triple", "Chambre triple"),
        ("quad", "Chambre quadruple"),
        ("vip", "Chambre VIP"),
        ("soins_intensifs", "Soins Intensifs"),
        ("pediatrie", "Chambre Pédiatrie"),
    ]

    service = models.ForeignKey(
        "medical.Service",
        on_delete=models.PROTECT,
        related_name="chambres",
        verbose_name="Service",
    )
    numero_chambre = models.CharField(max_length=10, verbose_name="Numéro de chambre")
    type_chambre = models.CharField(
        max_length=20,
        choices=TYPES_CHAMBRE,
        default="double",
        verbose_name="Type de chambre",
    )

    capacite_lits = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        verbose_name="Nombre de lits",
    )

    prix_nuit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("15000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix par nuitée (DA)",
        help_text="Prix facturé par nuit de séjour (24h)",
    )

    est_active = models.BooleanField(default=True, verbose_name="Actif")

    # Champs de traçabilité
    cree_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chambres_crees",
        verbose_name="Créé par",
    )
    cree_le = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    mis_a_jour_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chambres_mis_a_jour",
        verbose_name="Mis à jour par",
    )
    mis_a_jour_le = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    objects = TraceableManager()

    class Meta:
        ordering = ["service__name", "numero_chambre"]
        unique_together = ["service", "numero_chambre"]
        verbose_name = "Chambre"
        verbose_name_plural = "Chambres"
        indexes = [models.Index(fields=["service"])]

    def __str__(self):
        return f"Chambre {self.numero_chambre} - {self.service.name}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        current_user = get_current_user()

        # Définir cree_par lors de la création
        if is_new and current_user and not self.cree_par:
            self.cree_par = current_user

        # Toujours mettre à jour mis_a_jour_par
        if current_user:
            self.mis_a_jour_par = current_user

        super().save(*args, **kwargs)

    def mark_updated_by(self, user, save=True):
        """Marque l'objet comme mis à jour par user"""
        if user:
            self.mis_a_jour_par = user
        self.mis_a_jour_le = timezone.now()
        if save:
            try:
                self.save(update_fields=["mis_a_jour_par", "mis_a_jour_le"])
            except Exception:
                self.save()

    @property
    def nombre_lits_occupes(self) -> int:
        return self.lits.filter(est_active=True, est_occupe=True).count()

    @property
    def nombre_lits_disponibles(self) -> int:
        return max(0, self.capacite_lits - self.nombre_lits_occupes)

    @property
    def est_complete(self) -> bool:
        return self.nombre_lits_occupes >= self.capacite_lits


class Lit(models.Model):
    """Modèle pour les lits"""

    chambre = models.ForeignKey(
        Chambre, on_delete=models.CASCADE, related_name="lits", verbose_name="Chambre"
    )
    numero_lit = models.CharField(max_length=10, verbose_name="Numéro de lit")
    est_occupe = models.BooleanField(default=False, verbose_name="Occupé")
    est_active = models.BooleanField(default=True, verbose_name="Actif")

    # Champs de traçabilité
    cree_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lits_crees",
        verbose_name="Créé par",
    )
    cree_le = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    mis_a_jour_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lits_mis_a_jour",
        verbose_name="Mis à jour par",
    )
    mis_a_jour_le = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    objects = TraceableManager()

    class Meta:
        ordering = ["chambre", "numero_lit"]
        unique_together = ["chambre", "numero_lit"]
        verbose_name = "Lit"
        verbose_name_plural = "Lits"
        indexes = [models.Index(fields=["chambre", "est_occupe"])]

    def __str__(self):
        return f"Lit {self.numero_lit} - Chambre {self.chambre.numero_chambre}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        current_user = get_current_user()

        if is_new and current_user and not self.cree_par:
            self.cree_par = current_user

        if current_user:
            self.mis_a_jour_par = current_user

        super().save(*args, **kwargs)

    def mark_updated_by(self, user, save=True):
        if user:
            self.mis_a_jour_par = user
        self.mis_a_jour_le = timezone.now()
        if save:
            try:
                self.save(update_fields=["mis_a_jour_par", "mis_a_jour_le"])
            except Exception:
                self.save()

    @property
    def patient_actuel(self):
        if not self.est_occupe:
            return None
        attribution = self.attributions_lits.filter(est_courante=True).first()
        return attribution.admission.patient if attribution else None

    @property
    def statut_affichage(self):
        return "Occupé" if self.est_occupe else "Disponible"


class DemandeAdmission(models.Model):
    """Demande d'admission en attente"""

    STATUTS = [
        ("waiting", "En attente"),
        ("admitted", "Admis"),
        ("cancelled", "Annulé"),
        ("transferred", "Transféré"),
    ]

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="demandes_admissions",
        verbose_name="Patient",
    )
    service = models.ForeignKey(
        "medical.Service",
        on_delete=models.PROTECT,
        related_name="demandes_admissions",
        verbose_name="Service demandé",
    )
    medecin_referent = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="references",
        verbose_name="Médecin référent",
    )

    statut = models.CharField(
        max_length=20, choices=STATUTS, default="waiting", verbose_name="Statut"
    )
    motif = models.TextField(verbose_name="Motif d'admission", blank=True)

    date_demande = models.DateTimeField(
        default=timezone.now, verbose_name="Date de demande"
    )
    duree_estimee = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Durée estimée (jours)"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    admission_source = models.ForeignKey(
        "Admission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_transfert",
        verbose_name="Admission source (pour transferts)",
    )

    # Champs de traçabilité
    cree_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_admissions_crees",
        verbose_name="Créé par",
    )
    cree_le = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    mis_a_jour_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_admissions_mis_a_jour",
        verbose_name="Mis à jour par",
    )
    mis_a_jour_le = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    objects = TraceableManager()

    class Meta:
        ordering = ["-date_demande"]
        verbose_name = "Demande d'admission"
        verbose_name_plural = "Demandes d'admission"
        indexes = [models.Index(fields=["statut"])]

    def __str__(self):
        return f"Demande pour {self.patient.nom_complet} - {self.service.name} ({self.statut})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        current_user = get_current_user()

        if is_new and current_user and not self.cree_par:
            self.cree_par = current_user

        if current_user:
            self.mis_a_jour_par = current_user

        super().save(*args, **kwargs)

    def mark_updated_by(self, user, save=True):
        if user:
            self.mis_a_jour_par = user
        self.mis_a_jour_le = timezone.now()
        if save:
            self.save()

    def mark_admitted(self, user=None):
        self.statut = "admitted"
        if user:
            self.mark_updated_by(user)
        self.save(update_fields=["statut"])


class Admission(models.Model):
    """Modèle pour les admissions hospitalières avec support des séjours courts"""

    STATUTS = [
        ("active", "Actif"),
        ("discharged", "Sorti"),
        ("transferred", "Transféré"),
        ("cancelled", "Annulé"),
    ]

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="admissions",
        verbose_name="Patient",
    )
    demande_admission = models.ForeignKey(
        "DemandeAdmission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admissions",
        verbose_name="Demande d'admission",
    )
    medecin_traitant = models.ForeignKey(
        "medecin.Medecin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Médecin traitant",
    )
    date_admission = models.DateTimeField(
        default=timezone.now, verbose_name="Date d'admission"
    )
    date_sortie = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de sortie"
    )
    statut = models.CharField(
        max_length=20, choices=STATUTS, default="active", verbose_name="Statut"
    )
    cout_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Coût total",
    )
    notes_sortie = models.TextField(blank=True, verbose_name="Notes de sortie")
    est_active = models.BooleanField(default=True, verbose_name="Actif")

    # Champs de traçabilité
    cree_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admissions_crees",
        verbose_name="Créé par",
    )
    cree_le = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    mis_a_jour_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admissions_mis_a_jour",
        verbose_name="Mis à jour par",
    )
    mis_a_jour_le = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    objects = TraceableManager()

    class Meta:
        ordering = ["-date_admission"]
        verbose_name = "Admission"
        verbose_name_plural = "Admissions"
        indexes = [models.Index(fields=["patient", "statut"])]

    def __str__(self):
        return f"Admission de {self.patient.nom_complet} - {self.date_admission.strftime('%d/%m/%Y %H:%M')}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        current_user = get_current_user()

        if is_new and current_user and not self.cree_par:
            self.cree_par = current_user

        if current_user:
            self.mis_a_jour_par = current_user

        super().save(*args, **kwargs)

    def mark_updated_by(self, user, save=True):
        if user:
            self.mis_a_jour_par = user
        self.mis_a_jour_le = timezone.now()
        if save:
            try:
                self.save(update_fields=["mis_a_jour_par", "mis_a_jour_le"])
            except Exception:
                self.save()

    @property
    def duree_sejour_heures(self) -> float:
        """Durée totale du séjour en heures"""
        end_date = self.date_sortie or timezone.now()
        delta = end_date - self.date_admission
        return delta.total_seconds() / 3600

    @property
    def duree_sejour(self) -> int:
        """Durée totale du séjour en jours (pour compatibilité)"""
        return max(
            1,
            int(self.duree_sejour_heures / 24)
            + (1 if self.duree_sejour_heures % 24 > 0 else 0),
        )

    @property
    def lit_actuel(self):
        attribution = self.attributions_lits.filter(est_courante=True).first()
        return attribution.lit if attribution else None

    @property
    def service_actuel(self):
        lit = self.lit_actuel
        if lit:
            return lit.chambre.service
        last_transfer = self.transferts.order_by("-date_transfert").first()
        if last_transfer:
            if last_transfer.to_assignment and last_transfer.to_assignment.lit:
                return last_transfer.to_assignment.lit.chambre.service
            if getattr(last_transfer, "to_service", None):
                return last_transfer.to_service
        return None

    def calculer_cout_total(self) -> Decimal:
        """Calcul précis basé sur chaque période de séjour avec gestion des séjours courts"""
        total = Decimal("0.00")

        for attribution in self.attributions_lits.all():
            if attribution.cout is not None:
                # Si le coût est déjà calculé et finalisé
                total += attribution.cout
            else:
                # Si l'attribution est encore en cours, calculer le coût actuel
                cout_attribution = attribution.calculer_cout()
                total += cout_attribution

        return total

    def get_resume_facturation(self) -> dict:
        """Retourne un résumé de la facturation avec détails des séjours courts"""
        total = self.calculer_cout_total()
        attributions = self.attributions_lits.all().order_by("date_debut")

        sejours_courts = []
        sejours_normaux = []

        for attr in attributions:
            details = attr.get_facturation_details()
            if attr.est_sejour_court:
                sejours_courts.append(details)
            else:
                sejours_normaux.append(details)

        return {
            'cout_total': float(total),
            'duree_totale_heures': round(self.duree_sejour_heures, 2),
            'duree_totale_jours': self.duree_sejour,
            'nombre_sejours_courts': len(sejours_courts),
            'nombre_sejours_normaux': len(sejours_normaux),
            'sejours_courts': sejours_courts,
            'sejours_normaux': sejours_normaux,
            'attributions_details': [attr.get_facturation_details() for attr in attributions]
        }

    def obtenir_parcours_detaille_avec_couts(self):
        """Retourne le parcours complet avec détail des coûts par période"""
        parcours = []
        total_cumule = Decimal("0.00")

        for attribution in self.attributions_lits.all().order_by("date_debut"):
            cout_periode = attribution.calculer_cout()
            total_cumule += cout_periode

            parcours.append({
                'attribution': attribution,
                'lit': attribution.lit,
                'chambre': attribution.lit.chambre,
                'service': attribution.lit.chambre.service,
                'date_debut': attribution.date_debut,
                'date_fin': attribution.date_fin,
                'duree_jours': attribution.duree_jours,
                'prix_nuit': attribution.prix_nuit,
                'cout_periode': cout_periode,
                'total_cumule': total_cumule,
                'est_courante': attribution.est_courante,
            })

        return parcours

    @transaction.atomic
    def admit_to_lit(self, lit, cree_par=None, note: str = ""):
        """Admet (ou transfère) le patient dans un lit donné"""
        if not lit.est_active:
            raise ValueError("Le lit sélectionné n'est pas actif")
        if lit.est_occupe:
            raise ValueError("Le lit est déjà occupé")

        now = timezone.now()

        # Fermer attribution courante avec calcul précis du coût
        current = self.attributions_lits.filter(est_courante=True).first()
        if current:
            current.date_fin = now
            current.est_courante = False
            # CORRECTION: Calculer le coût basé sur la période réelle dans ce lit
            current.cout = current.calculer_cout()
            if cree_par:
                current.mis_a_jour_par = cree_par
            current.save(update_fields=["date_fin", "est_courante", "cout", "mis_a_jour_par"])

            # Libérer ancien lit
            current.lit.est_occupe = False
            current.lit.save(update_fields=["est_occupe"])

        # Occuper nouveau lit
        lit.est_occupe = True
        lit.save(update_fields=["est_occupe"])

        # Créer nouvelle attribution avec prix du nouveau lit
        attribution = AttributionLit.objects.create(
            admission=self,
            lit=lit,
            date_debut=now,
            est_courante=True,
            created_by=cree_par,
            notes=note,
            cree_par=cree_par,
            mis_a_jour_par=cree_par,
        )

        # Marquer la demande comme admise si nécessaire
        if self.demande_admission and self.demande_admission.statut == "waiting":
            self.demande_admission.mark_admitted(cree_par)

        # Recalculer coût total avec les nouvelles données
        self.cout_total = self.calculer_cout_total()
        if cree_par:
            self.mis_a_jour_par = cree_par
        self.save(update_fields=["cout_total", "mis_a_jour_par"])

        return attribution

    @transaction.atomic
    def discharge(
            self, date_sortie: timezone.datetime = None, discharged_by=None, notes: str = ""
    ) -> Decimal:
        """Effectue la sortie du patient avec calcul final précis"""
        when = date_sortie or timezone.now()
        self.date_sortie = when
        self.statut = "discharged"
        self.est_active = False
        if notes:
            self.notes_sortie = (self.notes_sortie or "") + "\n" + notes

        current = self.attributions_lits.filter(est_courante=True).first()
        if current:
            current.date_fin = when
            current.est_courante = False
            # CORRECTION: Calcul final précis jusqu'à la date de sortie
            current.cout = current.calculer_cout()
            if discharged_by:
                current.mis_a_jour_par = discharged_by
            current.save(update_fields=["date_fin", "est_courante", "cout", "mis_a_jour_par"])

            # Libérer le lit
            current.lit.est_occupe = False
            current.lit.save(update_fields=["est_occupe"])

            # Historiser
            StayHistory.objects.create(
                patient=self.patient,
                admission=self,
                bed=current.lit,
                start_date=current.date_debut,
                end_date=current.date_fin,
                cost=current.cout or Decimal("0.00"),
                notes=current.notes or "Sortie",
                cree_par=discharged_by,
                mis_a_jour_par=discharged_by,
            )

        # Recalculer coût total final
        self.cout_total = self.calculer_cout_total()
        if discharged_by:
            self.mis_a_jour_par = discharged_by
        self.save(
            update_fields=[
                "date_sortie",
                "statut",
                "est_active",
                "cout_total",
                "notes_sortie",
                "mis_a_jour_par",
            ]
        )

        return self.cout_total

    def get_movement_timeline(self):
        """Retourne une timeline chronologique de tous les mouvements du patient"""
        timeline = []

        # Ajouter l'admission initiale
        timeline.append(
            {
                "type": "admission",
                "date": self.date_admission,
                "description": "Admission initiale",
                "details": f"Admis par {self.cree_par.nom_complet if self.cree_par else 'Non spécifié'}",
            }
        )

        # Ajouter toutes les attributions de lits
        for attribution in self.attributions_lits.all().order_by("date_debut"):
            timeline.append(
                {
                    "type": "bed_assignment",
                    "date": attribution.date_debut,
                    "description": f"Assigné au lit {attribution.lit.numero_lit}",
                    "details": f"Chambre {attribution.lit.chambre.numero_chambre} - Service {attribution.lit.chambre.service.name}",
                    "cost": attribution.cout,
                    "end_date": attribution.date_fin,
                }
            )

        # Ajouter tous les transferts
        for transfert in self.transferts.all().order_by("date_transfert"):
            timeline.append(
                {
                    "type": "transfer",
                    "date": transfert.date_transfert,
                    "description": f"Transfert {transfert.get_type_display() if hasattr(transfert, 'get_type_display') else ''}",
                    "details": f"De {transfert.from_service.name if transfert.from_service else 'N/A'} vers {transfert.to_service.name if transfert.to_service else 'N/A'}",
                    "reason": transfert.motif,
                    "notes": transfert.notes,
                    "transferred_by": (
                        transfert.transfere_par.nom_complet
                        if transfert.transfere_par
                        else "Non spécifié"
                    ),
                }
            )

        # Ajouter la sortie si elle existe
        if self.date_sortie:
            timeline.append(
                {
                    "type": "discharge",
                    "date": self.date_sortie,
                    "description": "Sortie",
                    "details": f"Statut: {self.get_statut_display()}",
                    "notes": self.notes_sortie,
                }
            )

        # Trier par date
        timeline.sort(key=lambda x: x["date"])

        return timeline


class AttributionLit(models.Model):
    """Attribution d'un lit pour une période spécifique avec prix fixé"""

    admission = models.ForeignKey(
        "Admission",
        on_delete=models.CASCADE,
        related_name="attributions_lits",
        verbose_name="Admission",
    )
    lit = models.ForeignKey(
        "Lit",
        on_delete=models.PROTECT,
        related_name="attributions_lits",
        verbose_name="Lit",
    )

    date_debut = models.DateTimeField(
        default=timezone.now, verbose_name="Date de début"
    )
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name="Date de fin")

    # Prix fixé au moment de l'attribution
    prix_nuit_applique = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prix/nuit appliqué",
        help_text="Prix de la chambre au moment de l'attribution"
    )

    # NOUVEAU: Tarifs du service fixés au moment de l'attribution
    tarif_fixe_service = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Tarif fixe du service",
        help_text="Tarif fixe du service au moment de l'attribution (pour séjours courts)"
    )

    seuil_sejour_court = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Seuil séjour court (heures)",
        help_text="Seuil en heures fixé au moment de l'attribution"
    )

    cout = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        null=True,
        blank=True,
        verbose_name="Coût du séjour dans ce lit",
    )

    est_courante = models.BooleanField(
        default=True, verbose_name="Attribution courante"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    # Traçabilité directe
    created_by = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attributions_created_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attributions_crees",
        verbose_name="Créé par",
    )
    cree_le = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    mis_a_jour_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attributions_mis_a_jour",
        verbose_name="Mis à jour par",
    )
    mis_a_jour_le = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    objects = TraceableManager()

    class Meta:
        ordering = ["date_debut"]
        verbose_name = "Attribution de lit"
        verbose_name_plural = "Attributions de lits"
        indexes = [models.Index(fields=["admission", "est_courante"])]

    def __str__(self):
        return f"Attribution pour {self.admission.patient.nom_complet} - Lit {self.lit.numero_lit} ({self.date_debut.strftime('%d/%m/%Y %H:%M')})"

    @property
    def duree_heures(self) -> float:
        """Durée en heures pour cette attribution spécifique"""
        end_date = self.date_fin or timezone.now()
        delta = end_date - self.date_debut
        return delta.total_seconds() / 3600  # Convertir en heures

    @property
    def duree_jours(self) -> int:
        """Durée en jours (pour compatibilité)"""
        return max(1, int(self.duree_heures / 24) + (1 if self.duree_heures % 24 > 0 else 0))

    @property
    def prix_nuit(self) -> Decimal:
        """Utilise le prix fixé ou le prix actuel de la chambre"""
        if self.prix_nuit_applique is not None:
            return self.prix_nuit_applique
        return self.lit.chambre.prix_nuit or Decimal("0.00")

    @property
    def est_sejour_court(self) -> bool:
        """Détermine si c'est un séjour court"""
        seuil = self.seuil_sejour_court or 24
        return self.duree_heures < seuil

    def calculer_cout(self) -> Decimal:
        """
        Calcul du coût selon la durée :
        - Séjour court : tarif_fixe + ((prix_nuit - tarif_fixe) / 24h) * duree_heures
        - Séjour normal : prix_nuit * nombre_jours
        """
        duree_h = self.duree_heures
        prix_nuit = self.prix_nuit

        # Récupérer les tarifs du service (fixés au moment de l'attribution)
        tarif_fixe = self.tarif_fixe_service or Decimal("7000.00")  # Valeur par défaut
        seuil = self.seuil_sejour_court or 24

        if duree_h < seuil:
            # Séjour court - Application de la formule spéciale
            tarif_variable = prix_nuit - tarif_fixe
            cout_variable = (tarif_variable / Decimal(str(seuil))) * Decimal(str(duree_h))
            cout_total = tarif_fixe + cout_variable

            # S'assurer que le coût n'est jamais négatif
            return max(Decimal("0.00"), cout_total)
        else:
            # Séjour normal - Facturation par nuitées complètes
            return Decimal(self.duree_jours) * prix_nuit

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        current_user = get_current_user()

        if is_new:
            # Fixer les prix au moment de la création
            if self.prix_nuit_applique is None:
                self.prix_nuit_applique = self.lit.chambre.prix_nuit

            # Fixer les tarifs du service
            service = self.lit.chambre.service
            if self.tarif_fixe_service is None:
                self.tarif_fixe_service = getattr(service, 'tarif_fixe_sejour_court', Decimal("7000.00"))
            if self.seuil_sejour_court is None:
                self.seuil_sejour_court = getattr(service, 'seuil_sejour_court_heures', 24)

            # Traçabilité pour création
            if current_user and not self.cree_par:
                self.cree_par = current_user
            if not self.created_by and self.cree_par:
                self.created_by = self.cree_par

        # Traçabilité pour modification
        if current_user:
            self.mis_a_jour_par = current_user

        # Fermer autres attributions courantes
        if self.est_courante:
            AttributionLit.objects.filter(
                admission=self.admission, est_courante=True
            ).exclude(pk=self.pk).update(est_courante=False, date_fin=self.date_debut)

        super().save(*args, **kwargs)

        # Occuper le lit si nouveau
        if is_new:
            if not self.lit.est_active:
                raise ValueError("Impossible d'attribuer un lit inactif")
            self.lit.est_occupe = True
            self.lit.save(update_fields=["est_occupe"])

    def get_facturation_details(self) -> dict:
        """Retourne les détails de facturation pour cette attribution"""
        duree_h = self.duree_heures
        prix_nuit = self.prix_nuit
        tarif_fixe = self.tarif_fixe_service or Decimal("7000.00")
        seuil = self.seuil_sejour_court or 24

        details = {
            'duree_heures': round(duree_h, 2),
            'duree_jours': self.duree_jours,
            'prix_nuit_applique': float(prix_nuit),
            'tarif_fixe_service': float(tarif_fixe),
            'seuil_sejour_court': seuil,
            'est_sejour_court': self.est_sejour_court,
            'cout_total': float(self.calculer_cout())
        }

        if self.est_sejour_court:
            tarif_variable = prix_nuit - tarif_fixe
            cout_variable = (tarif_variable / Decimal(str(seuil))) * Decimal(str(duree_h))

            details.update({
                'mode_facturation': 'sejour_court',
                'tarif_variable_base': float(tarif_variable),
                'tarif_horaire': float(tarif_variable / Decimal(str(seuil))),
                'cout_variable': float(cout_variable),
                'formule': f"{float(tarif_fixe)} + ({float(tarif_variable)} / {seuil}h) × {round(duree_h, 2)}h"
            })
        else:
            details.update({
                'mode_facturation': 'sejour_normal',
                'formule': f"{self.duree_jours} jour(s) × {float(prix_nuit)} DA/nuit"
            })

        return details

    @transaction.atomic
    def close_and_save(self, end_date: timezone.datetime = None, mis_a_jour_par=None):
        """Ferme l'attribution avec calcul final précis"""
        when = end_date or timezone.now()
        self.date_fin = when
        self.est_courante = False
        self.cout = self.calculer_cout()
        if mis_a_jour_par:
            self.mis_a_jour_par = mis_a_jour_par
        self.save(
            update_fields=[
                "date_fin",
                "est_courante",
                "cout",
                "mis_a_jour_par",
                "mis_a_jour_le",
            ]
        )

        # Libérer lit
        self.lit.est_occupe = False
        self.lit.save(update_fields=["est_occupe"])

        # Historiser
        StayHistory.objects.create(
            patient=self.admission.patient,
            admission=self.admission,
            bed=self.lit,
            start_date=self.date_debut,
            end_date=self.date_fin,
            cost=self.cout or Decimal("0.00"),
            notes=self.notes or "Clôture d'attribution",
            cree_par=mis_a_jour_par,
        )


class Transfert(models.Model):
    """Modèle pour les transferts entre lits/services"""

    admission = models.ForeignKey(
        Admission,
        on_delete=models.CASCADE,
        related_name="transferts",
        verbose_name="Admission",
    )
    from_assignment = models.ForeignKey(
        AttributionLit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_from",
    )
    to_assignment = models.ForeignKey(
        AttributionLit,
        on_delete=models.CASCADE,
        related_name="transfer_to",
        null=True,
        blank=True,
    )
    from_service = models.ForeignKey(
        "medical.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferts_depuis",
        verbose_name="Service source",
    )
    to_service = models.ForeignKey(
        "medical.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferts_vers",
        verbose_name="Service destination",
    )
    date_transfert = models.DateTimeField(
        default=timezone.now, verbose_name="Date de transfert"
    )

    transfere_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Transféré par",
    )
    motif = models.TextField(blank=True, verbose_name="Motif du transfert")
    notes = models.TextField(blank=True, verbose_name="Notes")

    # Traçabilité
    cree_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferts_crees",
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    mis_a_jour_par = models.ForeignKey(
        "rh.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferts_mis_a_jour",
    )
    mis_a_jour_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_transfert"]
        verbose_name = "Transfert"
        verbose_name_plural = "Transferts"
        indexes = [models.Index(fields=["admission", "date_transfert"])]

    def __str__(self):
        return f"Transfert de {self.admission.patient.nom_complet} le {self.date_transfert.strftime('%d/%m/%Y')}"

    @property
    def difference_cout_nuitee(self) -> Decimal:
        """CORRECTION: Différence de prix/nuit entre ancien et nouveau lit"""
        old_price = Decimal("0.00")
        new_price = Decimal("0.00")

        if (self.from_assignment and self.from_assignment.lit and
                self.from_assignment.lit.chambre):
            old_price = self.from_assignment.prix_nuit

        if (self.to_assignment and self.to_assignment.lit and
                self.to_assignment.lit.chambre):
            new_price = self.to_assignment.prix_nuit

        return new_price - old_price

    def get_impact_financier_description(self) -> str:
        """Description de l'impact financier du transfert"""
        diff = self.difference_cout_nuitee
        if diff > 0:
            return f"Augmentation de {diff} DA/nuit"
        elif diff < 0:
            return f"Économie de {abs(diff)} DA/nuit"
        else:
            return "Aucun impact sur le prix/nuit"


class StayHistory(models.Model):
    """Historique détaillé des séjours pour la traçabilité"""

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="historique_sejours"
    )
    admission = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name="historique_sejours"
    )
    bed = models.ForeignKey(Lit, on_delete=models.CASCADE)

    start_date = models.DateTimeField(verbose_name="Date début")
    end_date = models.DateTimeField(null=True, blank=True, verbose_name="Date fin")
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)

    # AJOUT: Prix appliqué durant cette période pour l'historique
    prix_nuit_periode = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prix/nuit durant cette période"
    )

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Historique de séjour"
        verbose_name_plural = "Historiques de séjour"

    def __str__(self):
        return f"{self.patient.nom_complet} - Lit {self.bed.numero_lit} ({self.start_date.strftime('%d/%m/%Y')})"

    @property
    def duree_periode(self) -> int:
        """Durée de cette période spécifique"""
        end = self.end_date or timezone.now()
        delta = (end.date() - self.start_date.date()).days
        return max(1, delta + 1)

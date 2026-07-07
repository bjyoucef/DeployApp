import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from medecin.models import Medecin
from medical.models import Service
from patients.models import Patient
from rh.models import Personnel
from .models import (
    Admission,
    DemandeAdmission,
    Lit,
    Chambre,
    StayHistory,
    AttributionLit,
    Transfert
)


@login_required
def floor_plan_centralized(request, service_id):
    """Vue centralisée pour le plan d'étage avec toutes les fonctionnalités"""
    service = get_object_or_404(Service, id=service_id)

    # Récupérer toutes les chambres du service avec leurs lits
    rooms = (
        Chambre.objects.filter(service=service, est_active=True)
        .prefetch_related(
            Prefetch(
                "lits",
                queryset=Lit.objects.filter(est_active=True).prefetch_related(
                    Prefetch(
                        "attributions_lits",
                        queryset=AttributionLit.objects.filter(
                            est_courante=True
                        ).select_related("admission__patient"),
                        to_attr="current_attributions",
                    )
                ),
            )
        )
        .order_by("numero_chambre")
    )

    # Enrichir les lits avec les informations nécessaires
    for room in rooms:
        for bed in room.lits.all():
            if hasattr(bed, "current_attributions") and bed.current_attributions:
                # Il y a une attribution courante
                attribution = bed.current_attributions[0]
                bed.current_admission_id = attribution.admission.id
                bed.current_patient = attribution.admission.patient
            else:
                bed.current_admission_id = None
                bed.current_patient = None

    # Récupérer les demandes d'admission en attente pour ce service
    waiting_requests = (
        DemandeAdmission.objects.filter(service=service, statut="waiting")
        .select_related("patient", "medecin_referent", "admission_source")
        .order_by("date_demande")
    )

    # CORRECTION : Changer le nom de la variable de boucle
    for admission_request in waiting_requests:
        if admission_request.admission_source:
            # C'est un transfert - récupérer les détails de l'admission source
            try:
                source_admission = admission_request.admission_source
                # Obtenir le service actuel ou précédent
                current_bed = source_admission.lit_actuel
                if current_bed:
                    admission_request.source_service_name = (
                        current_bed.chambre.service.name
                    )
                    admission_request.source_bed_info = f"Lit {current_bed.numero_lit} - Chambre {current_bed.chambre.numero_chambre}"
                else:
                    # Patient déjà libéré, chercher dans l'historique
                    last_attribution = source_admission.attributions_lits.order_by(
                        "-date_fin"
                    ).first()
                    if last_attribution:
                        admission_request.source_service_name = (
                            last_attribution.lit.chambre.service.name
                        )
                        admission_request.source_bed_info = (
                            f"Anciennement lit {last_attribution.lit.numero_lit}"
                        )
                    else:
                        admission_request.source_service_name = "Service précédent"
                        admission_request.source_bed_info = "Information non disponible"
            except Exception as e:
                print(
                    f"Erreur lors de l'enrichissement de la demande {admission_request.id}: {e}"
                )
                admission_request.source_service_name = "Service inconnu"
                admission_request.source_bed_info = "Information non disponible"

    # Récupérer toutes les demandes d'admission pour le modal
    all_admission_requests = (
        DemandeAdmission.objects.filter(service=service)
        .select_related("patient", "medecin_referent", "cree_par", "admission_source")
        .order_by("-date_demande")[:100]
    )

    # Récupérer les admissions actuelles du service
    current_admissions = (
        Admission.objects.filter(
            attributions_lits__lit__chambre__service=service,
            est_active=True,
            date_sortie__isnull=True,
            attributions_lits__est_courante=True,
        )
        .select_related("patient", "medecin_traitant")
        .prefetch_related(
            Prefetch(
                "attributions_lits",
                queryset=AttributionLit.objects.filter(
                    est_courante=True
                ).select_related("lit__chambre"),
            )
        )
        .distinct()
        .order_by("date_admission")
    )

    # Calculer la durée de séjour et le coût avec la nouvelle logique
    for admission in current_admissions:
        admission.length_of_stay_days = admission.duree_sejour
        # CORRECTION: Utiliser la méthode corrigée
        admission.estimated_cost = admission.calculer_cout_total()

    # CORRECTION: Historique avec calculs précis
    admission_history = (
        Admission.objects.filter(
            Q(attributions_lits__lit__chambre__service=service)
            | Q(transferts__from_service=service)
            | Q(transferts__to_service=service)
        )
        .select_related("patient", "medecin_traitant")
        .distinct()
        .order_by("-date_admission")[:50]
    )

    # Calculer les coûts pour l'historique avec la nouvelle méthode
    total_revenue = Decimal("0.00")
    total_stays_days = 0
    for admission in admission_history:
        admission.length_of_stay_days = admission.duree_sejour
        # CORRECTION: Utiliser la méthode corrigée
        admission.calculated_total_cost = admission.calculer_cout_total()
        total_revenue += admission.calculated_total_cost
        total_stays_days += admission.duree_sejour

    # Calculer la durée moyenne de séjour
    average_stay = total_stays_days / len(admission_history) if admission_history else 0

    # Calculer les statistiques globales
    all_beds = Lit.objects.filter(chambre__service=service, est_active=True)
    total_beds = all_beds.count()
    occupied_beds = all_beds.filter(est_occupe=True).count()
    available_beds = total_beds - occupied_beds

    occupancy_rate = (
        round((occupied_beds / total_beds) * 100, 1) if total_beds > 0 else 0
    )

    stats = {
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "available_beds": available_beds,
        "occupancy_rate": occupancy_rate,
    }

    # Récupérer les données pour les formulaires
    patients = Patient.objects.filter(est_active=True).order_by(
        "last_name", "first_name"
    )[:100]
    services = Service.objects.filter(est_hospitalier=True).order_by("name")
    doctors = Medecin.objects.all()[:50]

    context = {
        "service": service,
        "rooms": rooms,
        "waiting_requests": waiting_requests,
        "admission_requests": all_admission_requests,
        "current_admissions": current_admissions,
        "admission_history": admission_history,
        "total_revenue": total_revenue,
        "average_stay": round(average_stay, 1),
        "stats": stats,
        "patients": patients,
        "services": services,
        "doctors": doctors,
    }

    return render(request, "hospitalisation/floor_plan.html", context)


@login_required
def add_admission_request(request):
    """Créer une nouvelle demande d'admission"""
    """Créer une nouvelle demande d'admission - VERSION CORRIGÉE"""
    if request.method == "POST":
        try:
            patient_id = request.POST.get("patient_id")
            service_id = request.POST.get("service_id")
            medecin_referent_id = request.POST.get("medecin_referent_id")
            motif = request.POST.get("motif")
            duree_estimee = request.POST.get("duree_estimee")
            notes = request.POST.get("notes", "")

            # Validation des champs obligatoires
            if not all([patient_id, service_id, motif]):
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Patient, service et motif sont obligatoires",
                    }
                )

            patient = get_object_or_404(Patient, id=patient_id)
            service = get_object_or_404(Service, id=service_id)

            # CORRECTION : Vérification plus précise des doublons
            # Chercher une demande en attente pour ce patient dans ce service
            existing_request = DemandeAdmission.objects.filter(
                patient=patient, service=service, statut="waiting"
            ).first()

            if existing_request:
                # Si c'est un transfert (a une admission_source), permettre
                if not existing_request.admission_source:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Une demande d'admission en attente existe déjà pour ce patient dans ce service",
                        }
                    )

            # Vérifier si le patient a déjà une admission active dans ce service
            active_admission = Admission.objects.filter(
                patient=patient,
                est_active=True,
                date_sortie__isnull=True,
                attributions_lits__lit__chambre__service=service,
                attributions_lits__est_courante=True,
            ).exists()

            if active_admission:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Ce patient est déjà hospitalisé dans ce service",
                    }
                )

            medecin_referent = None
            if medecin_referent_id:
                medecin_referent = get_object_or_404(Medecin, id=medecin_referent_id)

            # Récupérer le personnel connecté
            try:
                cree_par = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                cree_par = None

            # Créer la demande d'admission
            admission_request = DemandeAdmission.objects.create(
                patient=patient,
                service=service,
                medecin_referent=medecin_referent,
                motif=motif,
                notes=notes,
                duree_estimee=int(duree_estimee) if duree_estimee else None,
                cree_par=cree_par,
            )

            return JsonResponse(
                {
                    "success": True,
                    "message": "Demande d'admission créée avec succès",
                    "request_id": admission_request.id,
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Méthode non autorisée"})


@login_required
@csrf_exempt
def admit_patient(request):
    """API endpoint pour admettre un patient via drag & drop"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"})

    try:
        data = json.loads(request.body)
        request_id = data.get("request_id")
        bed_id = data.get("bed_id")
        continue_admission_id = data.get("continue_admission_id")

        if not request_id or not bed_id:
            return JsonResponse({"success": False, "error": "Données manquantes"})

        with transaction.atomic():
            # Récupérer la demande d'admission
            admission_request = get_object_or_404(
                DemandeAdmission.objects.select_related(
                    "patient", "service", "admission_source"
                ),
                id=request_id,
            )

            # Vérifier que la demande est en attente
            if admission_request.statut != "waiting":
                return JsonResponse(
                    {"success": False, "error": "Cette demande n'est plus en attente"}
                )

            # Récupérer le lit
            bed = get_object_or_404(
                Lit.objects.select_related("chambre__service"), id=bed_id
            )

            # Vérifier que le lit est disponible et actif
            if not bed.est_active:
                return JsonResponse(
                    {"success": False, "error": "Ce lit n'est pas actif"}
                )

            if bed.est_occupe:
                return JsonResponse(
                    {"success": False, "error": "Ce lit n'est pas disponible"}
                )

            # Vérifier que le lit est dans le bon service
            if bed.chambre.service != admission_request.service:
                return JsonResponse(
                    {"success": False, "error": "Ce lit n'est pas dans le bon service"}
                )

            # Récupérer le personnel connecté
            try:
                created_by = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                created_by = None

            # CAS 1: C'est un transfert (demande liée à une admission source)
            if admission_request.admission_source:
                existing_admission = admission_request.admission_source

                # Vérifier que l'admission source est toujours active
                if not existing_admission.est_active or existing_admission.date_sortie:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "L'admission source n'est plus active",
                        }
                    )

                # TRANSFERT : Assigner le nouveau lit à l'admission existante
                try:
                    new_attribution = existing_admission.admit_to_lit(
                        bed,
                        cree_par=created_by,
                        note=f"Transfert vers {bed.chambre.service.name} depuis demande #{admission_request.id}",
                    )
                except ValueError as ve:
                    return JsonResponse({"success": False, "error": str(ve)})

                # Marquer la demande comme traitée
                admission_request.statut = "admitted"
                if created_by:
                    admission_request.mark_updated_by(created_by)
                else:
                    admission_request.save(update_fields=["statut"])

                # Créer un enregistrement de transfert pour traçabilité
                # Déterminer le service source
                last_transfer = existing_admission.transferts.order_by(
                    "-date_transfert"
                ).first()
                from_service = last_transfer.to_service if last_transfer else None

                # Si pas de transfert précédent, chercher dans l'historique des attributions
                if not from_service:
                    last_attribution = (
                        existing_admission.attributions_lits.filter(est_courante=False)
                        .order_by("-date_fin")
                        .first()
                    )
                    if last_attribution:
                        from_service = last_attribution.lit.chambre.service

                Transfert.objects.create(
                    admission=existing_admission,
                    from_assignment=None,  # Patient était en liste d'attente
                    to_assignment=new_attribution,
                    from_service=from_service,
                    to_service=bed.chambre.service,
                    date_transfert=timezone.now(),
                    transfere_par=created_by,
                    motif=f"Assignation dans le service {bed.chambre.service.name} (transfert inter-services)",
                    notes=f"Continuation de l'admission #{existing_admission.id} - Patient assigné au lit {bed.numero_lit} depuis la liste d'attente du service {bed.chambre.service.name}",
                    cree_par=created_by,
                )

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Patient assigné au nouveau service (transfert)",
                        "patient_name": f"{admission_request.patient.last_name} {admission_request.patient.first_name}",
                        "admission_id": existing_admission.id,
                        "bed_number": bed.numero_lit,
                        "room_number": bed.chambre.numero_chambre,
                        "continuation": True,
                        "transfer_type": "inter_service_assignment",
                    }
                )

            # CAS 2: Nouvelle admission (pas de source)
            else:
                # Vérifier qu'il n'y a pas d'admission active pour ce patient
                existing_active = Admission.objects.filter(
                    patient=admission_request.patient,
                    est_active=True,
                    date_sortie__isnull=True,
                    statut="active",
                ).exists()

                if existing_active:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Ce patient a déjà une admission active. Utilisez la fonction de transfert.",
                        }
                    )

                # Créer une nouvelle admission
                admission = Admission.objects.create(
                    patient=admission_request.patient,
                    demande_admission=admission_request,
                    medecin_traitant=admission_request.medecin_referent,
                    cree_par=created_by,
                )

                # Assigner le lit
                try:
                    admission.admit_to_lit(
                        bed, cree_par=created_by, note="Admission initiale"
                    )
                except ValueError as ve:
                    return JsonResponse({"success": False, "error": str(ve)})

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Patient admis avec succès",
                        "patient_name": f"{admission_request.patient.last_name} {admission_request.patient.first_name}",
                        "admission_id": admission.id,
                        "bed_number": bed.numero_lit,
                        "room_number": bed.chambre.numero_chambre,
                        "continuation": False,
                    }
                )

    except Exception as e:
        import traceback

        print(f"Erreur admission: {traceback.format_exc()}")
        return JsonResponse({"success": False, "error": str(e)})


@login_required
@csrf_exempt
def transfer_patient(request):
    """API pour transférer un patient - intra-service avec lit spécifié, inter-services vers liste d'attente"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"})

    try:
        data = json.loads(request.body)
        admission_id = data.get("admission_id")
        new_bed_id = data.get("new_bed_id")
        new_service_id = data.get("new_service_id")
        reason = data.get("reason", "Transfert initié par l'administration")

        if not admission_id:
            return JsonResponse({"success": False, "error": "ID d'admission manquant"})

        if not new_bed_id and not new_service_id:
            return JsonResponse(
                {"success": False, "error": "Destination de transfert manquante"}
            )

        with transaction.atomic():
            # Récupérer l'admission actuelle
            try:
                admission = Admission.objects.select_related("patient").get(
                    id=admission_id, est_active=True, date_sortie__isnull=True
                )
            except Admission.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Admission non trouvée ou inactive"}
                )

            # Récupérer le lit actuel
            old_bed = admission.lit_actuel
            if not old_bed:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Aucun lit actuel trouvé pour cette admission",
                    }
                )

            # Récupérer le personnel connecté
            try:
                transferred_by = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                transferred_by = None

            # Cas 1: Transfert intra-service (avec nouveau lit spécifié)
            if new_bed_id:
                new_bed = get_object_or_404(
                    Lit.objects.select_related("chambre__service"), id=new_bed_id
                )

                if not new_bed.est_active:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Le lit de destination n'est pas actif",
                        }
                    )

                if new_bed.est_occupe:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Le lit de destination n'est pas disponible",
                        }
                    )

                if old_bed.id == new_bed.id:
                    return JsonResponse(
                        {"success": False, "error": "Le patient est déjà dans ce lit"}
                    )

                # Vérifier si c'est vraiment intra-service
                if old_bed.chambre.service != new_bed.chambre.service:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Utilisez le transfert inter-services pour changer de service",
                        }
                    )

                # Effectuer le transfert intra-service
                new_attribution = admission.admit_to_lit(
                    new_bed, cree_par=transferred_by, note=reason
                )

                # Enregistrer le transfert
                Transfert.objects.create(
                    admission=admission,
                    from_assignment=admission.attributions_lits.filter(
                        lit=old_bed, est_courante=False
                    )
                    .order_by("-date_fin")
                    .first(),
                    to_assignment=new_attribution,
                    from_service=old_bed.chambre.service,
                    to_service=new_bed.chambre.service,
                    date_transfert=timezone.now(),
                    transfere_par=transferred_by,
                    motif=reason,
                    notes=f"Transfert intra-service: lit {old_bed.numero_lit} vers lit {new_bed.numero_lit}",
                    cree_par=transferred_by,
                )

                return JsonResponse(
                    {
                        "success": True,
                        "transfer_type": "intra_service",
                        "message": "Patient transféré avec succès dans le même service",
                        "patient_name": f"{admission.patient.last_name} {admission.patient.first_name}",
                        "old_bed": f"Chambre {old_bed.chambre.numero_chambre} - Lit {old_bed.numero_lit}",
                        "new_bed": f"Chambre {new_bed.chambre.numero_chambre} - Lit {new_bed.numero_lit}",
                        "service": new_bed.chambre.service.name,
                    }
                )

            # Cas 2: Transfert inter-services SANS FERMER L'ADMISSION
            elif new_service_id:
                new_service = get_object_or_404(Service, id=new_service_id)

                if old_bed.chambre.service.id == new_service.id:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Le patient est déjà dans ce service",
                        }
                    )

                # MODIFICATION: Ne pas fermer l'admission, juste l'attribution courante
                current_attribution = admission.attributions_lits.filter(
                    est_courante=True
                ).first()
                if current_attribution:
                    # Fermer l'attribution courante sans affecter l'admission
                    current_attribution.date_fin = timezone.now()
                    current_attribution.est_courante = False
                    current_attribution.cout = current_attribution.calculer_cout()
                    current_attribution.save(
                        update_fields=["date_fin", "est_courante", "cout"]
                    )

                    # Libérer le lit
                    old_bed.est_occupe = False
                    old_bed.save(update_fields=["est_occupe"])

                    # Historiser le séjour dans ce lit
                    StayHistory.objects.create(
                        patient=admission.patient,
                        admission=admission,
                        bed=old_bed,
                        start_date=current_attribution.date_debut,
                        end_date=current_attribution.date_fin,
                        cost=current_attribution.cout or Decimal("0.00"),
                        notes=f"Libération pour transfert vers {new_service.name}",
                        cree_par=transferred_by,
                    )

                # L'ADMISSION RESTE ACTIVE - ne pas la fermer
                # Créer une demande d'admission dans le nouveau service
                transfer_request = DemandeAdmission.objects.create(
                    patient=admission.patient,
                    service=new_service,
                    medecin_referent=admission.medecin_traitant,
                    motif=f"Transfert inter-services depuis {old_bed.chambre.service.name}: {reason}",
                    notes=f"Transfert de l'admission #{admission.id} depuis le service {old_bed.chambre.service.name}. Patient libéré du lit {old_bed.numero_lit} (Chambre {old_bed.chambre.numero_chambre}).",
                    statut="waiting",
                    cree_par=transferred_by,
                    admission_source=admission,  # NOUVEAU: Lier à l'admission source
                )

                # Enregistrer le transfert inter-services
                Transfert.objects.create(
                    admission=admission,
                    from_assignment=current_attribution,
                    to_assignment=None,  # Pas encore de nouveau lit
                    from_service=old_bed.chambre.service,
                    to_service=new_service,
                    date_transfert=timezone.now(),
                    transfere_par=transferred_by,
                    motif=reason,
                    notes=f"Transfert inter-services: admission continue #{admission.id}. Patient libéré du lit {old_bed.numero_lit} vers liste d'attente du service {new_service.name}.",
                    cree_par=transferred_by,
                )

                # Mettre à jour le coût total de l'admission (sans la fermer)
                admission.cout_total = admission.calculer_cout_total()
                admission.save(update_fields=["cout_total"])

                return JsonResponse(
                    {
                        "success": True,
                        "transfer_type": "inter_service_continuous",
                        "message": f"Patient transféré vers la liste d'attente du service {new_service.name} (admission continue)",
                        "patient_name": f"{admission.patient.last_name} {admission.patient.first_name}",
                        "old_service": old_bed.chambre.service.name,
                        "new_service": new_service.name,
                        "old_bed": f"Chambre {old_bed.chambre.numero_chambre} - Lit {old_bed.numero_lit}",
                        "request_id": transfer_request.id,
                    }
                )

    except Exception as e:
        import traceback

        print(f"Erreur transfert: {traceback.format_exc()}")
        return JsonResponse({"success": False, "error": str(e)})


@login_required
def available_beds_by_service_api(request, service_id=None):
    """API pour récupérer les lits disponibles par service"""
    try:
        beds = Lit.objects.filter(
            est_active=True,
            est_occupe=False
        ).select_related("chambre__service")

        if service_id:
            beds = beds.filter(chambre__service_id=service_id)

        beds_data = []
        for bed in beds:
            beds_data.append(
                {
                    "id": bed.id,
                    "bed_number": bed.numero_lit,
                    "room_number": bed.chambre.numero_chambre,
                    "service_id": bed.chambre.service.id,
                    "service_name": bed.chambre.service.name,
                    "room_type": bed.chambre.get_type_chambre_display(),
                    "night_price": float(bed.chambre.prix_nuit),
                }
            )

        return JsonResponse(
            {"success": True, "beds": beds_data, "total_count": len(beds_data)}
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def admission_detail_api(request, admission_id):
    """API pour récupérer les détails d'une admission avec gestion des séjours courts"""
    try:
        admission = get_object_or_404(
            Admission.objects.select_related(
                "patient", "medecin_traitant"
            ).prefetch_related(
                "attributions_lits__lit__chambre__service",
                "transferts__from_service",
                "transferts__to_service",
                "transferts__transfere_par",
                "historique_sejours__bed__chambre__service",
            ),
            id=admission_id,
        )

        # Calculer la durée de séjour en heures et jours
        length_of_stay_hours = admission.duree_sejour_heures
        length_of_stay_days = admission.duree_sejour

        # Utiliser la nouvelle méthode de calcul avec séjours courts
        estimated_cost = float(admission.calculer_cout_total())

        # Obtenir le résumé de facturation avec détails des séjours courts
        resume_facturation = admission.get_resume_facturation()

        # Récupérer le lit actuel
        lit_actuel = admission.lit_actuel

        # Préparer les données du lit si disponible
        bed_data = None
        if lit_actuel:
            bed_data = {
                "id": lit_actuel.id,
                "bed_number": lit_actuel.numero_lit,
                "room": {
                    "id": lit_actuel.chambre.id,
                    "room_number": lit_actuel.chambre.numero_chambre,
                    "service": lit_actuel.chambre.service.name,
                    "night_price": float(lit_actuel.chambre.prix_nuit),
                },
            }

        # Historique détaillé des attributions avec gestion des séjours courts
        attributions_history = []
        for attribution in admission.attributions_lits.all().order_by("date_debut"):
            details_facturation = attribution.get_facturation_details()

            attributions_history.append(
                {
                    "id": attribution.id,
                    "bed_number": attribution.lit.numero_lit,
                    "room_number": attribution.lit.chambre.numero_chambre,
                    "service_name": attribution.lit.chambre.service.name,
                    "start_date": attribution.date_debut.isoformat(),
                    "end_date": (
                        attribution.date_fin.isoformat()
                        if attribution.date_fin
                        else None
                    ),
                    "is_current": attribution.est_courante,
                    "duration_hours": details_facturation['duree_heures'],
                    "duration_days": details_facturation['duree_jours'],
                    "cost": details_facturation['cout_total'],
                    "night_price_applied": details_facturation['prix_nuit_applique'],
                    "current_room_price": float(attribution.lit.chambre.prix_nuit),
                    "price_changed": details_facturation['prix_nuit_applique'] != float(
                        attribution.lit.chambre.prix_nuit),
                    "is_short_stay": details_facturation['est_sejour_court'],
                    "billing_mode": details_facturation['mode_facturation'],
                    "billing_formula": details_facturation['formule'],
                    "service_fixed_rate": details_facturation.get('tarif_fixe_service'),
                    "hourly_rate": details_facturation.get('tarif_horaire'),
                    "notes": attribution.notes or "",
                }
            )

        # Historique des transferts (inchangé)
        transfers_history = []
        for transfert in admission.transferts.all().order_by("date_transfert"):
            transfer_data = {
                "id": transfert.id,
                "date": transfert.date_transfert.isoformat(),
                "reason": transfert.motif or "Non spécifié",
                "notes": transfert.notes or "",
                "transferred_by": (
                    transfert.transfere_par.nom_complet
                    if transfert.transfere_par
                    else "Non spécifié"
                ),
                "from_service": (
                    transfert.from_service.name if transfert.from_service else None
                ),
                "to_service": (
                    transfert.to_service.name if transfert.to_service else None
                ),
                "financial_impact": {
                    "price_difference": float(transfert.difference_cout_nuitee),
                    "impact_description": transfert.get_impact_financier_description(),
                }
            }

            # Informations sur les lits avec prix
            if transfert.from_assignment:
                transfer_data["from_bed"] = {
                    "bed_number": transfert.from_assignment.lit.numero_lit,
                    "room_number": transfert.from_assignment.lit.chambre.numero_chambre,
                    "service": transfert.from_assignment.lit.chambre.service.name,
                    "night_price": float(transfert.from_assignment.prix_nuit),
                }

            if transfert.to_assignment:
                transfer_data["to_bed"] = {
                    "bed_number": transfert.to_assignment.lit.numero_lit,
                    "room_number": transfert.to_assignment.lit.chambre.numero_chambre,
                    "service": transfert.to_assignment.lit.chambre.service.name,
                    "night_price": float(transfert.to_assignment.prix_nuit),
                }

            # Type de transfert
            if transfert.from_service and transfert.to_service:
                if transfert.from_service.id == transfert.to_service.id:
                    transfer_data["type"] = "intra_service"
                    transfer_data["type_display"] = "Transfert intra-service"
                else:
                    transfer_data["type"] = "inter_service"
                    transfer_data["type_display"] = "Transfert inter-services"
            else:
                transfer_data["type"] = "unknown"
                transfer_data["type_display"] = "Type inconnu"

            transfers_history.append(transfer_data)

        # Parcours détaillé avec coûts (adapté pour les séjours courts)
        parcours_detaille = admission.obtenir_parcours_detaille_avec_couts()
        detailed_journey = []
        for etape in parcours_detaille:
            # Obtenir les détails de facturation pour cette étape
            attribution_details = etape['attribution'].get_facturation_details()

            detailed_journey.append(
                {
                    "service": etape['service'].name,
                    "room_number": etape['chambre'].numero_chambre,
                    "bed_number": etape['lit'].numero_lit,
                    "start_date": etape['date_debut'].isoformat(),
                    "end_date": etape['date_fin'].isoformat() if etape['date_fin'] else None,
                    "duration_days": etape['duree_jours'],
                    "duration_hours": attribution_details['duree_heures'],
                    "night_price": float(etape['prix_nuit']),
                    "period_cost": float(etape['cout_periode']),
                    "cumulative_cost": float(etape['total_cumule']),
                    "is_current": etape['est_courante'],
                    "is_short_stay": attribution_details['est_sejour_court'],
                    "billing_mode": attribution_details['mode_facturation'],
                    "billing_details": attribution_details
                })

        response_data = {
            "success": True,
            "admission": {
                "id": admission.id,
                "admission_date": admission.date_admission.isoformat(),
                "discharge_date": (
                    admission.date_sortie.isoformat() if admission.date_sortie else None
                ),
                "status": admission.get_statut_display(),
                "length_of_stay_days": length_of_stay_days,
                "length_of_stay_hours": round(length_of_stay_hours, 2),
                "estimated_cost": estimated_cost,
                "patient": {
                    "id": admission.patient.id,
                    "last_name": admission.patient.last_name,
                    "first_name": admission.patient.first_name,
                    "social_security_number": getattr(
                        admission.patient, "numero_securite_sociale", ""
                    )
                                              or getattr(admission.patient, "social_security_number", ""),
                },
                "bed": bed_data,
                "attending_doctor": (
                    {
                        "id": admission.medecin_traitant.id,
                        "nom_complet": admission.medecin_traitant.nom_complet,
                    }
                    if admission.medecin_traitant
                    else None
                ),
                # CHAMPS AMÉLIORÉS
                "attributions_history": attributions_history,
                "transfers_history": transfers_history,
                "detailed_journey": detailed_journey,
                # NOUVEAU: Résumé de facturation avec détails des séjours courts
                "billing_summary": resume_facturation,
            },
        }

        return JsonResponse(response_data)

    except Admission.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Admission non trouvée"}, status=404
        )
    except Exception as e:
        import traceback

        print(f"Erreur lors de la récupération des détails: {traceback.format_exc()}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def discharge_patient(request, admission_id):
    """Vue pour la sortie d'un patient"""
    try:
        admission = get_object_or_404(
            Admission.objects.select_related('patient'),
            id=admission_id,
            est_active=True,
            date_sortie__isnull=True
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Admission non trouvée: {str(e)}"}, status=404
        )

    if request.method == "POST":
        try:
            # Récupérer les données du formulaire
            discharge_destination = request.POST.get("discharge_destination", "").strip()
            discharge_notes = request.POST.get("discharge_notes", "").strip()

            # Validation des données
            if not discharge_destination:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "La destination de sortie est obligatoire",
                    },
                    status=400,
                )

            if not discharge_notes:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Les notes de sortie sont obligatoires",
                    },
                    status=400,
                )

            # Récupérer le personnel connecté
            try:
                discharged_by = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                discharged_by = None

            # Utiliser la méthode du modèle pour la sortie
            total_cost = admission.discharge(
                discharged_by=discharged_by,
                notes=f"Destination: {discharge_destination}\nNotes: {discharge_notes}"
            )

            return JsonResponse(
                {
                    "success": True,
                    "message": "Sortie enregistrée avec succès",
                    "admission_id": admission.id,
                    "patient_name": f"{admission.patient.last_name} {admission.patient.first_name}",
                    "total_cost": float(total_cost),
                }
            )

        except Exception as e:
            import logging
            import traceback

            logger = logging.getLogger(__name__)
            logger.error(
                f"Erreur lors de la sortie du patient {admission_id}: {str(e)}"
            )
            logger.error(f"Traceback: {traceback.format_exc()}")

            return JsonResponse(
                {
                    "success": False,
                    "error": f"Erreur lors de l'enregistrement de la sortie: {str(e)}",
                },
                status=500,
            )

    # Pour les requêtes GET - retourner les détails de l'admission
    try:
        lit_actuel = admission.lit_actuel

        return JsonResponse(
            {
                "success": True,
                "admission": {
                    "id": admission.id,
                    "patient_name": f"{admission.patient.last_name} {admission.patient.first_name}",
                    "room_number": (
                        lit_actuel.chambre.numero_chambre
                        if lit_actuel and lit_actuel.chambre
                        else "N/A"
                    ),
                    "bed_number": lit_actuel.numero_lit if lit_actuel else "N/A",
                    "admission_date": admission.date_admission.strftime("%d/%m/%Y %H:%M"),
                    "length_of_stay": admission.duree_sejour,
                },
            }
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Erreur lors du chargement: {str(e)}"},
            status=500,
        )


@login_required
def room_detail_api(request, room_id):
    """API pour récupérer les détails d'une chambre"""
    try:
        room = get_object_or_404(
            Chambre.objects.prefetch_related(
                Prefetch(
                    'lits',
                    queryset=Lit.objects.filter(est_active=True).prefetch_related(
                        Prefetch(
                            'attributions_lits',
                            queryset=AttributionLit.objects.filter(est_courante=True)
                            .select_related('admission__patient')
                        )
                    )
                )
            ),
            id=room_id
        )

        # Préparer les données des lits
        beds_data = []
        for bed in room.lits.all():
            current_patient = bed.patient_actuel
            current_patient_name = None
            if current_patient:
                current_patient_name = f"{current_patient.last_name} {current_patient.first_name}"

            beds_data.append(
                {
                    "id": bed.id,
                    "bed_number": bed.numero_lit,
                    "is_occupied": bed.est_occupe,
                    "current_patient": current_patient_name,
                    "status": bed.statut_affichage,
                }
            )

        response_data = {
            "success": True,
            "room": {
                "id": room.id,
                "room_number": room.numero_chambre,
                "room_type": room.type_chambre,
                "room_type_display": room.get_type_chambre_display(),
                "bed_capacity": room.capacite_lits,
                "night_price": float(room.prix_nuit),
                "est_active": room.est_active,
                "occupied_beds_count": room.nombre_lits_occupes,
                "available_beds_count": room.nombre_lits_disponibles,
                "beds": beds_data,
            },
        }

        return JsonResponse(response_data)

    except Chambre.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Chambre non trouvée"}, status=404
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@csrf_exempt
def transfer_patient_to_service(request):
    """API pour transférer un patient vers un autre service (liste d'attente)"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"})
    try:
        data = json.loads(request.body)
        admission_id = data.get("admission_id")
        new_service_id = data.get("new_service_id")
        reason = data.get("reason", "Transfert entre services")

        if not admission_id or not new_service_id:
            return JsonResponse({"success": False, "error": "Données manquantes"})

        with transaction.atomic():
            # Récupérer l'admission actuelle
            try:
                admission = Admission.objects.select_related("patient").get(
                    id=admission_id, est_active=True, date_sortie__isnull=True
                )
            except Admission.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Admission non trouvée ou inactive"}
                )

            # Récupérer le nouveau service
            new_service = get_object_or_404(Service, id=new_service_id)

            # Récupérer le lit actuel
            old_bed = admission.lit_actuel
            if not old_bed:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Aucun lit actuel trouvé pour cette admission",
                    }
                )

            # Vérifier qu'on ne transfère pas vers le même service
            if old_bed.chambre.service.id == new_service.id:
                return JsonResponse(
                    {"success": False, "error": "Le patient est déjà dans ce service"}
                )

            # Récupérer le personnel connecté
            try:
                transferred_by = Personnel.objects.get(user=request.user)
            except Personnel.DoesNotExist:
                transferred_by = None

            # CORRECTION PRINCIPALE : Fermer l'attribution courante sans fermer l'admission
            current_attribution = admission.attributions_lits.filter(
                est_courante=True
            ).first()
            if current_attribution:
                # Fermer l'attribution courante
                current_attribution.date_fin = timezone.now()
                current_attribution.est_courante = False
                current_attribution.cout = current_attribution.calculer_cout()
                if transferred_by:
                    current_attribution.mis_a_jour_par = transferred_by
                current_attribution.save(
                    update_fields=["date_fin", "est_courante", "cout", "mis_a_jour_par"]
                )

                # Libérer le lit
                old_bed.est_occupe = False
                old_bed.save(update_fields=["est_occupe"])

                # Historiser le séjour
                StayHistory.objects.create(
                    patient=admission.patient,
                    admission=admission,
                    bed=old_bed,
                    start_date=current_attribution.date_debut,
                    end_date=current_attribution.date_fin,
                    cost=current_attribution.cout or Decimal("0.00"),
                    notes=f"Libération pour transfert vers {new_service.name}",
                    cree_par=transferred_by,
                )

            # CORRECTION : Vérifier qu'il n'y a pas déjà une demande en attente pour ce service
            existing_request = DemandeAdmission.objects.filter(
                patient=admission.patient,
                service=new_service,
                statut="waiting",
                admission_source=admission,
            ).first()

            if existing_request:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Une demande de transfert vers {new_service.name} existe déjà pour ce patient",
                    }
                )

            # Créer une demande d'admission dans le nouveau service AVEC LIEN vers l'admission source
            transfer_request = DemandeAdmission.objects.create(
                patient=admission.patient,
                service=new_service,
                medecin_referent=admission.medecin_traitant,
                motif=f"Transfert inter-services depuis {old_bed.chambre.service.name}: {reason}",
                notes=f"Transfert de l'admission #{admission.id} depuis le service {old_bed.chambre.service.name}. Patient libéré du lit {old_bed.numero_lit} (Chambre {old_bed.chambre.numero_chambre}).",
                statut="waiting",
                cree_par=transferred_by,
                admission_source=admission,  # CRUCIAL: Lier à l'admission source
            )

            # Enregistrer le transfert inter-services
            Transfert.objects.create(
                admission=admission,
                from_assignment=current_attribution,
                to_assignment=None,  # Pas encore de nouveau lit
                from_service=old_bed.chambre.service,
                to_service=new_service,
                date_transfert=timezone.now(),
                transfere_par=transferred_by,
                motif=reason,
                notes=f"Transfert inter-services: admission continue #{admission.id}. Patient libéré du lit {old_bed.numero_lit} vers liste d'attente du service {new_service.name}.",
                cree_par=transferred_by,
            )

            # Mettre à jour le coût total de l'admission (sans la fermer)
            admission.cout_total = admission.calculer_cout_total()
            if transferred_by:
                admission.mis_a_jour_par = transferred_by
            admission.save(update_fields=["cout_total", "mis_a_jour_par"])

            return JsonResponse(
                {
                    "success": True,
                    "transfer_type": "inter_service_continuous",
                    "message": f"Patient transféré vers la liste d'attente du service {new_service.name} (admission continue)",
                    "patient_name": f"{admission.patient.last_name} {admission.patient.first_name}",
                    "old_service": old_bed.chambre.service.name,
                    "new_service": new_service.name,
                    "old_bed": f"Chambre {old_bed.chambre.numero_chambre} - Lit {old_bed.numero_lit}",
                    "request_id": transfer_request.id,
                    "admission_id": admission.id,
                }
            )

    except Exception as e:
        import traceback

        print(f"Erreur transfert: {traceback.format_exc()}")
        return JsonResponse({"success": False, "error": str(e)})


@login_required
@csrf_exempt
def cancel_admission_request(request, request_id):
    """API pour annuler une demande d'admission"""
    if request.method == "POST":
        try:
            admission_request = get_object_or_404(DemandeAdmission, id=request_id)

            if admission_request.statut != "waiting":
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Seules les demandes en attente peuvent être annulées",
                    }
                )

            # Récupérer le personnel connecté
            try:
                cancelled_by = Personnel.objects.get(user=request.user)
                print(f"Personnel trouvé: {cancelled_by}")
            except Personnel.DoesNotExist:
                cancelled_by = None
                print("Aucun personnel trouvé pour cet utilisateur")

            # CORRECTION: Changer le statut ET sauvegarder explicitement
            admission_request.statut = "cancelled"

            if cancelled_by:
                # La méthode mark_updated_by doit inclure la sauvegarde du statut
                admission_request.mark_updated_by(
                    cancelled_by, save=False
                )  # Ne pas sauver encore
                admission_request.save(
                    update_fields=["statut", "mis_a_jour_par", "mis_a_jour_le"]
                )
            else:
                admission_request.save(update_fields=["statut"])

            print(f"Statut après sauvegarde: {admission_request.statut}")

            # Vérifier que la sauvegarde a bien eu lieu
            admission_request.refresh_from_db()
            print(f"Statut après refresh_from_db: {admission_request.statut}")

            return JsonResponse(
                {"success": True, "message": "Demande d'admission annulée avec succès"}
            )

        except Exception as e:
            print(f"Erreur lors de l'annulation: {str(e)}")
            import traceback

            print(f"Traceback complet: {traceback.format_exc()}")
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Méthode non autorisée"})


@login_required
@csrf_exempt
def check_requests_status(request):
    """API pour vérifier le statut des demandes d'admission"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"})

    try:
        data = json.loads(request.body)
        request_ids = data.get("request_ids", [])

        if not request_ids:
            return JsonResponse(
                {"success": False, "error": "Aucun ID de demande fourni"}
            )

        # Récupérer les demandes qui ne sont plus en attente
        processed_requests = list(
            DemandeAdmission.objects.filter(
                id__in=request_ids, statut__in=["admitted", "cancelled", "transferred"]
            ).values_list("id", flat=True)
        )

        return JsonResponse({"success": True, "processed_requests": processed_requests})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
def financial_report_api(request, admission_id):
    """API pour générer un rapport financier détaillé d'une admission"""
    try:
        admission = get_object_or_404(Admission, id=admission_id)

        # Récupérer le parcours détaillé avec coûts
        parcours_detaille = admission.obtenir_parcours_detaille_avec_couts()

        # Statistiques financières
        total_cost = admission.calculer_cout_total()
        nombre_transferts = admission.transferts.count()
        services_visites = list(set([etape['service'].name for etape in parcours_detaille]))

        # Détail par service
        couts_par_service = {}
        for etape in parcours_detaille:
            service_name = etape['service'].name
            if service_name not in couts_par_service:
                couts_par_service[service_name] = {
                    'jours': 0,
                    'cout_total': Decimal('0.00'),
                    'prix_moyen': Decimal('0.00'),
                    'periodes': []
                }

            couts_par_service[service_name]['jours'] += etape['duree_jours']
            couts_par_service[service_name]['cout_total'] += etape['cout_periode']
            couts_par_service[service_name]['periodes'].append({
                'chambre': etape['chambre'].numero_chambre,
                'lit': etape['lit'].numero_lit,
                'jours': etape['duree_jours'],
                'prix_nuit': etape['prix_nuit'],
                'cout': etape['cout_periode'],
            })

        # Calculer prix moyen par service
        for service_data in couts_par_service.values():
            if service_data['jours'] > 0:
                service_data['prix_moyen'] = service_data['cout_total'] / service_data['jours']

        return JsonResponse({
            "success": True,
            "financial_report": {
                "admission_id": admission.id,
                "patient_name": f"{admission.patient.last_name} {admission.patient.first_name}",
                "total_cost": float(total_cost),
                "total_days": admission.duree_sejour,
                "average_daily_cost": float(total_cost / admission.duree_sejour) if admission.duree_sejour > 0 else 0,
                "number_of_transfers": nombre_transferts,
                "services_visited": services_visites,
                "cost_by_service": {
                    service: {
                        "days": data['jours'],
                        "total_cost": float(data['cout_total']),
                        "average_price": float(data['prix_moyen']),
                        "periods": [
                            {
                                "room": periode['chambre'],
                                "bed": periode['lit'],
                                "days": periode['jours'],
                                "night_price": float(periode['prix_nuit']),
                                "period_cost": float(periode['cout']),
                            }
                            for periode in data['periodes']
                        ]
                    }
                    for service, data in couts_par_service.items()
                },
                "detailed_journey": [
                    {
                        "service": etape['service'].name,
                        "room": etape['chambre'].numero_chambre,
                        "bed": etape['lit'].numero_lit,
                        "start_date": etape['date_debut'].isoformat(),
                        "end_date": etape['date_fin'].isoformat() if etape['date_fin'] else None,
                        "days": etape['duree_jours'],
                        "night_price": float(etape['prix_nuit']),
                        "period_cost": float(etape['cout_periode']),
                        "cumulative_cost": float(etape['total_cumule']),
                    }
                    for etape in parcours_detaille
                ]
            }
        })

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def clean_obsolete_requests():
    """Nettoie les demandes d'admission obsolètes"""
    from django.utils import timezone
    from datetime import timedelta

    # Marquer comme annulées les demandes très anciennes sans admission source
    old_requests = DemandeAdmission.objects.filter(
        statut="waiting",
        admission_source__isnull=True,  # Pas de transfert
        date_demande__lt=timezone.now() - timedelta(days=7),  # Plus de 7 jours
    )

    count = old_requests.update(statut="cancelled")
    return count

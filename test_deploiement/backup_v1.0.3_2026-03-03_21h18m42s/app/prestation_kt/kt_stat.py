from flask import render_template, g

from app import app, get_db_connection
from collections import defaultdict


@app.route("/kt_stats")
def kt_stats():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Notez que nous récupérons désormais les colonnes nécessaires
            sql = """
            SELECT
                d.id_dossier,
                CONCAT(doc.first_name, ' ', doc.last_name) AS doctor_name, 
                d.patient AS patient_name, 
                d.acte_date,
                d.urgence, 
                ak.code_cnas, 
                d.extras, 
                d.part_operateur_extrat, 
                dak.convention,
                dak.part_clinique_convention,
                dak.part_clinique_esp,
                dak.part_operateur AS part_operateur_acte 
            FROM kt_dossier_patient d
            LEFT JOIN kt_dossier_actes dak ON d.id_dossier = dak.id_dossier
            LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
            LEFT JOIN doctors doc ON d.id_doctor = doc.id
            WHERE doc.id_specialty IN (11, 19, 20)
            ORDER BY d.acte_date
            """
            cursor.execute(sql)
            results = cursor.fetchall()
    finally:
        connection.close()

    # Initialisation des agrégations par médecin
    aggregated_convention = {}
    aggregated_esp = {}
    aggregated_operator_convention = {}
    aggregated_operator_esp = {}

    # NOUVEAU: Agrégations par mois
    monthly_convention = defaultdict(float)
    monthly_esp = defaultdict(float)

    for row in results:
        doctor = row.get("doctor_name") or "Inconnu"

        # Extraction du mois depuis acte_date (format: YYYY-MM)
        acte_date = row.get("acte_date")
        if acte_date:
            month_key = acte_date.strftime("%Y-%m")
        else:
            month_key = "Inconnu"

        # Initialisation
        aggregated_convention[doctor] = aggregated_convention.get(doctor, 0)
        aggregated_esp[doctor] = aggregated_esp.get(doctor, 0)
        aggregated_operator_convention[doctor] = aggregated_operator_convention.get(
            doctor, 0
        )
        aggregated_operator_esp[doctor] = aggregated_operator_esp.get(doctor, 0)

        # Récupération des valeurs numériques
        extras = 0
        try:
            extras = float(row.get("extras") or 0)
        except ValueError:
            extras = 0

        # ✅ Utiliser les prix déjà calculés et stockés dans kt_dossier_actes
        try:
            price_convention = float(row.get("part_clinique_convention") or 0)
        except (ValueError, TypeError):
            price_convention = 0

        try:
            price_esp = float(row.get("part_clinique_esp") or 0)
        except (ValueError, TypeError):
            price_esp = 0

        # Ajouter extras au prix espèces si convention payante
        convention_value = row.get("convention")
        if convention_value and convention_value.lower() == "payante":
            price_esp += extras

        # Agrégation mensuelle
        monthly_convention[month_key] += price_convention
        monthly_esp[month_key] += price_esp

        aggregated_convention[doctor] += price_convention
        aggregated_esp[doctor] += price_esp

        # Parts opérateurs (code existant)
        try:
            part_operator_acte = float(row.get("part_operateur_acte") or 0)
        except ValueError:
            part_operator_acte = 0
        try:
            part_operator_extrat = float(row.get("part_operateur_extrat") or 0)
        except ValueError:
            part_operator_extrat = 0

        if convention_value and convention_value.lower() == "payante":
            operator_value = part_operator_acte + part_operator_extrat
            aggregated_operator_esp[doctor] += operator_value
        else:
            operator_value = part_operator_acte
            aggregated_operator_convention[doctor] += operator_value

    # Tri des données par médecin
    sorted_convention = sorted(
        aggregated_convention.items(), key=lambda item: item[1], reverse=True
    )
    sorted_esp = sorted(aggregated_esp.items(), key=lambda item: item[1], reverse=True)
    sorted_operator_convention = sorted(
        aggregated_operator_convention.items(), key=lambda item: item[1], reverse=True
    )
    sorted_operator_esp = sorted(
        aggregated_operator_esp.items(), key=lambda item: item[1], reverse=True
    )

    # Tri des données mensuelles
    sorted_monthly = sorted(monthly_convention.keys())

    labels_convention = [item[0] for item in sorted_convention]
    data_convention = [item[1] for item in sorted_convention]

    labels_esp = [item[0] for item in sorted_esp]
    data_esp = [item[1] for item in sorted_esp]

    labels_operator_convention = [item[0] for item in sorted_operator_convention]
    data_operator_convention = [item[1] for item in sorted_operator_convention]

    labels_operator_esp = [item[0] for item in sorted_operator_esp]
    data_operator_esp = [item[1] for item in sorted_operator_esp]

    # Données mensuelles
    labels_monthly = sorted_monthly
    data_monthly_convention = [monthly_convention[month] for month in sorted_monthly]
    data_monthly_esp = [monthly_esp[month] for month in sorted_monthly]

    total_convention = sum(data_convention)
    total_esp = sum(data_esp)
    total_operator_convention = sum(data_operator_convention)
    total_operator_esp = sum(data_operator_esp)

    return render_template(
        "admin/kt_stats.html",
        results=results,
        labels_convention=labels_convention,
        data_convention=data_convention,
        labels_esp=labels_esp,
        data_esp=data_esp,
        labels_operator_convention=labels_operator_convention,
        data_operator_convention=data_operator_convention,
        labels_operator_esp=labels_operator_esp,
        data_operator_esp=data_operator_esp,
        labels_monthly=labels_monthly,
        data_monthly_convention=data_monthly_convention,
        data_monthly_esp=data_monthly_esp,
        total_convention=total_convention,
        total_esp=total_esp,
        total_operator_convention=total_operator_convention,
        total_operator_esp=total_operator_esp,
        user=g.user,
    )

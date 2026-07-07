# hospitalisation/urls.py
from django.urls import path

from . import views

app_name = "hospitalisation"

urlpatterns = [
    # Vue principale du plan d"étage
    path(
        "floor_plan/<int:service_id>/",
        views.floor_plan_centralized,
        name="floor_plan_centralized",
    ),
    # API endpoints pour les actions AJAX
    path("api/admit_patient/", views.admit_patient, name="admit_patient"),
    path("api/transfer_patient/", views.transfer_patient, name="transfer_patient"),
    path(
        "api/transfer_patient_to_service/",
        views.transfer_patient_to_service,
        name="transfer_patient_to_service",
    ),
    path(
        "api/add_admission_request/",
        views.add_admission_request,
        name="add_admission_request",
    ),
    path(
        "api/discharge_patient/<int:admission_id>/",
        views.discharge_patient,
        name="discharge_patient",
    ),
    path(
        "api/cancel_admission_request/<int:request_id>/",
        views.cancel_admission_request,
        name="cancel_admission_request",
    ),
    # API endpoints pour récupérer les données
    path(
        "api/admission_detail/<int:admission_id>/",
        views.admission_detail_api,
        name="admission_detail_api",
    ),
    path(
        "api/available_beds/",
        views.available_beds_by_service_api,
        name="available_beds_api",
    ),
    path(
        "api/available_beds/<int:service_id>/",
        views.available_beds_by_service_api,
        name="available_beds_by_service_api",
    ),
    path(
        "api/room_detail/<int:room_id>/", views.room_detail_api, name="room_detail_api"
    ),
    path(
        "api/check-requests-status/",
        views.check_requests_status,
        name="check_requests_status",
    ),
]

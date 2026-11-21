from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from ..models.thietbi import ThietBi
from ..services.network_monitor_service import (
    diagnose_device,
    get_network_monitor_snapshot,
)
from ..utils.sql_error_handler import get_sql_error


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_network_monitor_snapshot(request):
    try:
        return JsonResponse(get_network_monitor_snapshot(), status=status.HTTP_200_OK)
    except Exception as error:
        message, status_code = get_sql_error(error)
        return JsonResponse({"error": message}, status=status_code)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_network_diagnostics(request, ma_tb):
    try:
        device = ThietBi.objects.get(ma_tb=ma_tb)
    except ThietBi.DoesNotExist:
        return JsonResponse(
            {"error": "Không tìm thấy thiết bị"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as error:
        message, status_code = get_sql_error(error)
        return JsonResponse({"error": message}, status=status_code)

    return JsonResponse(diagnose_device(device), status=status.HTTP_200_OK)

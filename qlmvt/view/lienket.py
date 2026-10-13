from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from ..utils.sql_error_handler import get_sql_error
from rest_framework import status
from ..model.lienket import LienKet
from ..serializers import LienKetSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_get_ds_lk(request):
    """lấy danh sách liên kết"""
    try:
        ds_lk = LienKet.objects.all()
        serializer = LienKetSerializer(ds_lk, many=True)
        return JsonResponse(serializer.data, status=status.HTTP_200_OK, safe=False)

    except Exception as e:
        message, status_code = get_sql_error(e)
        return JsonResponse({"error": message}, status=status_code)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_get_lk(request, ma_lk):
    """lấyy liên kết theo mã liên kết"""
    try:
        lk = LienKet.objects.get(ma_lk=ma_lk)
        serializer = LienKetSerializer(lk)
        return JsonResponse(serializer.data, status=status.HTTP_200_OK)

    except LienKet.DoesNotExist:
        return JsonResponse(
            {"error": "Không tìm thấy liên kết"}, status=status.HTTP_404_NOT_FOUND
        )

    except Exception as e:
        message, status_code = get_sql_error(e)
        return JsonResponse({"error": message}, status=status_code)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_lk(request):
    """thêm mới 1 hoặc nhiều liên kết cùng lúc, chỉ admin được phép tạo mới"""
    try:
        if not request.user.is_staff:
            return JsonResponse(
                {"error": "Bạn không có quyền tạo mới liên kết"},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = request.data.copy()
        ma_nv = request.user.employee_account.nhan_vien.ma_nv
        if isinstance(data, list):
            for item in data:
                item.setdefault("manv_tao", ma_nv)
            serializer = LienKetSerializer(data=data, many=True)
        else:
            data.setdefault("manv_tao", ma_nv)
            serializer = LienKetSerializer(data=data)

        if serializer.is_valid():
            serializer.save()
            return JsonResponse(serializer.data, status=status.HTTP_201_CREATED)

        return JsonResponse(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        message, status_code = get_sql_error(e)
        return JsonResponse({"error": message}, status=status_code)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def api_update_lk(request, ma_lk):
    """cập nhật liên kết theo mã:
    + Admin chỉ được cập nhật liên kết do mình tạo
    """
    try:
        if not request.user.is_staff:
            return JsonResponse(
                {"error": "Bạn không có quyền sửa liên kết"},
                status=status.HTTP_403_FORBIDDEN,
            )
        lk = LienKet.objects.get(ma_lk=ma_lk)

        ma_nv = request.user.employee_account.nhan_vien.ma_nv
        print(ma_nv, lk.manv_tao.ma_nv)
        if lk.manv_tao.ma_nv != ma_nv:
            return JsonResponse(
                {"error": "Bạn không có quyền chỉnh sửa liên kết này"},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Không cho sửa mã liên kết
        data = request.data.copy()
        data.pop("ma_lk", None)
        serializer = LienKetSerializer(lk, data=data)

        if serializer.is_valid():
            serializer.save()
            return JsonResponse(serializer.data, status=status.HTTP_200_OK)

        return JsonResponse(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except LienKet.DoesNotExist:
        return JsonResponse(
            {"error": "Không tìm thấy liên kết"}, status=status.HTTP_404_NOT_FOUND
        )

    except Exception as e:
        message, status_code = get_sql_error(e)
        return JsonResponse({"error": message}, status=status_code)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def api_delete_lk(request, ma_lk):
    """xoá liên kết theo mã liên kết
    + Admin chỉ được xoá liên kết do mình tạo
    """
    try:
        if not request.user.is_staff:
            return JsonResponse(
                {"error": "Bạn không có quyền xoá liên kết"},
                status=status.HTTP_403_FORBIDDEN,
            )
        lk = LienKet.objects.get(ma_lk=ma_lk)

        ma_nv = request.user.employee_account.nhan_vien.ma_nv
        if lk.manv_tao.ma_nv != ma_nv:
            return JsonResponse(
                {"error": "Bạn không có quyền xoá liên kết này"},
                status=status.HTTP_403_FORBIDDEN,
            )
        lk.delete()

        return JsonResponse({"message": "Đã xoá thành công"}, status=status.HTTP_200_OK)

    except LienKet.DoesNotExist:
        return JsonResponse(
            {"error": "Không tìm thấy liên kết"}, status=status.HTTP_404_NOT_FOUND
        )

    except Exception as e:
        message, status_code = get_sql_error(e)
        return JsonResponse({"error": message}, status=status_code)

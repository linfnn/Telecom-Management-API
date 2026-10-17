import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from rest_framework.decorators import api_view, permission_classes

from ..models.hieusuat import ChiSoHieuSuat
from ..models.lienket import LienKet
from ..models.lohong import LoHong
from ..models.nhanvien import NhanVien
from ..models.nhatkyloi import NhatKyLoi
from ..models.thietbi import ThietBi
from ..permission.permission import IsAdmin
from ..utils.sql_error_handler import get_sql_error

BACKUP_FORMAT = settings.BACKUP_FORMAT
BACKUP_VERSION = settings.BACKUP_VERSION

# Restore bảng cha trước bảng có khóa ngoại.
BACKUP_MODELS = (
    ("nhanvien", NhanVien),
    ("thietbi", ThietBi),
    ("lienket", LienKet),
    ("hieusuat", ChiSoHieuSuat),
    ("lohong", LoHong),
    ("nhatkyloi", NhatKyLoi),
)


def create_backup():
    """Tạo snapshot dữ liệu mà không thay đổi database."""
    models_data = {}

    for name, model in BACKUP_MODELS:
        records = []

        for instance in model.objects.all():
            record = {}

            for field in model._meta.concrete_fields:
                record[field.name] = getattr(instance, field.attname)

            records.append(record)

        models_data[name] = records

    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "models": models_data,
    }


def backup_to_json():
    """Chuyển snapshot backup thành chuỗi JSON."""
    return json.dumps(
        create_backup(),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
        indent=2,
    )


def validate_backup(payload):
    """Kiểm tra cấu trúc file backup trước khi restore."""
    if not isinstance(payload, dict):
        raise ValueError("Dữ liệu backup phải là một object JSON.")

    if payload.get("format") != BACKUP_FORMAT:
        raise ValueError("Định dạng file backup không được hỗ trợ.")

    if payload.get("version") != BACKUP_VERSION:
        raise ValueError("Phiên bản file backup không được hỗ trợ.")

    models = payload.get("models")
    if not isinstance(models, dict):
        raise ValueError("File backup thiếu trường models.")

    supported_models = {name for name, _ in BACKUP_MODELS}
    unknown_models = set(models.keys()) - supported_models
    if unknown_models:
        raise ValueError(
            "File backup chứa model không được hỗ trợ: "
            + ", ".join(sorted(unknown_models))
        )

    for name, model in BACKUP_MODELS:
        records = models.get(name, [])
        if not isinstance(records, list):
            raise ValueError(f"Dữ liệu của model {name} phải là danh sách.")

        field_names = {field.name for field in model._meta.concrete_fields}
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"Bản ghi của model {name} không hợp lệ.")

            unknown_fields = set(record.keys()) - field_names
            if unknown_fields:
                raise ValueError(
                    f"Bản ghi {name} chứa trường không được hỗ trợ: "
                    + ", ".join(sorted(unknown_fields))
                )


@transaction.atomic
def restore_backup(payload):
    """
    Khôi phục dữ liệu từ file backup:
    - Bản ghi đã tồn tại: bỏ qua, không cập nhật.
    - Bản ghi chưa tồn tại: thêm mới.
    - Có lỗi: rollback toàn bộ transaction.
    """
    validate_backup(payload)
    restored = {}

    for name, model in BACKUP_MODELS:
        records = payload["models"].get(name, [])
        primary_key = model._meta.pk.name

        added_count = 0
        skipped_count = 0

        for record in records:
            if primary_key not in record:
                raise ValueError(f"Bản ghi {name} thiếu khóa chính '{primary_key}'.")

            converted_values = {}

            for field in model._meta.concrete_fields:
                if field.name not in record:
                    continue

                try:
                    converted_values[field.name] = field.to_python(record[field.name])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Giá trị trường '{field.name}' "
                        f"của model '{name}' không hợp lệ."
                    ) from exc

            pk_value = converted_values.pop(primary_key)

            _, created = model.objects.get_or_create(
                **{primary_key: pk_value},
                defaults=converted_values,
            )

            if created:
                added_count += 1
            else:
                skipped_count += 1

        restored[name] = {
            "added": added_count,
            "skipped": skipped_count,
        }

    return restored


@api_view(["GET"])
@permission_classes([IsAdmin])
def api_backup_database(request):
    """Tải toàn bộ dữ liệu được hỗ trợ thành file JSON."""
    try:
        response = HttpResponse(
            backup_to_json(),
            content_type="application/json; charset=utf-8",
        )
        response["Content-Disposition"] = 'attachment; filename="qlmvt_backup.json"'
        return response
    except Exception as exc:
        message, status_code = get_sql_error(exc)
        return JsonResponse({"error": message}, status=status_code)


@api_view(["POST"])
@permission_classes([IsAdmin])
def api_restore_database(request):
    """Khôi phục dữ liệu từ file JSON backup."""
    backup_file = request.FILES.get("file")

    if backup_file is None:
        return JsonResponse(
            {"error": "Vui lòng tải lên file backup JSON."},
            status=400,
        )

    try:
        if backup_file.size == 0:
            return JsonResponse(
                {"error": "File backup đang trống."},
                status=400,
            )

        try:
            payload = json.load(backup_file)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse(
                {"error": "File backup không phải JSON hợp lệ."},
                status=400,
            )

        restored = restore_backup(payload)

        return JsonResponse(
            {
                "message": "Khôi phục dữ liệu thành công.",
                "data": restored,
            },
            status=200,
        )

    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    except Exception as exc:
        message, status_code = get_sql_error(exc)
        return JsonResponse(
            {"error": message},
            status=status_code,
        )

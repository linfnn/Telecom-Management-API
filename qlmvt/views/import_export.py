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

IMPORT_EXPORT_FORMAT = settings.IMPORT_EXPORT_FORMAT
IMPORT_EXPORT_VERSION = settings.IMPORT_EXPORT_VERSION

IMPORT_EXPORT_MODELS = {
    "nhanvien": NhanVien,
    "thietbi": ThietBi,
    "lienket": LienKet,
    "hieusuat": ChiSoHieuSuat,
    "lohong": LoHong,
    "nhatkyloi": NhatKyLoi,
}


def get_model(model_name):
    """Lấy model được hỗ trợ cho thao tác import hoặc export."""
    model = IMPORT_EXPORT_MODELS.get(model_name)
    if model is None:
        raise ValueError(f"Model '{model_name}' không được hỗ trợ.")
    return model


def export_model(model_name):
    """Tạo dữ liệu export cho một model."""
    model = get_model(model_name)
    records = []

    for instance in model.objects.all():
        record = {}

        for field in model._meta.concrete_fields:
            record[field.name] = getattr(instance, field.attname)

        records.append(record)

    return {
        "format": IMPORT_EXPORT_FORMAT,
        "version": IMPORT_EXPORT_VERSION,
        "model": model_name,
        "records": records,
    }


def export_model_to_json(model_name):
    """Chuyển dữ liệu export thành chuỗi JSON."""
    return json.dumps(
        export_model(model_name),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
        indent=2,
    )


def validate_import_data(payload, model_name):
    """Kiểm tra cấu trúc và các trường của dữ liệu import."""
    if not isinstance(payload, dict):
        raise ValueError("Dữ liệu import phải là một object JSON.")

    if payload.get("format") != IMPORT_EXPORT_FORMAT:
        raise ValueError("Định dạng file import không được hỗ trợ.")

    if payload.get("version") != IMPORT_EXPORT_VERSION:
        raise ValueError("Phiên bản file import không được hỗ trợ.")

    if payload.get("model") != model_name:
        raise ValueError("Model trong file import không khớp với API.")

    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Trường 'records' phải là một danh sách.")

    model = get_model(model_name)
    field_names = {field.name for field in model._meta.concrete_fields}

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Bản ghi thứ {index + 1} không hợp lệ.")

        unknown_fields = set(record.keys()) - field_names
        if unknown_fields:
            raise ValueError(
                f"Bản ghi thứ {index + 1} chứa trường không được hỗ trợ: "
                + ", ".join(sorted(unknown_fields))
            )


@transaction.atomic
def import_model(model_name, payload):
    """
    Import dữ liệu vào model, cập nhật bản ghi có sẵn hoặc tạo bản ghi mới.

    Không xóa dữ liệu hiện có; lỗi sẽ rollback toàn bộ transaction.
    """
    validate_import_data(payload, model_name)

    model = get_model(model_name)
    primary_key = model._meta.pk.name
    created_count = 0
    updated_count = 0
    records = payload["records"]

    for record in records:
        values = {}

        for field in model._meta.concrete_fields:
            if field.name not in record:
                continue

            try:
                values[field.name] = field.to_python(record[field.name])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Giá trị trường '{field.name}' "
                    f"của model '{model_name}' không hợp lệ."
                ) from exc

        if primary_key not in values:
            raise ValueError(f"Bản ghi thiếu khóa chính '{primary_key}'.")

        primary_key_value = values.pop(primary_key)
        _, created = model.objects.update_or_create(
            **{primary_key: primary_key_value},
            defaults=values,
        )

        if created:
            created_count += 1
        else:
            updated_count += 1

    return {
        "model": model_name,
        "total": len(records),
        "created": created_count,
        "updated": updated_count,
    }


@api_view(["GET"])
@permission_classes([IsAdmin])
def api_export_table(request, model_name):
    """Export dữ liệu của model thành file JSON."""
    try:
        response = HttpResponse(
            export_model_to_json(model_name),
            content_type="application/json; charset=utf-8",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{model_name}_export.json"'
        )
        return response
    except ValueError as exc:
        message, _ = get_sql_error(exc)
        return JsonResponse({"error": message}, status=400)
    except Exception as exc:
        message, status_code = get_sql_error(exc)
        return JsonResponse({"error": message}, status=status_code)


@api_view(["POST"])
@permission_classes([IsAdmin])
def api_import_table(request, model_name):
    """Import dữ liệu từ file JSON được upload."""
    try:
        get_model(model_name)

        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            raise ValueError("Vui lòng upload file JSON với key 'file'.")

        if not uploaded_file.name.lower().endswith(".json"):
            raise ValueError("File import phải có định dạng .json.")

        try:
            payload = json.loads(uploaded_file.read().decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ValueError("File JSON phải sử dụng encoding UTF-8.") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("File không phải JSON hợp lệ.") from exc

        result = import_model(model_name, payload)
        return JsonResponse(
            {
                "message": f"Import dữ liệu {model_name} thành công.",
                "data": result,
            },
            status=200,
        )
    except ValueError as exc:
        message, _ = get_sql_error(exc)
        return JsonResponse({"error": message}, status=400)
    except Exception as exc:
        message, status_code = get_sql_error(exc)
        return JsonResponse({"error": message}, status=status_code)

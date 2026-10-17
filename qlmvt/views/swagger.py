from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def swagger_ui(request):
    return render(request, "qlmvt/swagger.html")


@require_GET
def swagger_schema(request):
    schema_path = Path(settings.BASE_DIR) / "swagger.yaml"
    return HttpResponse(
        schema_path.read_text(encoding="utf-8"),
        content_type="application/yaml; charset=utf-8",
    )

import ipaddress
import logging
import platform
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.core.cache import cache
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from ..models.hieusuat import ChiSoHieuSuat
from ..models.lienket import LienKet
from ..models.thietbi import ThietBi

logger = logging.getLogger(__name__)

SNAPSHOT_CACHE_KEY = "network-monitor-snapshot-v1"
SNAPSHOT_CACHE_SECONDS = 10
PING_TIMEOUT_SECONDS = 2
MAX_CONCURRENT_PINGS = 16
PING_LATENCY_PATTERN = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)


def _unknown_probe(message: str) -> dict[str, Any]:
    return {
        "status": "UNKNOWN",
        "latency_ms": None,
        "sample_loss_percent": None,
        "message": message,
    }


def probe_ip_address(address: str | None) -> dict[str, Any]:
    """Probe one configured IPv4 address without accepting arbitrary request targets."""
    if not address:
        return _unknown_probe("Thiết bị chưa khai báo địa chỉ IP.")

    try:
        parsed_address = ipaddress.ip_address(address.strip())
    except ValueError:
        return _unknown_probe("Địa chỉ IP cấu hình không hợp lệ.")

    if parsed_address.version != 4:
        return _unknown_probe("Backend hiện chỉ hỗ trợ kiểm tra IPv4.")

    command = ["ping"]
    if platform.system() == "Windows":
        command.extend(["-n", "1", "-w", str(PING_TIMEOUT_SECONDS * 1000)])
    elif platform.system() == "Darwin":
        command.append("-n")
        command.extend(["-c", "1", "-W", str(PING_TIMEOUT_SECONDS * 1000)])
    else:
        command.append("-n")
        command.extend(["-c", "1", "-W", str(PING_TIMEOUT_SECONDS)])
    command.append(str(parsed_address))

    started_at = time.monotonic()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=PING_TIMEOUT_SECONDS + 1,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "NO_RESPONSE",
            "latency_ms": None,
            "sample_loss_percent": 100,
            "message": "Không nhận được phản hồi ICMP trong thời gian chờ.",
        }
    except OSError:
        logger.exception("Unable to execute the system ping command")
        return _unknown_probe("Máy chủ chưa cài hoặc không chạy được lệnh ping.")

    if result.returncode == 1:
        return {
            "status": "NO_RESPONSE",
            "latency_ms": None,
            "sample_loss_percent": 100,
            "message": "Thiết bị không phản hồi ICMP.",
        }
    if result.returncode != 0:
        logger.warning(
            "Ping command failed for configured device IP with exit code %s",
            result.returncode,
        )
        return _unknown_probe("Lệnh ping không thể hoàn tất phép kiểm tra.")

    output = f"{result.stdout}\n{result.stderr}"
    latency_match = PING_LATENCY_PATTERN.search(output)
    latency_ms = (
        float(latency_match.group(1))
        if latency_match
        else round((time.monotonic() - started_at) * 1000, 2)
    )
    return {
        "status": "RESPONSIVE",
        "latency_ms": latency_ms,
        "sample_loss_percent": 0,
        "message": "Thiết bị phản hồi ICMP.",
    }


def _latest_metrics_query():
    return ChiSoHieuSuat.objects.filter(ma_tb_id=OuterRef("pk")).order_by(
        "-thoi_gian_ghi_nhan", "-ma_cs"
    )


def _get_snapshot_data() -> dict[str, Any]:
    latest_metrics = _latest_metrics_query()
    devices = list(
        ThietBi.objects.annotate(
            latest_metric_time=Subquery(
                latest_metrics.values("thoi_gian_ghi_nhan")[:1]
            ),
            latest_latency=Subquery(latest_metrics.values("do_tre")[:1]),
            latest_packet_loss=Subquery(latest_metrics.values("mat_goi")[:1]),
            latest_bandwidth=Subquery(
                latest_metrics.values("bang_thong_su_dung")[:1]
            ),
        ).order_by("ma_tb")
    )

    with ThreadPoolExecutor(
        max_workers=min(MAX_CONCURRENT_PINGS, max(len(devices), 1))
    ) as executor:
        probes = list(executor.map(probe_ip_address, (device.dia_chi_ip for device in devices)))

    device_rows = []
    for device, probe in zip(devices, probes, strict=True):
        device_rows.append(
            {
                "MaTB": device.ma_tb,
                "MaMonitor": device.ma_tb,
                "TenTB": device.ten_tb or "",
                "LoaiTB": device.loai_tb or "",
                "DiaChiIP": device.dia_chi_ip or "",
                "ViTri": device.vi_tri or "",
                "TrangThai": device.trang_thai or "",
                "TinhTrang": device.tinh_trang or "",
                "PowerState": "UNKNOWN",
                "MonitorState": probe["status"],
                "PingLatencyMs": probe["latency_ms"],
                "PingSampleLossPercent": probe["sample_loss_percent"],
                "PingStatusMessage": probe["message"],
                "LatestMetricTime": (
                    device.latest_metric_time.isoformat()
                    if device.latest_metric_time
                    else None
                ),
                "LatestLatencyMs": device.latest_latency,
                "LatestPacketLossPercent": device.latest_packet_loss,
                "LatestBandwidthUsage": device.latest_bandwidth,
                "LastSeen": None,
                "CPUPercent": None,
                "RAMPercent": None,
                "Temperature": None,
                "UptimeSeconds": None,
            }
        )

    links = LienKet.objects.select_related("matb_goc", "matb_dich").order_by("ma_lk")
    link_rows = [
        {
            "MaLK": link.ma_lk,
            "MaTB_Goc": link.matb_goc_id,
            "MaTB_Dich": link.matb_dich_id,
            "TenTB_Goc": link.matb_goc.ten_tb if link.matb_goc else None,
            "TenTB_Dich": link.matb_dich.ten_tb if link.matb_dich else None,
            "BangThongToiDa": link.bang_thong_toi_da,
            "TrangThai": "Chưa có dữ liệu",
            "MonitorState": "UNKNOWN",
            "StatusReason": "Chưa có controller hoặc nguồn telemetry liên kết.",
        }
        for link in links
    ]

    return {
        "success": True,
        "serverTime": timezone.now().isoformat(),
        "devices": device_rows,
        "links": link_rows,
    }


def get_network_monitor_snapshot() -> dict[str, Any]:
    snapshot = cache.get(SNAPSHOT_CACHE_KEY)
    if snapshot is None:
        snapshot = _get_snapshot_data()
        cache.set(SNAPSHOT_CACHE_KEY, snapshot, SNAPSHOT_CACHE_SECONDS)
    return snapshot


def diagnose_device(device: ThietBi) -> dict[str, Any]:
    probe = probe_ip_address(device.dia_chi_ip)
    configured_status_ok = (device.trang_thai or "").strip().casefold() == "hoạt động"
    condition_ok = (device.tinh_trang or "").strip().casefold() not in {
        "",
        "lỗi",
        "hỏng",
    }
    reachable = probe["status"] == "RESPONSIVE"
    checks = [
        {
            "label": "Kết nối ICMP",
            "detail": probe["message"],
            "ok": reachable,
            "warning": not reachable,
        },
        {
            "label": "Trạng thái khai báo",
            "detail": device.trang_thai or "Chưa có dữ liệu",
            "ok": configured_status_ok,
            "warning": not configured_status_ok,
        },
        {
            "label": "Tình trạng khai báo",
            "detail": device.tinh_trang or "Chưa có dữ liệu",
            "ok": condition_ok,
            "warning": not condition_ok,
        },
    ]
    healthy = reachable and configured_status_ok and condition_ok
    return {
        "success": True,
        "healthy": healthy,
        "status": "HEALTHY" if healthy else "WARNING",
        "checkedAt": timezone.now().isoformat(),
        "checks": checks,
    }

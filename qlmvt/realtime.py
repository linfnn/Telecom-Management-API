import asyncio
import logging
import time
from collections.abc import Mapping

import socketio
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from socketio.exceptions import ConnectionRefusedError

from .services.network_monitor_service import get_network_monitor_snapshot

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 30
MAX_TOKEN_LENGTH = 8192

socketio_server = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.SOCKETIO_ALLOWED_ORIGINS,
    logger=False,
    engineio_logger=False,
)

_connection_expirations: dict[str, float] = {}
_snapshot_tasks: dict[str, asyncio.Task] = {}


def _validate_access_token(raw_token: str) -> float:
    authentication = JWTAuthentication()
    validated_token = authentication.get_validated_token(raw_token)
    user = authentication.get_user(validated_token)
    if not user.is_active:
        raise AuthenticationFailed("Tài khoản đã bị khóa.")
    return float(validated_token["exp"])


def _execute_database_operation(operation, *args):
    def run():
        close_old_connections()
        try:
            return operation(*args)
        finally:
            close_old_connections()

    return sync_to_async(run, thread_sensitive=True)()


async def _authenticate_token(raw_token: str) -> float:
    return await _execute_database_operation(_validate_access_token, raw_token)


async def _load_snapshot():
    return await _execute_database_operation(get_network_monitor_snapshot)


@socketio_server.event
async def connect(sid, environ, auth=None):
    token = auth.get("token") if isinstance(auth, Mapping) else None
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        raise ConnectionRefusedError("unauthorized")

    try:
        expires_at = await _authenticate_token(token)
    except (AuthenticationFailed, InvalidToken) as error:
        raise ConnectionRefusedError("unauthorized") from error

    _connection_expirations[sid] = expires_at
    return True


@socketio_server.on("subscribe_network_monitor")
async def subscribe_network_monitor(sid):
    expires_at = _connection_expirations.get(sid)
    if expires_at is None:
        await socketio_server.disconnect(sid)
        return

    existing_task = _snapshot_tasks.get(sid)
    if existing_task and not existing_task.done():
        return

    _snapshot_tasks[sid] = asyncio.create_task(
        _stream_snapshots(sid, expires_at)
    )


async def _stream_snapshots(sid: str, expires_at: float):
    while True:
        if time.time() >= expires_at:
            await socketio_server.emit(
                "auth_expired",
                {"message": "Phiên đăng nhập đã hết hạn."},
                to=sid,
            )
            await socketio_server.disconnect(sid)
            return

        try:
            snapshot = await _load_snapshot()
            await socketio_server.emit("network_snapshot", snapshot, to=sid)
        except Exception:
            logger.exception("Unable to load network monitor snapshot")
            await socketio_server.emit(
                "network_error",
                {"message": "Không tải được dữ liệu giám sát mạng."},
                to=sid,
            )

        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)


@socketio_server.event
async def disconnect(sid, reason=None):
    _connection_expirations.pop(sid, None)
    task = _snapshot_tasks.pop(sid, None)
    if task is not None and task is not asyncio.current_task():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket


INSTANCE_SERVICE_NAME = "wemedia_baby_single_instance_v1"


def another_instance_is_running(service_name: str = INSTANCE_SERVICE_NAME) -> bool:
    check_socket = QLocalSocket()
    check_socket.connectToServer(service_name)
    if not check_socket.waitForConnected(500):
        return False

    logging.info("Detected an existing instance; exiting current process.")
    try:
        print(
            "\nWeMediaBaby is already running. This process will exit and try to activate "
            "the existing window.\n",
            file=sys.stderr,
        )
    except Exception:
        pass
    check_socket.disconnectFromServer()
    return True


def create_single_instance_server(
    service_name: str = INSTANCE_SERVICE_NAME,
) -> QLocalServer:
    local_server = QLocalServer()
    local_server.removeServer(service_name)
    if not local_server.listen(service_name):
        logging.warning(
            "Failed to start single-instance listener: %s",
            local_server.errorString(),
        )
    else:
        logging.info("Single-instance listener started: %s", service_name)
    return local_server


def connect_activation_handler(local_server: QLocalServer, activate: Callable[[], None]) -> None:
    def handle_activation() -> None:
        logging.info("Received activation request from another instance.")
        while local_server.hasPendingConnections():
            conn = local_server.nextPendingConnection()
            conn.close()
        activate()

    if local_server.isListening():
        local_server.newConnection.connect(handle_activation)

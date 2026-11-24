"""Локальный релей: на пути до VPS что-то режет соединение, если клиент SSH
отправляет свой баннер первым. Релей дожидается баннера сервера, и только потом
прокидывает данные клиента.

Использование: python ssh_relay.py  [локальный порт]
Затем:         ssh -p 2222 -i <ключ> root@127.0.0.1
"""

import socket
import sys
import threading

REMOTE = ("138.124.32.65", 22)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 2222


def pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while chunk := src.recv(65536):
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(local: socket.socket) -> None:
    remote = socket.create_connection(REMOTE, timeout=10)
    # 1) клиент уже прислал свой баннер — копим его в буфере
    buffer = b""
    local.settimeout(0.2)
    try:
        buffer = local.recv(4096)
    except OSError:
        pass
    local.settimeout(None)

    # 2) берём баннер сервера, отдаём клиенту
    remote.settimeout(10)
    banner = b""
    while not banner.endswith(b"\n"):
        banner += remote.recv(1)
    local.sendall(banner)

    # 3) только теперь пускаем данные клиента
    if buffer:
        remote.sendall(buffer)
    threading.Thread(target=pump, args=(remote, local), daemon=True).start()
    pump(local, remote)


def safe_handle(local: socket.socket) -> None:
    try:
        handle(local)
    except Exception as exc:
        print(f"conn failed: {exc!r}", flush=True)
        try:
            local.close()
        except OSError:
            pass


def main() -> None:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(16)
    print(f"relay 127.0.0.1:{PORT} -> {REMOTE[0]}:{REMOTE[1]}")
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=safe_handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()

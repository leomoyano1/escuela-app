import threading

import webview
from werkzeug.serving import make_server

from app import create_app


server = None


def serve_app(app) -> None:
    """Levantar el servidor Flask local para la interfaz web."""
    global server
    server = make_server("127.0.0.1", 5000, app)
    server.serve_forever()


def launch_desktop() -> None:
    """Abrir la aplicación con PyWebView en una ventana nativa."""
    app = create_app()
    threading.Thread(target=serve_app, args=(app,), daemon=True).start()

    webview.create_window(
        "Galileo Galilei - Sistema Integrado de Gestión Escolar",
        "http://127.0.0.1:5000",
        width=1400,
        height=900,
        resizable=True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    launch_desktop()

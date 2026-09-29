import os
import site
import sys
import threading


scriptdir, script = os.path.split(os.path.abspath(__file__))
pkgdir = os.path.join(scriptdir, "pkgs")
site.addsitedir(pkgdir)
sys.path.insert(0, pkgdir)
sys.path.insert(0, scriptdir)


from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from kiwiscribe_splash import SPLASH_GIF_FILENAME, finish_splash_screen, show_splash_screen


def main():
    app = QApplication(sys.argv)
    try:
        app.setStyle("Fusion")
    except Exception as e:
        print(f"Não foi possível aplicar estilo: {e}")

    splash = show_splash_screen(app, os.path.join(scriptdir, SPLASH_GIF_FILENAME))

    # O import de Kiwiscribe carrega os SDKs pesados; fora da thread da UI a animação não congela.
    state = {}

    def load_app_module():
        try:
            import Kiwiscribe
            Kiwiscribe.cleanup_old_logs(Kiwiscribe.get_log_dir())
            state["module"] = Kiwiscribe
        except BaseException as e:
            state["error"] = e

    loader = threading.Thread(target=load_app_module, daemon=True)
    loader.start()

    poll = QTimer()

    def on_poll():
        if loader.is_alive():
            return
        poll.stop()
        if "error" in state:
            if splash is not None:
                splash.close()
            QMessageBox.critical(None, "Kiwiscribe", f"Falha ao iniciar o Kiwiscribe:\n{state['error']!r}")
            app.exit(1)
            return
        state["window"] = state["module"].TranscriptionWindow()
        finish_splash_screen(splash, state["window"])

    poll.timeout.connect(on_poll)
    poll.start(30)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

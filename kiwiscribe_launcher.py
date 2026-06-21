import os
import site
import sys


scriptdir, script = os.path.split(os.path.abspath(__file__))
pkgdir = os.path.join(scriptdir, "pkgs")
site.addsitedir(pkgdir)
sys.path.insert(0, pkgdir)
sys.path.insert(0, scriptdir)


from Kiwiscribe import QApplication, TranscriptionWindow, cleanup_old_logs, get_log_dir


def main():
    app = QApplication(sys.argv)
    try:
        app.setStyle("Fusion")
    except Exception as e:
        print(f"Não foi possível aplicar estilo: {e}")

    log_dir = get_log_dir()
    cleanup_old_logs(log_dir)

    window = TranscriptionWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
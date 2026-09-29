import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor, QGuiApplication, QMovie, QPixmap
from PyQt6.QtWidgets import QLabel


SPLASH_GIF_FILENAME = "kiwi_scribe.gif"
# Limite de segurança caso a animação não chegue ao último quadro.
SPLASH_MAX_ANIMATION_MS = 10000


class AnimatedSplashScreen(QLabel):
    """Splash com GIF animado que toca uma vez e para no último quadro.

    Usa QLabel em vez de QSplashScreen: no Qt6/Windows, QSplashScreen.show()
    bloqueia ~1 s aguardando a exposição da janela.
    """

    def __init__(self, gif_path):
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._window = None
        self._animation_done = False
        self._movie = QMovie(gif_path, parent=self)
        if self._movie.isValid() and self._movie.frameCount() > 1:
            self._last_frame = self._movie.frameCount() - 1
            self._movie.frameChanged.connect(self._on_frame_changed)
            self.setMovie(self._movie)
            self._movie.jumpToFrame(0)
            self._movie.start()
            QTimer.singleShot(SPLASH_MAX_ANIMATION_MS, self._mark_animation_done)
        else:
            self._movie = None
            self.setPixmap(QPixmap(gif_path))
            self._animation_done = True
        self.adjustSize()
        self._center_on_screen()

    def _center_on_screen(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    def _on_frame_changed(self, frame_number):
        if frame_number >= self._last_frame:
            self._movie.setPaused(True)
            self._mark_animation_done()

    def _mark_animation_done(self):
        self._animation_done = True
        self._try_reveal()

    def mousePressEvent(self, event):
        self._mark_animation_done()

    def finish_when_ready(self, window):
        """Revela a janela principal assim que a animação terminar."""
        self._window = window
        self._try_reveal()

    def _try_reveal(self):
        if self._window is None or not self._animation_done:
            return
        window, self._window = self._window, None
        window.show()
        window.raise_()
        window.activateWindow()
        if self._movie is not None:
            self._movie.stop()
        self.close()


def show_splash_screen(app, gif_path):
    """Exibe a splash animada; devolve None se o GIF não existir."""
    if not os.path.isfile(gif_path):
        print(f"Aviso: splash GIF não encontrado em {gif_path}")
        return None

    splash = AnimatedSplashScreen(gif_path)
    splash.show()
    app.processEvents()
    return splash


def finish_splash_screen(splash, window):
    """Mostra a janela principal ao fim da animação (ou imediatamente, sem splash)."""
    if splash is None:
        window.show()
        return
    splash.finish_when_ready(window)

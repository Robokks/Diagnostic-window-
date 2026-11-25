import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication, QPushButton
from app import Window
from core import Store

def test_desktop_pages(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = Window(Store(tmp_path / 'gui.db'))
    try:
        next(b for b in win.findChildren(QPushButton) if b.text() == 'Enter isolated demo').click()
        win.tick()
        for i in range(7):
            win.navigate(i)
            win.tick()
            app.processEvents()
        assert win.role == 'Administrator'
        assert len(win.c['drives']) == 3
        win.inject()
        win.tick()
        assert win.active
        win.clear()
        win.tick()
        assert not win.active
    finally:
        win.close()
        win.receiver.join(3)

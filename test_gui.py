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

def test_startup_storage(tmp_path, monkeypatch):
    from app import open_store
    target = tmp_path / 'nested' / 'private'
    monkeypatch.setenv('SYSTEMWINDOW_DATA_DIR', str(target))
    store = open_store()
    assert (target / 'system.db').is_file()
    store.create('admin', 'long-password-123', 'Administrator')
    store.db.close()
    reopened = open_store()
    assert reopened.login('admin', 'long-password-123') == 'Administrator'
    reopened.db.close()

def test_denied_storage(tmp_path, monkeypatch):
    import pytest
    from pathlib import Path
    from app import open_store
    def denied(*args, **kwargs):
        raise PermissionError('Access denied')
    monkeypatch.setattr(Path, 'mkdir', denied)
    with pytest.raises(PermissionError):
        open_store(tmp_path / 'blocked')

def test_startup_cancel_on_denied(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    import app as module
    qt = QApplication.instance() or QApplication([])
    def denied(*args, **kwargs):
        raise PermissionError('Access denied')
    monkeypatch.setattr(module, 'open_store', denied)
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: 0)
    assert module.startup_store() is None

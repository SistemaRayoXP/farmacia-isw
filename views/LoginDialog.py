# main.py
# Requisitos: pip install PySide6
# Ejecuta: python main.py
from __future__ import annotations
import sqlite3
from database import sha256, DB_FILE
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

# ---------- Diálogo de Login ----------
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Acceso - Farmacia")
        self.setModal(True)
        self.user = QLineEdit()
        self.passw = QLineEdit()
        self.passw.setEchoMode(QLineEdit.Password)
        self.btn_ok = QPushButton("Ingresar")
        self.btn_cancel = QPushButton("Cancelar")

        form = QFormLayout()
        form.addRow("Usuario:", self.user)
        form.addRow("Contraseña:", self.passw)

        btns = QHBoxLayout()
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(btns)

        self.btn_ok.clicked.connect(self.try_login)
        self.btn_cancel.clicked.connect(self.reject)

    def try_login(self):
        u = self.user.text().strip()
        p = self.passw.text()
        if not u or not p:
            QMessageBox.warning(self, "Faltan datos", "Escribe usuario y contraseña.")
            return

        # Validación directa a SQLite para no depender de QSql*
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute(
            "SELECT usuario_id FROM usuarios WHERE usuario=? AND password_hash=?",
            (u, sha256(p)),
        )
        row = cur.fetchone()
        conn.close()

        if row:
            self.accept()
        else:
            QMessageBox.critical(
                self, "Acceso denegado", "Usuario o contraseña incorrectos."
        )
from __future__ import annotations
from views.CrudDialog import CrudDialog
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

# ---------- Ventana Principal ----------
# Antes: la renombraste a CrudDialog por error. Esto vuelve a ser MainWindow (QMainWindow).
class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Farmacia de especialidades CUCEI")
        self.resize(1000, 650)

        # Centro con imagen genérica / texto
        lbl = QLabel(
            "Gestor de la farmacia\n\nUsa el menú para gestionar las ventas, compras, artículos y demás."
        )
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 20px;")
        self.setCentralWidget(lbl)

        # Menú Archivo
        m_file = self.menuBar().addMenu("&Archivo")
        act_logout = QAction("Cerrar sesión", self)
        act_exit = QAction("Salir", self)
        m_file.addAction(act_logout)
        m_file.addSeparator()
        m_file.addAction(act_exit)

        act_logout.triggered.connect(self.request_logout)
        act_exit.triggered.connect(self.close)

        # Menú Catálogos
        m_cat = self.menuBar().addMenu("&Catálogos")
        self.add_catalog_action(m_cat, "Usuarios", "usuarios")
        self.add_catalog_action(m_cat, "Clientes", "clientes")
        self.add_catalog_action(m_cat, "Vehículos", "vehiculos")
        self.add_catalog_action(m_cat, "Piezas", "piezas")

        # Menú Operación
        m_op = self.menuBar().addMenu("&Operación")
        self.add_catalog_action(m_op, "Reparaciones", "reparaciones")

        # Menú Ayuda
        m_help = self.menuBar().addMenu("Ay&uda")
        about = QAction("Acerca de…", self)
        m_help.addAction(about)
        about.triggered.connect(
            lambda: QMessageBox.information(
                self,
                "Acerca de",
                "Demo de IU en Qt para Farmacia.\nLogin + Menús + CRUD con QSqlTableModel.",
            )
        )

        # Barra de herramientas opcional
        tb = QToolBar("Accesos")
        self.addToolBar(tb)
        tb.addAction(act_logout)

    def add_catalog_action(self, menu, label, table):
        act = QAction(label, self)
        menu.addAction(act)
        act.triggered.connect(lambda: self.open_crud(table, label))

    def open_crud(self, table: str, label: str):
        dlg = CrudDialog(table, f"{label} - CRUD", parent=self)
        dlg.exec()

    def request_logout(self):
        # Confirmación escueta
        if (
            QMessageBox.question(
                self, "Cerrar sesión", "¿Volver a la pantalla de login?"
            )
            == QMessageBox.Yes
        ):
            self.logout_requested.emit()
            self.close()
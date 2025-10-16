# main.py
# Requisitos: pip install PySide6
# Ejecuta: python main.py
from __future__ import annotations
import sys
from database import init_sqlite_file, open_qt_db_or_die
from views.LoginDialog import LoginDialog
from views.MainWindow import MainWindow
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
)


# ---------- Bucle de app con ciclo de login ----------
def main():
    init_sqlite_file()
    app = QApplication(sys.argv)
    open_qt_db_or_die()

    while True:
        login = LoginDialog()
        if login.exec() == QDialog.Accepted:
            mainw = MainWindow()
            # Si el usuario cierra sesión, volvemos al login
            # Conectamos la señal por si quieres reaccionar a logout desde el main.
            mainw.logout_requested.connect(lambda: None)
            mainw.show()

            # Ejecuta el bucle hasta que cierre la ventana principal
            app.exec()

            # Si cerró la app completa con Alt+F4 o menú Salir, rompemos ciclo
            # Si fue "Cerrar sesión", simplemente reitera y muestra el login de nuevo.
            # Detección simple: si no hay ventanas, salir.
            if not QApplication.topLevelWidgets():
                break
        else:
            break


if __name__ == "__main__":
    main()

from PySide6.QtCore import Signal, QThread
from PySide6.QtWidgets import (
    QMessageBox
)
import socket
from threading import Event

class receiveThread(QThread):
    rcv_data = Signal(str)
    def __init__(self, par, soc: socket.socket):
        super().__init__()
        self.par = par
        self.soc = soc
        self.is_running = Event()
        self.is_running.set()
    
    def run(self):
        while self.is_running.is_set():
            try:
                rcv = self.soc.recv(1024).decode().strip()
                if rcv and rcv.startswith("ariyflow/HNU-ICU@"):
                    rcv = rcv[17:]
                    print(f"receive data: {rcv}")
                    self.rcv_data.emit(rcv)
            except:
                pass
            
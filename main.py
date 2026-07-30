"""Application entry point for Pi Provider Manager."""

import tkinter as tk
from tkinter import messagebox

from config_manager import ConfigManager
from database import Database
from ui_main import MainWindow


def main():
    root = tk.Tk()
    try:
        database = Database()
        config_manager = ConfigManager(database)
        MainWindow(root, config_manager, database)
    except Exception as error:
        root.withdraw()
        messagebox.showerror("Pi Provider Manager", "应用启动失败：\n%s" % error, parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

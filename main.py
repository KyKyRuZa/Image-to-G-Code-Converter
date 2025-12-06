import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox

from gui import ImageToGCodeApp

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageToGCodeApp(root)
    root.geometry("1100x750")
    root.minsize(900, 650)
    root.mainloop()
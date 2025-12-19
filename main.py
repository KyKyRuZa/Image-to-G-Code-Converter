import tkinter as tk
from tkinter import ttk, messagebox
from GUI import ImageToGCodeApp
import sys

def main():
    root = tk.Tk()
    
    style = ttk.Style()
    if sys.platform == "win32":
        style.theme_use('vista')
    elif sys.platform == "darwin":
        style.theme_use('aqua')
    else:
        style.theme_use('clam')
        
    app = ImageToGCodeApp(root)
    
    root.geometry("1200x800")
    root.minsize(1000, 700)
    
    def on_closing():
        if app.processing:
            if messagebox.askokcancel("Закрытие", "Обработка еще выполняется. Закрыть программу?"):
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    root.mainloop()

if __name__ == "__main__":
    main()
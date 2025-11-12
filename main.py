import tkinter as tk
from tkinter import filedialog, scrolledtext
import numpy as np
from PIL import Image, ImageTk
import cv2
from image import process_image
from gcode import generate_gcode

class ImageToGCodeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image to G-Code Converter")
        
        self.original_image = None
        self.processed_image = None
        self.gcode = ""
        self.scale_factor = 0.5
        self.canny_min = 50
        self.canny_max = 150
        self.pen_up_z = 5.0
        self.pen_down_z = -2.0
        self.feed_rate = 2000
        
        self.create_widgets()
        
    def create_widgets(self):
        params_frame = tk.LabelFrame(self.root, text="Conversion Parameters")
        params_frame.pack(pady=5, padx=10, fill=tk.X)
        
        tk.Label(params_frame, text="Scale Factor:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.scale_entry = tk.Entry(params_frame, width=10)
        self.scale_entry.insert(0, str(self.scale_factor))
        self.scale_entry.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(params_frame, text="Canny Min:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.canny_min_entry = tk.Entry(params_frame, width=10)
        self.canny_min_entry.insert(0, str(self.canny_min))
        self.canny_min_entry.grid(row=0, column=3, padx=5, pady=5)
        
        tk.Label(params_frame, text="Canny Max:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.canny_max_entry = tk.Entry(params_frame, width=10)
        self.canny_max_entry.insert(0, str(self.canny_max))
        self.canny_max_entry.grid(row=0, column=5, padx=5, pady=5)
        
        tk.Label(params_frame, text="Pen Up Z:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.pen_up_entry = tk.Entry(params_frame, width=10)
        self.pen_up_entry.insert(0, str(self.pen_up_z))
        self.pen_up_entry.grid(row=1, column=1, padx=5, pady=5)
        
        tk.Label(params_frame, text="Pen Down Z:").grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        self.pen_down_entry = tk.Entry(params_frame, width=10)
        self.pen_down_entry.insert(0, str(self.pen_down_z))
        self.pen_down_entry.grid(row=1, column=3, padx=5, pady=5)
        
        tk.Label(params_frame, text="Feed Rate:").grid(row=1, column=4, padx=5, pady=5, sticky=tk.W)
        self.feed_rate_entry = tk.Entry(params_frame, width=10)
        self.feed_rate_entry.insert(0, str(self.feed_rate))
        self.feed_rate_entry.grid(row=1, column=5, padx=5, pady=5)
        
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)
        
        self.select_btn = tk.Button(button_frame, text="Select Image", command=self.select_image)
        self.select_btn.pack(side=tk.LEFT, padx=5)
        
        self.process_btn = tk.Button(button_frame, text="Process Image", command=self.process_image)
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        self.save_btn = tk.Button(button_frame, text="Save G-Code", command=self.save_gcode)
        self.save_btn.pack(side=tk.LEFT, padx=5)
        
        image_frame = tk.Frame(self.root)
        image_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        
        self.original_canvas = tk.Canvas(image_frame, width=400, height=400, bg="gray")
        self.original_canvas.pack(side=tk.LEFT, padx=10)
        
        self.processed_canvas = tk.Canvas(image_frame, width=400, height=400, bg="gray")
        self.processed_canvas.pack(side=tk.LEFT, padx=10)
        
        self.gcode_text = scrolledtext.ScrolledText(self.root, width=80, height=20)
        self.gcode_text.pack(pady=10, padx=10)
        
    def select_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp")])
        if file_path:
            self.original_image = Image.open(file_path)
            self.display_image(self.original_image, self.original_canvas)
            
            self.processed_image = None
            self.gcode = ""
            self.gcode_text.delete(1.0, tk.END)
    
    def display_image(self, image, canvas):
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width, canvas_height = 400, 400
            
        img_width, img_height = image.size
        ratio = min(canvas_width / img_width, canvas_height / img_height)
        new_width = int(img_width * ratio)
        new_height = int(img_height * ratio)
        
        resized_image = image.resize((new_width, new_height))
        photo = ImageTk.PhotoImage(resized_image)
        
        canvas.delete("all")
        canvas.create_image(canvas_width // 2, canvas_height // 2, image=photo)
        canvas.image = photo
    
    def process_image(self):
        if self.original_image is None:
            return
            
        try:
            self.scale_factor = float(self.scale_entry.get())
            self.pen_up_z = float(self.pen_up_entry.get())
            self.pen_down_z = float(self.pen_down_entry.get())
            self.feed_rate = int(self.feed_rate_entry.get())
        except ValueError:
            tk.messagebox.showerror("Invalid Input", "Please enter valid numeric values for all parameters.")
            return
            
        img = np.array(self.original_image)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        
        processed_img, contours, canny_min, canny_max = process_image(img)
        
        self.canny_min = canny_min
        self.canny_max = canny_max
        self.canny_min_entry.delete(0, tk.END)
        self.canny_min_entry.insert(0, str(self.canny_min))
        self.canny_max_entry.delete(0, tk.END)
        self.canny_max_entry.insert(0, str(self.canny_max))
        
        self.processed_image = Image.fromarray(cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB))
        self.display_image(self.processed_image, self.processed_canvas)
        
        self.gcode = generate_gcode(contours, 
                                   self.scale_factor,
                                   self.pen_up_z,
                                   self.pen_down_z,
                                   self.feed_rate)
        
        self.gcode_text.delete(1.0, tk.END)
        self.gcode_text.insert(tk.END, self.gcode)
    
    def save_gcode(self):
        if not self.gcode:
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".gcode",
            filetypes=[("G-Code files", "*.gcode"), ("All files", "*.*")]
        )
        if file_path:
            with open(file_path, "w") as f:
                f.write(self.gcode)

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageToGCodeApp(root)
    root.geometry("1000x700")
    root.mainloop()
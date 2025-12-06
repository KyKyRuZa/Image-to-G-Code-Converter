import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from PIL import Image, ImageTk, ImageDraw
import numpy as np
import os

import cv2
from image_processing import get_contours
from hatching import generate_hatching
from gcode_generator import generate_sketch_gcode
from utils import display_image_on_canvas, auto_adjust_scale

class ImageToGCodeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Плоттер: Карандашный рисунок + Контуры")
        
        self.original_image = None
        self.processed_image = None
        self.lines = []
        self.contours = []
        self.gcode = ""
        
        self.config = {
            "scale_factor": 0.3,
            "canny_min": 50,
            "canny_max": 150,
            "pen_up_z": 5.0,
            "pen_down_z": -0.5,
            "feed_rate": 800,
            "rapid_feed_rate": 2000,
            "work_area_x": 200,
            "work_area_y": 200,
            "hatch_density": 12,
            "hatch_angle": 45,
            "hatch_cross": True,
            "draw_contours": True,
            "draw_hatching": True,
            "optimize_order": True,
        }
        
        self.create_widgets()
        
    def create_widgets(self):
        params_frame = tk.LabelFrame(self.root, text="Параметры рисования")
        params_frame.pack(pady=5, padx=10, fill=tk.X)
        
        tk.Label(params_frame, text="Контуры - Canny Min:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.canny_min_slider = tk.Scale(params_frame, from_=0, to=255, orient=tk.HORIZONTAL, length=150)
        self.canny_min_slider.set(self.config["canny_min"])
        self.canny_min_slider.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(params_frame, text="Canny Max:").grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)
        self.canny_max_slider = tk.Scale(params_frame, from_=0, to=255, orient=tk.HORIZONTAL, length=150)
        self.canny_max_slider.set(self.config["canny_max"])
        self.canny_max_slider.grid(row=0, column=3, padx=5, pady=2)
        
        tk.Label(params_frame, text="Штриховка - Плотность:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.hatch_slider = tk.Scale(params_frame, from_=1, to=20, orient=tk.HORIZONTAL, length=150)
        self.hatch_slider.set(self.config["hatch_density"])
        self.hatch_slider.grid(row=1, column=1, padx=5, pady=2)
        
        tk.Label(params_frame, text="Угол (град):").grid(row=1, column=2, padx=5, pady=2, sticky=tk.W)
        self.angle_slider = tk.Scale(params_frame, from_=0, to=180, orient=tk.HORIZONTAL, length=150)
        self.angle_slider.set(self.config["hatch_angle"])
        self.angle_slider.grid(row=1, column=3, padx=5, pady=2)
        
        self.contours_var = tk.BooleanVar(value=self.config["draw_contours"])
        self.contours_check = tk.Checkbutton(params_frame, text="Рисовать контуры", variable=self.contours_var)
        self.contours_check.grid(row=2, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)
        
        self.hatch_var = tk.BooleanVar(value=self.config["draw_hatching"])
        self.hatch_check = tk.Checkbutton(params_frame, text="Рисовать штриховку", variable=self.hatch_var)
        self.hatch_check.grid(row=2, column=2, columnspan=2, padx=5, pady=2, sticky=tk.W)
        
        self.cross_var = tk.BooleanVar(value=self.config["hatch_cross"])
        self.cross_check = tk.Checkbutton(params_frame, text="Перекрестная штриховка", variable=self.cross_var)
        self.cross_check.grid(row=3, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)
        
        tk.Label(params_frame, text="Область X (мм):").grid(row=4, column=0, padx=5, pady=2, sticky=tk.W)
        self.work_x_entry = tk.Entry(params_frame, width=8)
        self.work_x_entry.insert(0, str(self.config["work_area_x"]))
        self.work_x_entry.grid(row=4, column=1, padx=5, pady=2)
        
        tk.Label(params_frame, text="Область Y (мм):").grid(row=4, column=2, padx=5, pady=2, sticky=tk.W)
        self.work_y_entry = tk.Entry(params_frame, width=8)
        self.work_y_entry.insert(0, str(self.config["work_area_y"]))
        self.work_y_entry.grid(row=4, column=3, padx=5, pady=2)
        
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="Загрузить", command=self.load_image, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Предпросмотр", command=self.process_image, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="G-код", command=self.generate_gcode, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Сохранить", command=self.save_gcode, width=12).pack(side=tk.LEFT, padx=5)
        
        image_frame = tk.Frame(self.root)
        image_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        
        orig_frame = tk.LabelFrame(image_frame, text="Исходное фото")
        orig_frame.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)
        self.original_canvas = tk.Canvas(orig_frame, width=400, height=400, bg="gray")
        self.original_canvas.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        proc_frame = tk.LabelFrame(image_frame, text="Результат")
        proc_frame.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)
        self.processed_canvas = tk.Canvas(proc_frame, width=400, height=400, bg="white")
        self.processed_canvas.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        gcode_frame = tk.LabelFrame(self.root, text="G-код")
        gcode_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.gcode_text = scrolledtext.ScrolledText(gcode_frame, width=80, height=15)
        self.gcode_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def load_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.tiff")]
        )
        if file_path:
            try:
                self.original_image = Image.open(file_path)
                display_image_on_canvas(self.original_image, self.original_canvas)
                self.status_var.set(f"Загружено: {os.path.basename(file_path)}")
                
                self.processed_image = None
                self.lines = []
                self.contours = []
                self.gcode = ""
                self.gcode_text.delete(1.0, tk.END)
                self.processed_canvas.delete("all")
                
                auto_adjust_scale(self.original_image, self.config)
                self.status_var.set(f"Размер: {self.original_image.size[0]}x{self.original_image.size[1]}px")
                
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить изображение: {str(e)}")
    
    def process_image(self):
        if self.original_image is None:
            messagebox.showwarning("Нет изображения", "Сначала загрузите изображение")
            return
        
        try:
            canny_min = int(self.canny_min_slider.get())
            canny_max = int(self.canny_max_slider.get())
            hatch_density = int(self.hatch_slider.get())
            hatch_angle = int(self.angle_slider.get())
            draw_contours = self.contours_var.get()
            draw_hatching = self.hatch_var.get()
            cross_hatch = self.cross_var.get()
            
            img_cv = np.array(self.original_image.convert('RGB'))[:, :, ::-1].copy()
            
            if draw_contours or draw_hatching:
                edges, self.contours = get_contours(img_cv, canny_min, canny_max)
            else:
                self.contours = []
            
            if draw_hatching:
                self.lines = generate_hatching(img_cv, hatch_density, hatch_angle, cross_hatch)
            else:
                self.lines = []
            
            self.create_preview_image(draw_contours)
            
            contour_count = len(self.contours) if self.contours else 0
            line_count = len(self.lines) if self.lines else 0
            
            self.status_var.set(f"Контуров: {contour_count}, Линий штриховки: {line_count}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка обработки: {str(e)}")
    
    def create_preview_image(self, draw_contours=True):
        if self.original_image is None:
            return
        
        img_width, img_height = self.original_image.size
        preview = Image.new('RGB', (img_width, img_height), (255, 255, 255))
        draw = ImageDraw.Draw(preview)
        
        for line in self.lines:
            if len(line) > 1:
                for i in range(len(line) - 1):
                    x1, y1 = line[i]
                    x2, y2 = line[i + 1]
                    draw.line([(x1, y1), (x2, y2)], fill=(70, 70, 70), width=1)
        
        if draw_contours and self.contours:
            for contour in self.contours:
                points = []
                for point in contour:
                    x, y = point[0]
                    points.append((x, y))
                
                if len(points) > 1:
                    for i in range(len(points) - 1):
                        x1, y1 = points[i]
                        x2, y2 = points[i + 1]
                        draw.line([(x1, y1), (x2, y2)], fill=(0, 0, 0), width=2)
                    if len(points) > 2:
                        x1, y1 = points[-1]
                        x2, y2 = points[0]
                        draw.line([(x1, y1), (x2, y2)], fill=(0, 0, 0), width=2)
        
        self.processed_image = preview
        display_image_on_canvas(preview, self.processed_canvas)
    
    def generate_gcode(self):
        if not self.lines and not self.contours:
            messagebox.showwarning("Нет данных", "Сначала обработайте изображение")
            return
        
        try:
            scale_factor = float(self.config["scale_factor"])
            pen_up_z = float(self.config["pen_up_z"])
            pen_down_z = float(self.config["pen_down_z"])
            feed_rate = float(self.config["feed_rate"])
            rapid_rate = float(self.config["rapid_feed_rate"])
            work_area_x = float(self.work_x_entry.get())
            work_area_y = float(self.work_y_entry.get())
            draw_contours = bool(self.contours_var.get())
            draw_hatching = bool(self.hatch_var.get())
            optimize_order = self.config["optimize_order"]
            
            self.gcode = generate_sketch_gcode(
                hatching_lines=self.lines,
                contours=self.contours,
                scale_factor=scale_factor,
                pen_up_z=pen_up_z,
                pen_down_z=pen_down_z,
                feed_rate=feed_rate,
                rapid_feed_rate=rapid_rate,
                draw_contours=draw_contours,
                draw_hatching=draw_hatching,
                work_area=(work_area_x, work_area_y),
                start_point=(10, 10),
                optimize_order=optimize_order
            )
            
            self.gcode_text.delete(1.0, tk.END)
            self.gcode_text.insert(tk.END, self.gcode)
            
            self.status_var.set(f"G-код сгенерирован. Линий: {len(self.lines)}, Контуров: {len(self.contours)}")
            
        except ValueError as e:
            messagebox.showerror("Ошибка ввода", f"Проверьте числовые параметры: {str(e)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка генерации: {str(e)}")
    
    def save_gcode(self):
        if not self.gcode:
            messagebox.showwarning("Нет G-кода", "Сначала сгенерируйте G-код")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".gcode",
            filetypes=[("G-код", "*.gcode *.nc"), ("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.gcode)
                
                messagebox.showinfo("Сохранено", f"Файл сохранен: {os.path.basename(file_path)}")
                
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {str(e)}")
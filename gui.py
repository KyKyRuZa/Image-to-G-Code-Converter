import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from PIL import Image, ImageTk, ImageDraw
import cv2
import numpy as np
import os
import threading
import time
from config import DEFAULT_CONFIG
from utils import display_image_on_canvas, auto_adjust_scale, validate_numeric_input
from image_processing import get_contours, generate_hatching
from gcode_generator import generate_sketch_gcode
from hershey_fonts import text_to_gcode_cyrillic, add_cyrillic_text_to_contours
from serial_port import ConnectionManager, SerialConnection

class ConfigManager:
    def __init__(self, default_config):
        self.config = default_config.copy()
        
    def update_from_ui(self, ui_elements):
        try:
            font_size_pt = float(ui_elements["font_size_entry"].get())
            font_scale = (font_size_pt / 12) * 0.4
            self.config.update({
                "canny_min": int(ui_elements["canny_min_slider"].get()),
                "canny_max": int(ui_elements["canny_max_slider"].get()),
                "hatch_density": int(ui_elements["hatch_slider"].get()),
                "hatch_angle": int(ui_elements["angle_slider"].get()),
                "draw_hatching": ui_elements["hatch_var"].get(),
                "hatch_cross": ui_elements["cross_var"].get(),
                "work_area_x": validate_numeric_input(ui_elements["work_x_entry"].get(), 50, 1000),
                "work_area_y": validate_numeric_input(ui_elements["work_y_entry"].get(), 50, 1000),
                "pen_up_z": validate_numeric_input(ui_elements["pen_up_entry"].get(), 1.0, 50.0),
                "pen_down_z": validate_numeric_input(ui_elements["pen_down_entry"].get(), -10.0, -0.1),
                "feed_rate": validate_numeric_input(ui_elements["feed_rate_entry"].get(), 100, 5000),
                "rapid_feed_rate": validate_numeric_input(ui_elements["rapid_rate_entry"].get(), 500, 10000),
                "min_contour_length": max(5, int(validate_numeric_input(ui_elements["min_contour_entry"].get(), 5, 1000))),
                "min_line_length": max(2, int(validate_numeric_input(ui_elements["min_line_entry"].get(), 2, 1000))),
                "font_scale": font_scale,  
                "font_spacing": float(ui_elements["font_spacing_slider"].get()),
                "text_position_x": float(ui_elements["text_pos_x_entry"].get()) / self.config["work_area_x"],
                "text_position_y": float(ui_elements["text_pos_y_entry"].get()) / self.config["work_area_y"],
                "text_align": ui_elements["align_var"].get(),
                "morph_kernel_size": max(1, int(validate_numeric_input(ui_elements["morph_kernel_entry"].get(), 1, 15, 3))),
                "morph_iterations": max(1, int(validate_numeric_input(ui_elements["morph_iter_entry"].get(), 1, 10, 1))),
                "blur_kernel": max(1, int(validate_numeric_input(ui_elements["blur_kernel_entry"].get(), 1, 25, 5))),
                "blur_sigma": max(0.1, float(validate_numeric_input(ui_elements["blur_sigma_entry"].get(), 0.1, 10.0, 1.0))),
            })
            return True
        except ValueError as e:
            messagebox.showerror("Ошибка ввода", f"Проверьте корректность параметров:\n{str(e)}")
            return False
            
    def reset_to_default(self, default_config):
        self.config = default_config.copy()
        return self.config

class PreviewRenderer:
    @staticmethod
    def create_image_preview(original_image, lines, contours, text_contours):
        if original_image is None:
            return None
            
        img_width, img_height = original_image.size
        preview = Image.new('RGB', (img_width, img_height), (255, 255, 255))
        draw = ImageDraw.Draw(preview)
        
        PreviewRenderer._draw_hatching(draw, lines)
        PreviewRenderer._draw_contours(draw, contours, (0, 0, 0))
        PreviewRenderer._draw_contours(draw, text_contours, (255, 0, 0))
        
        return preview
        
    @staticmethod
    def _draw_hatching(draw, lines):
        for line in lines:
            if len(line) > 1:
                for i in range(len(line) - 1):
                    x1, y1 = line[i]
                    x2, y2 = line[i + 1]
                    draw.line([(x1, y1), (x2, y2)], fill=(150, 150, 150), width=1)
                    
    @staticmethod
    def _draw_contours(draw, contours, color):
        for contour in contours:
            if len(contour) > 2:
                points = [(point[0][0], point[0][1]) for point in contour]
                draw.polygon(points, outline=color, width=2)

class ImageToGCodeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PyPlotter")
        self.root.geometry("1400x850")
        
        self.original_image = None
        self.processed_image = None
        self.lines = []
        self.contours = []
        self.text_contours = []
        self.current_text = ""
        self.gcode = ""
        self.processing = False
        self.emergency_stop_activated = False
        
        self.status_var = tk.StringVar(value="Готов к работе. Введите русский текст или загрузите изображение.")
        self.stats_var = tk.StringVar(value="")
        self.notebook = None
        self.control_button_frame = None
        
        self.config_manager = ConfigManager(DEFAULT_CONFIG)
        self.config = self.config_manager.config
        self.config["font_scale"] = 0.4
        
        self.connection_manager = ConnectionManager(self)
        self.is_connected = False
        
        self.create_widgets()
        self.root.bind('<Configure>', self.on_resize)
        
    def create_widgets(self):
        self.create_menu()
        self.create_main_layout()
        self.create_status_bar()
        self.setup_ui_bindings()
        
    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Загрузить изображение", command=self.load_image)
        file_menu.add_command(label="Очистить всё", command=self.clear_image)
        file_menu.add_command(label="Сохранить G-код", command=self.save_gcode)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit)
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Инструменты", menu=tools_menu)
        tools_menu.add_command(label="Сбросить параметры", command=self.reset_config)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Помощь", menu=help_menu)
        help_menu.add_command(label="О программе", command=self.show_about)
        
    def create_main_layout(self):
        connection_frame = ttk.LabelFrame(self.root, text="Подключение к устройству")
        connection_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(connection_frame, text="Тип подключения:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.connection_type_var = tk.StringVar(value="serial")
        ttk.Radiobutton(connection_frame, text="Последовательный порт", 
                       variable=self.connection_type_var, value="serial",
                       command=self.update_connection_options).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Radiobutton(connection_frame, text="Bluetooth", 
                       variable=self.connection_type_var, value="bluetooth").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        
        ttk.Label(connection_frame, text="Устройство:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.device_combo = ttk.Combobox(connection_frame, width=40, state="readonly")
        self.device_combo.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)
        
        refresh_btn = ttk.Button(connection_frame, text="Обновить список", command=self.refresh_devices)
        refresh_btn.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        self.connect_btn = ttk.Button(connection_frame, text="Подключиться", command=self.toggle_connection)
        self.connect_btn.grid(row=2, column=2, padx=5, pady=5, sticky="e")
        
        connection_frame.columnconfigure(1, weight=1)
        connection_frame.columnconfigure(2, weight=1)
        
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        params_frame = ttk.Frame(main_frame)
        params_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5), pady=0)
        params_frame.config(width=400)
        params_frame.pack_propagate(False) 
        
        self.create_all_parameters(params_frame)
        
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=0)
        
        self.notebook = ttk.Notebook(content_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        self.create_preview_tab(self.notebook)
        self.create_text_tab(self.notebook)
        self.create_gcode_tab(self.notebook)
        
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        self.control_button_frame = button_frame
        
        emergency_frame = ttk.Frame(self.root)
        emergency_frame.pack(fill=tk.X, padx=10, pady=5)
        
        style = ttk.Style()
        style.configure("Emergency.TButton", background="red", foreground="red", font=('Arial', 10, 'bold'))
        
        self.emergency_btn = ttk.Button(emergency_frame, text="ЭКСТРЕННАЯ ОСТАНОВКА", 
                                       command=self.emergency_stop, 
                                       width=30,
                                       style="Emergency.TButton")
        self.emergency_btn.pack(side=tk.RIGHT, padx=5)
        
        self.update_control_buttons()
        
        self.refresh_devices()
        
    def create_all_parameters(self, parent_frame):
        image_frame = ttk.LabelFrame(parent_frame, text="Параметры обработки изображения")
        image_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(image_frame, text="Canny Min:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.canny_min_slider = tk.Scale(image_frame, from_=0, to=255, orient=tk.HORIZONTAL, length=120)
        self.canny_min_slider.set(self.config["canny_min"])
        self.canny_min_slider.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(image_frame, text="Canny Max:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.canny_max_slider = tk.Scale(image_frame, from_=0, to=255, orient=tk.HORIZONTAL, length=120)
        self.canny_max_slider.set(self.config["canny_max"])
        self.canny_max_slider.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(image_frame, text="Размер ядра размытия:").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.blur_kernel_entry = ttk.Entry(image_frame, width=8)
        self.blur_kernel_entry.insert(0, str(self.config.get("blur_kernel", 5)))
        self.blur_kernel_entry.grid(row=2, column=1, padx=5, pady=2)
        
        ttk.Label(image_frame, text="Сигма размытия:").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        self.blur_sigma_entry = ttk.Entry(image_frame, width=8)
        self.blur_sigma_entry.insert(0, str(self.config.get("blur_sigma", 1.0)))
        self.blur_sigma_entry.grid(row=3, column=1, padx=5, pady=2)
        
        ttk.Label(image_frame, text="Размер ядра морфологии:").grid(row=4, column=0, padx=5, pady=2, sticky="e")
        self.morph_kernel_entry = ttk.Entry(image_frame, width=8)
        self.morph_kernel_entry.insert(0, str(self.config.get("morph_kernel_size", 3)))
        self.morph_kernel_entry.grid(row=4, column=1, padx=5, pady=2)
        
        ttk.Label(image_frame, text="Итерации морфологии:").grid(row=5, column=0, padx=5, pady=2, sticky="e")
        self.morph_iter_entry = ttk.Entry(image_frame, width=8)
        self.morph_iter_entry.insert(0, str(self.config.get("morph_iterations", 1)))
        self.morph_iter_entry.grid(row=5, column=1, padx=5, pady=2)
        
        ttk.Label(image_frame, text="Мин. длина контура:").grid(row=6, column=0, padx=5, pady=2, sticky="e")
        self.min_contour_entry = ttk.Entry(image_frame, width=8)
        self.min_contour_entry.insert(0, str(self.config["min_contour_length"]))
        self.min_contour_entry.grid(row=6, column=1, padx=5, pady=2)
        
        ttk.Label(image_frame, text="Мин. длина линии:").grid(row=7, column=0, padx=5, pady=2, sticky="e")
        self.min_line_entry = ttk.Entry(image_frame, width=8)
        self.min_line_entry.insert(0, str(self.config["min_line_length"]))
        self.min_line_entry.grid(row=7, column=1, padx=5, pady=2)
        
        hatch_frame = ttk.LabelFrame(parent_frame, text="Параметры штриховки")
        hatch_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(hatch_frame, text="Плотность:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.hatch_slider = tk.Scale(hatch_frame, from_=1, to=20, orient=tk.HORIZONTAL, length=120)
        self.hatch_slider.set(self.config["hatch_density"])
        self.hatch_slider.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(hatch_frame, text="Угол (град):").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.angle_slider = tk.Scale(hatch_frame, from_=0, to=180, orient=tk.HORIZONTAL, length=120)
        self.angle_slider.set(self.config["hatch_angle"])
        self.angle_slider.grid(row=1, column=1, padx=5, pady=2)
        
        self.hatch_var = tk.BooleanVar(value=self.config["draw_hatching"])
        ttk.Checkbutton(hatch_frame, text="Рисовать штриховку", variable=self.hatch_var).grid(row=2, column=0, columnspan=2, padx=5, pady=2, sticky="w")
        
        self.cross_var = tk.BooleanVar(value=self.config["hatch_cross"])
        ttk.Checkbutton(hatch_frame, text="Перекрестная штриховка", variable=self.cross_var).grid(row=3, column=0, columnspan=2, padx=5, pady=2, sticky="w")
        
        machine_frame = ttk.LabelFrame(parent_frame, text="Параметры станка")
        machine_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(machine_frame, text="Рабочая область X (мм):").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.work_x_entry = ttk.Entry(machine_frame, width=8)
        self.work_x_entry.insert(0, str(self.config["work_area_x"]))
        self.work_x_entry.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(machine_frame, text="Рабочая область Y (мм):").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.work_y_entry = ttk.Entry(machine_frame, width=8)
        self.work_y_entry.insert(0, str(self.config["work_area_y"]))
        self.work_y_entry.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(machine_frame, text="Z поднято (мм):").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.pen_up_entry = ttk.Entry(machine_frame, width=8)
        self.pen_up_entry.insert(0, str(self.config["pen_up_z"]))
        self.pen_up_entry.grid(row=2, column=1, padx=5, pady=2)
        
        ttk.Label(machine_frame, text="Z опущено (мм):").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        self.pen_down_entry = ttk.Entry(machine_frame, width=8)
        self.pen_down_entry.insert(0, str(self.config["pen_down_z"]))
        self.pen_down_entry.grid(row=3, column=1, padx=5, pady=2)
        
        ttk.Label(machine_frame, text="Скорость подачи (мм/мин):").grid(row=4, column=0, padx=5, pady=2, sticky="e")
        self.feed_rate_entry = ttk.Entry(machine_frame, width=8)
        self.feed_rate_entry.insert(0, str(self.config["feed_rate"]))
        self.feed_rate_entry.grid(row=4, column=1, padx=5, pady=2)
        
        ttk.Label(machine_frame, text="Быстрая подача (мм/мин):").grid(row=5, column=0, padx=5, pady=2, sticky="e")
        self.rapid_rate_entry = ttk.Entry(machine_frame, width=8)
        self.rapid_rate_entry.insert(0, str(self.config["rapid_feed_rate"]))
        self.rapid_rate_entry.grid(row=5, column=1, padx=5, pady=2)
        
        text_frame = ttk.LabelFrame(parent_frame, text="Параметры русского текста")
        text_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(text_frame, text="Размер шрифта (pt):").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.font_size_entry = ttk.Entry(text_frame, width=10)
        self.font_size_entry.insert(0, "12")
        self.font_size_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(text_frame, text="Межсимвольный интервал:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.font_spacing_slider = tk.Scale(text_frame, from_=0.1, to=1.0, resolution=0.05,
                                           orient=tk.HORIZONTAL, length=120)
        self.font_spacing_slider.set(0.8)
        self.font_spacing_slider.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(text_frame, text="Позиция X (мм):").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.text_pos_x_entry = ttk.Entry(text_frame, width=10)
        default_x = self.config.get("work_area_x", 100) * 0.5
        self.text_pos_x_entry.insert(0, str(default_x))
        self.text_pos_x_entry.grid(row=2, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(text_frame, text="Позиция Y (мм):").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        self.text_pos_y_entry = ttk.Entry(text_frame, width=10)
        default_y = self.config.get("work_area_y", 100) * 0.9
        self.text_pos_y_entry.insert(0, str(default_y))
        self.text_pos_y_entry.grid(row=3, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(text_frame, text="Выравнивание:").grid(row=4, column=0, padx=5, pady=2, sticky="e")
        self.align_var = tk.StringVar(value=self.config["text_align"])
        align_combo = ttk.Combobox(text_frame, textvariable=self.align_var, 
                                   values=["left", "center", "right"], width=10, state="readonly")
        align_combo.grid(row=4, column=1, padx=5, pady=2, sticky="w")
        
    def on_tab_changed(self, event):
        self.update_control_buttons()
        
    def create_preview_tab(self, notebook):
        image_frame = ttk.Frame(notebook)
        notebook.add(image_frame, text="Изображение")
        
        orig_frame = ttk.LabelFrame(image_frame, text="Исходное изображение")
        orig_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.original_canvas = tk.Canvas(orig_frame, bg="gray", width=450, height=450)
        self.original_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        proc_frame = ttk.LabelFrame(image_frame, text="Результат обработки")
        proc_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.processed_canvas = tk.Canvas(proc_frame, bg="white", width=450, height=450)
        self.processed_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
    def create_text_tab(self, notebook):
        text_frame = ttk.Frame(notebook)
        notebook.add(text_frame, text="Текст")
        
        text_input_frame = ttk.LabelFrame(text_frame, text="Введите текст")
        text_input_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.text_entry = scrolledtext.ScrolledText(text_input_frame, height=8, width=60, font=("Arial", 12))
        self.text_entry.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.text_entry.insert("1.0", "Привет, мир!")
        
    def create_gcode_tab(self, notebook):
        gcode_frame = ttk.Frame(notebook)
        notebook.add(gcode_frame, text="G-код")
        
        self.gcode_text = scrolledtext.ScrolledText(gcode_frame, width=80, height=25, font=("Courier", 10))
        self.gcode_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.gcode_stats_var = tk.StringVar(value="Статистика будет доступна после генерации G-кода")
        ttk.Label(gcode_frame, textvariable=self.gcode_stats_var, foreground="gray").pack(side=tk.BOTTOM, pady=5)
                
    def update_control_buttons(self):
        for widget in self.control_button_frame.winfo_children():
            widget.destroy()
            
        if not self.notebook:
            return
            
        current_tab_index = self.notebook.index(self.notebook.select())
        current_tab_text = self.notebook.tab(current_tab_index, "text")
        
        if current_tab_text == "Изображение":
            load_btn = ttk.Button(self.control_button_frame, text="Загрузить изображение", 
                                 command=self.load_image, width=25)
            load_btn.pack(side=tk.LEFT, padx=5)
            
            clear_btn = ttk.Button(self.control_button_frame, text="Очистить изображение", 
                                  command=self.clear_image, width=25)
            clear_btn.pack(side=tk.LEFT, padx=5)
            
            preview_btn = ttk.Button(self.control_button_frame, text="Обработка изображения", 
                                    command=self.process_image, width=25)
            preview_btn.pack(side=tk.LEFT, padx=5)
            
            gcode_btn = ttk.Button(self.control_button_frame, text="Сгенерировать G-код", 
                                      command=self.generate_gcode, width=20)
            gcode_btn.pack(side=tk.LEFT, padx=5)
            
            save_btn = ttk.Button(self.control_button_frame, text="Сохранить G-код", 
                                    command=self.save_gcode, width=20)
            save_btn.pack(side=tk.LEFT, padx=5)
            
            if self.is_connected:
                send_btn = ttk.Button(self.control_button_frame, text="Отправить на устройство", 
                                    command=self.send_gcode_to_device, width=26)
                send_btn.pack(side=tk.LEFT, padx=5)
                
        elif current_tab_text == "Текст":
            add_text_btn = ttk.Button(self.control_button_frame, text="Добавить текст к изображению", 
                                     command=self.add_text_to_preview, width=30)
            add_text_btn.pack(side=tk.LEFT, padx=5)
            
            clear_text_btn = ttk.Button(self.control_button_frame, text="Очистить текст", 
                                       command=self.clear_text, width=20)
            clear_text_btn.pack(side=tk.LEFT, padx=5)
            
            text_only_btn = ttk.Button(self.control_button_frame, text="Сгенерировать G-код", 
                                      command=self.generate_text_only, width=26)
            text_only_btn.pack(side=tk.LEFT, padx=5)
            
            save_btn = ttk.Button(self.control_button_frame, text="Сохранить G-код", 
                                    command=self.save_gcode, width=20)
            save_btn.pack(side=tk.LEFT, padx=5)
            
            if self.is_connected:
                send_btn = ttk.Button(self.control_button_frame, text="Отправить на устройство", 
                                    command=self.send_gcode_to_device, width=26)
                send_btn.pack(side=tk.LEFT, padx=5)
                
        elif current_tab_text == "G-код":
            copy_btn = ttk.Button(self.control_button_frame, text="Копировать в буфер", 
                                    command=self.copy_gcode_to_clipboard, width=20)
            copy_btn.pack(side=tk.RIGHT, padx=5)
            
            if self.is_connected:
                send_btn = ttk.Button(self.control_button_frame, text="Отправить на устройство", 
                                    command=self.send_gcode_to_device, width=26)
                send_btn.pack(side=tk.LEFT, padx=5)
                
    def copy_gcode_to_clipboard(self):
        if self.gcode:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.gcode)
            self.root.update()
            self.status_var.set("G-код скопирован в буфер обмена")
            
    def create_status_bar(self):
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=2)
        
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor=tk.W)
        self.status_label.pack(fill=tk.X, side=tk.LEFT)
        
        self.stats_label = ttk.Label(status_frame, textvariable=self.stats_var, anchor=tk.E, foreground="gray")
        self.stats_label.pack(fill=tk.X, side=tk.RIGHT)
        
        connection_status_frame = ttk.Frame(status_frame)
        connection_status_frame.pack(side=tk.RIGHT, padx=(20, 5))
        
        ttk.Label(connection_status_frame, text="Статус подключения:").pack(side=tk.LEFT, padx=(10, 5))
        self.connection_status_var = tk.StringVar(value="Отключено")
        self.connection_status_label = ttk.Label(
            connection_status_frame, 
            textvariable=self.connection_status_var, 
            foreground="red",
            font=('Arial', 9, 'bold')
        )
        self.connection_status_label.pack(side=tk.LEFT)
        
        self.progress = ttk.Progressbar(status_frame, mode='indeterminate')
        
    def setup_ui_bindings(self):
        self.ui_elements = {
            "canny_min_slider": self.canny_min_slider,
            "canny_max_slider": self.canny_max_slider,
            "hatch_slider": self.hatch_slider,
            "angle_slider": self.angle_slider,
            "hatch_var": self.hatch_var,
            "cross_var": self.cross_var,
            "work_x_entry": self.work_x_entry,
            "work_y_entry": self.work_y_entry,
            "pen_up_entry": self.pen_up_entry,
            "pen_down_entry": self.pen_down_entry,
            "feed_rate_entry": self.feed_rate_entry,
            "rapid_rate_entry": self.rapid_rate_entry,
            "min_contour_entry": self.min_contour_entry,
            "min_line_entry": self.min_line_entry,
            "font_size_entry": self.font_size_entry,
            "font_spacing_slider": self.font_spacing_slider,
            "text_pos_x_entry": self.text_pos_x_entry,
            "text_pos_y_entry": self.text_pos_y_entry,
            "align_var": self.align_var,
            "morph_kernel_entry": self.morph_kernel_entry,
            "morph_iter_entry": self.morph_iter_entry,
            "blur_kernel_entry": self.blur_kernel_entry,
            "blur_sigma_entry": self.blur_sigma_entry,
        }
        
    def on_resize(self, event):
        if self.original_image:
            self.update_previews()
            
    def update_config_from_ui(self):
        return self.config_manager.update_from_ui(self.ui_elements)
        
    def load_image(self):
        if self.processing:
            messagebox.showwarning("Занято", "Дождитесь завершения текущей операции")
            return
            
        file_path = filedialog.askopenfilename(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.tiff *.gif")]
        )
        if not file_path:
            return
            
        try:
            self.status_var.set(f"Загрузка изображения: {os.path.basename(file_path)}")
            self.root.update()
            self.original_image = Image.open(file_path)
            if self.original_image.mode != 'RGB':
                self.original_image = self.original_image.convert('RGB')
            self.update_previews()
            auto_adjust_scale(self.original_image, self.config)
            default_x = self.config.get("work_area_x", 100) * 0.5
            default_y = self.config.get("work_area_y", 100) * 0.9
            self.text_pos_x_entry.delete(0, tk.END)
            self.text_pos_x_entry.insert(0, str(default_x))
            self.text_pos_y_entry.delete(0, tk.END)
            self.text_pos_y_entry.insert(0, str(default_y))
            self.work_x_entry.delete(0, tk.END)
            self.work_x_entry.insert(0, str(self.config["work_area_x"]))
            self.work_y_entry.delete(0, tk.END)
            self.work_y_entry.insert(0, str(self.config["work_area_y"]))
            self.status_var.set(f"Загружено: {os.path.basename(file_path)}, размер: {self.original_image.size[0]}x{self.original_image.size[1]}px")
            self.processed_image = None
            self.lines = []
            self.contours = []
            self.text_contours = []
            self.gcode = ""
            self.gcode_text.delete(1.0, tk.END)
            self.processed_canvas.delete("all")
            self.gcode_stats_var.set("Статистика будет доступна после генерации G-кода")
            self.update_control_buttons()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", f"Не удалось загрузить изображение:\n{str(e)}")
            self.status_var.set("Ошибка загрузки изображения")
            
    def update_previews(self):
        if self.original_image:
            display_image_on_canvas(self.original_image, self.original_canvas)
        if self.processed_image:
            display_image_on_canvas(self.processed_image, self.processed_canvas)
            
    def process_image(self):
        if self.processing:
            messagebox.showwarning("Занято", "Обработка уже выполняется")
            return
            
        if self.original_image is None:
            messagebox.showwarning("Нет изображения", "Сначала загрузите изображение")
            return
            
        if not self.update_config_from_ui():
            return
            
        self.text_contours = []
        self.processing = True
        self.progress.pack(fill=tk.X, padx=5, pady=2)
        self.progress.start()
        threading.Thread(target=self._process_image_thread, daemon=True).start()
        
    def _process_image_thread(self):
        try:
            self.status_var.set("Обработка изображения...")
            self.root.update()
            img_cv = np.array(self.original_image)
            img_cv = cv2.cvtColor(img_cv, cv2.COLOR_RGB2BGR)
            _, self.contours = get_contours(
                img_cv, 
                canny_min=self.config["canny_min"], 
                canny_max=self.config["canny_max"],
                blur_kernel=self.config["blur_kernel"],
                blur_sigma=self.config["blur_sigma"],
                morph_kernel_size=self.config["morph_kernel_size"],
                morph_iterations=self.config["morph_iterations"],
                min_contour_length=self.config["min_contour_length"]
            )
            self.lines = []
            if self.config["draw_hatching"]:
                self.lines = generate_hatching(
                    img_cv, 
                    self.config["hatch_density"], 
                    self.config["hatch_angle"], 
                    self.config["hatch_cross"],
                    min_line_length=self.config["min_line_length"]
                )
            self.processed_image = PreviewRenderer.create_image_preview(
                self.original_image, self.lines, self.contours, self.text_contours
            )
            contour_count = len(self.contours)
            line_count = len(self.lines)
            self.stats_var.set(f"Контуры: {contour_count} | Линии штриховки: {line_count}")
            self.status_var.set(f"Обработка завершена. Контуры: {contour_count}, линии штриховки: {line_count}")
        except Exception as e:
            error_msg = f"Ошибка обработки: {str(e)}"
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: messagebox.showerror("Ошибка обработки", error_msg))
            self.status_var.set("Ошибка обработки изображения")
            self.stats_var.set("")
        finally:
            self.root.after(0, self._finish_processing)
            
    def _finish_processing(self):
        self.processing = False
        self.progress.stop()
        self.progress.pack_forget()
        self.update_previews()
        self.update_control_buttons()
        
    def add_text_to_preview(self):
        if self.processing:
            messagebox.showwarning("Занято", "Дождитесь завершения текущей операции")
            return
            
        if not self.update_config_from_ui():
            return
            
        self.current_text = self.text_entry.get("1.0", tk.END).strip()
        if not self.current_text:
            messagebox.showwarning("Нет текста", "Введите текст для добавления")
            return
            
        try:
            start_x = float(self.text_pos_x_entry.get())
            start_y = float(self.text_pos_y_entry.get())
            work_area_x = self.config.get("work_area_x", 100)
            work_area_y = self.config.get("work_area_y", 100)
            position = (start_x / work_area_x, start_y / work_area_y)
            align = self.config["text_align"]
            self.text_contours = add_cyrillic_text_to_contours(
                self.current_text,
                self.contours,
                self.config,
                position,
                align
            )
            self.processed_image = PreviewRenderer.create_image_preview(
                self.original_image, self.lines, self.contours, self.text_contours
            )
            self.update_previews()
            display_text = self.current_text[:30] + "..." if len(self.current_text) > 30 else self.current_text
            self.status_var.set(f"Добавлен русский текст: '{display_text}'")
            self.update_control_buttons()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось добавить текст: {str(e)}")
            
    def clear_image(self):
        if not messagebox.askyesno("Очистка изображения", "Вы уверены, что хотите удалить всё содержимое?"):
            return
            
        self.original_image = None
        self.processed_image = None
        self.lines = []
        self.contours = []
        self.text_contours = []
        self.current_text = ""
        self.gcode = ""
        self.original_canvas.delete("all")
        self.processed_canvas.delete("all")
        self.gcode_text.delete(1.0, tk.END)
        self.gcode_stats_var.set("Статистика будет доступна после генерации G-кода")
        self.status_var.set("Изображение и все данные очищены.")
        self.stats_var.set("")
        self.update_control_buttons()
        
    def clear_text(self):
        self.text_contours = []
        self.current_text = ""
        self.text_entry.delete("1.0", tk.END)
        if self.original_image:
            self.processed_image = PreviewRenderer.create_image_preview(
                self.original_image, self.lines, self.contours, self.text_contours
            )
            self.update_previews()
        self.status_var.set("Текст очищен")
        self.update_control_buttons()
        
    def generate_text_only(self):
        if self.processing:
            messagebox.showwarning("Занято", "Дождитесь завершения текущей операции")
            return
            
        if not self.current_text:
            messagebox.showwarning("Нет текста", "Сначала добавьте текст")
            return
            
        if not self.update_config_from_ui():
            return
            
        try:
            start_x = float(self.text_pos_x_entry.get())
            start_y = float(self.text_pos_y_entry.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректные значения позиции текста")
            return
            
        work_area_x = self.config.get("work_area_x", 100)
        work_area_y = self.config.get("work_area_y", 100)
        if not (0 <= start_x <= work_area_x) or not (0 <= start_y <= work_area_y):
            messagebox.showwarning("Предупреждение", 
                                 f"Позиция текста должна быть в пределах рабочей области:\n"
                                 f"X: 0-{work_area_x} мм, Y: 0-{work_area_y} мм")
            return
            
        self.processing = True
        self.progress.pack(fill=tk.X, padx=5, pady=2)
        self.progress.start()
        threading.Thread(target=self._generate_text_gcode_thread, 
                        args=(start_x, start_y), daemon=True).start()
        
    def _generate_text_gcode_thread(self, start_x, start_y):
        try:
            self.status_var.set("Генерация G-кода для русского текста...")
            self.root.update()
            self.gcode = text_to_gcode_cyrillic(
                self.current_text,
                self.config,
                start_x,
                start_y,
                self.config["text_align"]
            )
            font_size_pt = self.font_size_entry.get()
            header = f"; G-код для русского текста\n"
            header += f"; Текст: {self.current_text}\n"
            header += f"; Позиция: X={start_x:.2f}mm, Y={start_y:.2f}mm\n"
            header += f"; Выравнивание: {self.config['text_align']}\n"
            header += f"; Размер шрифта: {font_size_pt}pt\n"
            self.gcode = header + self.gcode
            self.root.after(0, self._update_gcode_display)
            self.root.after(0, lambda: self.status_var.set(
                f"G-код для русского текста сгенерирован"
            ))
            line_count = len(self.gcode.splitlines())
            size_kb = len(self.gcode) // 1024
            stats_text = f"Строк: {line_count} | Размер: {size_kb} КБ | Режим: Только текст"
            self.root.after(0, lambda: self.gcode_stats_var.set(stats_text))
        except Exception as e:
            error_msg = f"Ошибка генерации G-кода для текста:\n{str(e)}"
            self.root.after(0, lambda: messagebox.showerror("Ошибка генерации", error_msg))
            self.root.after(0, lambda: self.status_var.set("Ошибка генерации G-кода текста"))
        finally:
            self.root.after(0, self._finish_gcode_generation)
            
    def generate_gcode(self):
        if self.processing:
            messagebox.showwarning("Занято", "Дождитесь обработки")
            return
            
        if not self.lines and not self.contours and not self.text_contours:
            messagebox.showwarning("Нет данных", "Сначала обработайте изображение или добавьте текст")
            return
            
        if not self.update_config_from_ui():
            return
            
        if self.config["pen_down_z"] >= self.config["pen_up_z"]:
            if not messagebox.askyesno("Предупреждение", 
                "Z опущено должно быть меньше Z поднято. Исправить автоматически?"):
                return
            self.config["pen_down_z"] = self.config["pen_up_z"] - 1.0
            self.pen_down_entry.delete(0, tk.END)
            self.pen_down_entry.insert(0, str(self.config["pen_down_z"]))
            
        self.processing = True
        self.progress.pack(fill=tk.X, padx=5, pady=2)
        self.progress.start()
        threading.Thread(target=self._generate_gcode_thread, daemon=True).start()
        
    def _generate_gcode_thread(self):
        try:
            self.status_var.set("Генерация G-кода...")
            self.root.update()
            all_contours = self.contours + self.text_contours
            self.gcode = generate_sketch_gcode(
                hatching_lines=self.lines,
                contours=all_contours,
                image_width=self.original_image.size[0],
                image_height=self.original_image.size[1],
                config=self.config,
                optimize_order=self.config.get("optimize_order", True)
            )
            if self.current_text and self.text_contours:
                font_size_pt = self.font_size_entry.get()
                text_info = f"; Добавлен русский текст: {self.current_text}\n"
                text_info += f"; Выравнивание: {self.config['text_align']}\n"
                text_info += f"; Размер шрифта: {font_size_pt}pt\n"
                self.gcode = text_info + self.gcode
            self.root.after(0, self._update_gcode_display)
            line_count = len(self.lines)
            contour_count = len(self.contours)
            text_contour_count = len(self.text_contours)
            status = f"G-код сгенерирован. Штриховка: {line_count} линий, Контур: {contour_count}, Текст: {text_contour_count} контуров"
            self.root.after(0, lambda: self.status_var.set(status))
            total_lines = len(self.gcode.splitlines())
            size_kb = len(self.gcode) // 1024
            mode = "Изображение + текст" if self.text_contours else "Только изображение"
            stats_text = f"Строк: {total_lines} | Размер: {size_kb} КБ | Режим: {mode}"
            self.root.after(0, lambda: self.gcode_stats_var.set(stats_text))
            self.root.after(0, lambda: self.stats_var.set(f"Строк: {total_lines} | Размер: {size_kb} КБ"))
        except Exception as e:
            error_msg = f"Ошибка генерации G-кода:\n{str(e)}"
            self.root.after(0, lambda: messagebox.showerror("Ошибка генерации", error_msg))
            self.root.after(0, lambda: self.status_var.set("Ошибка генерации G-кода"))
            self.root.after(0, lambda: self.stats_var.set(""))
        finally:
            self.root.after(0, self._finish_gcode_generation)
            
    def _update_gcode_display(self):
        self.gcode_text.delete(1.0, tk.END)
        self.gcode_text.insert(tk.END, self.gcode)
        
    def _finish_gcode_generation(self):
        self.processing = False
        self.progress.stop()
        self.progress.pack_forget()
        self.update_control_buttons()
        
    def save_gcode(self):
        if not self.gcode:
            messagebox.showwarning("Нет G-кода", "Сначала сгенерируйте G-код")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".gcode",
            filetypes=[
                ("G-код", "*.gcode *.nc"),
                ("Текстовые файлы", "*.txt"),
                ("Все файлы", "*.*")
            ],
            initialfile=f"drawing_{time.strftime('%Y%m%d_%H%M%S')}.gcode"
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.gcode)
            messagebox.showinfo("Сохранено", f"G-код успешно сохранен в:\n{file_path}")
            self.status_var.set(f"Сохранено: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить файл:\n{str(e)}")
            
    def reset_config(self):
        if messagebox.askyesno("Сброс параметров", "Вы действительно хотите сбросить все параметры к значениям по умолчанию?"):
            self.config = self.config_manager.reset_to_default(DEFAULT_CONFIG)
            self.canny_min_slider.set(self.config["canny_min"])
            self.canny_max_slider.set(self.config["canny_max"])
            self.hatch_slider.set(self.config["hatch_density"])
            self.angle_slider.set(self.config["hatch_angle"])
            self.hatch_var.set(self.config["draw_hatching"])
            self.cross_var.set(self.config["hatch_cross"])
            self.work_x_entry.delete(0, tk.END)
            self.work_x_entry.insert(0, str(self.config["work_area_x"]))
            self.work_y_entry.delete(0, tk.END)
            self.work_y_entry.insert(0, str(self.config["work_area_y"]))
            self.pen_up_entry.delete(0, tk.END)
            self.pen_up_entry.insert(0, str(self.config["pen_up_z"]))
            self.pen_down_entry.delete(0, tk.END)
            self.pen_down_entry.insert(0, str(self.config["pen_down_z"]))
            self.feed_rate_entry.delete(0, tk.END)
            self.feed_rate_entry.insert(0, str(self.config["feed_rate"]))
            self.rapid_rate_entry.delete(0, tk.END)
            self.rapid_rate_entry.insert(0, str(self.config["rapid_feed_rate"]))
            self.min_contour_entry.delete(0, tk.END)
            self.min_contour_entry.insert(0, str(self.config["min_contour_length"]))
            self.min_line_entry.delete(0, tk.END)
            self.min_line_entry.insert(0, str(self.config["min_line_length"]))
            self.font_size_entry.delete(0, tk.END)
            self.font_size_entry.insert(0, "12")
            self.config["font_scale"] = 0.4
            self.font_spacing_slider.set(0.8)
            default_x = self.config.get("work_area_x", 100) * 0.5
            default_y = self.config.get("work_area_y", 100) * 0.9
            self.text_pos_x_entry.delete(0, tk.END)
            self.text_pos_x_entry.insert(0, str(default_x))
            self.text_pos_y_entry.delete(0, tk.END)
            self.text_pos_y_entry.insert(0, str(default_y))
            self.align_var.set(self.config["text_align"])
            self.morph_kernel_entry.delete(0, tk.END)
            self.morph_kernel_entry.insert(0, str(self.config.get("morph_kernel_size", 3)))
            self.morph_iter_entry.delete(0, tk.END)
            self.morph_iter_entry.insert(0, str(self.config.get("morph_iterations", 1)))
            self.blur_kernel_entry.delete(0, tk.END)
            self.blur_kernel_entry.insert(0, str(self.config.get("blur_kernel", 5)))
            self.blur_sigma_entry.delete(0, tk.END)
            self.blur_sigma_entry.insert(0, str(self.config.get("blur_sigma", 1.0)))
            self.status_var.set("Параметры сброшены к значениям по умолчанию")
            self.stats_var.set("")
            
    def show_about(self):
        about_text = (
            "PyPlotter\n"
            "Версия 2.0\n"
            "Программа для генерации G-кода для художественной рисовальной машины.\n"
            "Преобразует изображения в контуры и штриховку для рисования карандашом.\n"
            "Поддерживает добавление русского текста шрифтом Hershey.\n"
            "Улучшенные функции:\n"
            "- Улучшенная детекция контуров с настройками морфологических операций\n"
            "- Гауссово размытие с настраиваемыми параметрами\n"
            "- Размер шрифта в пунктах (pt), как в Word\n"
            "- Абсолютные координаты позиции текста в мм\n"
            "ВСЕГДА проверяйте G-код в симуляторе перед запуском на реальном станке!"
        )
        messagebox.showinfo("О программе", about_text)
        
    def update_connection_options(self):
        self.refresh_devices()
        
    def refresh_devices(self):
        connection_type = self.connection_type_var.get()
        devices = self.connection_manager.get_available_devices(connection_type)
        
        self.device_combo['values'] = [device['name'] for device in devices]
        if devices:
            self.device_combo.current(0)
            self.device_combo.config(state="readonly")
        else:
            self.device_combo.set("Устройства не найдены")
            self.device_combo.config(state="disabled")
            
    def on_device_selected(self, event):
        pass  
        
    def toggle_connection(self):
        if self.is_connected:
            self.disconnect_device()
        else:
            self.connect_device()
            
    def connect_device(self):
        if not self.device_combo.get() or self.device_combo.get() == "Устройства не найдены":
            messagebox.showwarning("Нет устройства", "Выберите устройство для подключения")
            return
            
        connection_type = self.connection_type_var.get()
        device_index = self.device_combo.current()
        devices = self.connection_manager.get_available_devices(connection_type)
        
        if device_index >= 0 and device_index < len(devices):
            device_id = devices[device_index]['id']
            success, message = self.connection_manager.connect(device_id, connection_type)
            
            if success:
                self.is_connected = True
                self.connect_btn.config(text="Отключиться")
                self.connection_status_var.set(f"Подключено: {self.device_combo.get()}")
                self.connection_status_label.config(foreground="green")
                self.update_control_buttons()  
            else:
                messagebox.showerror("Ошибка подключения", message)
        else:
            messagebox.showwarning("Неверное устройство", "Выберите корректное устройство")
            
    def disconnect_device(self):
        success, message = self.connection_manager.disconnect()
        if success:
            self.is_connected = False
            self.connect_btn.config(text="Подключиться")
            self.connection_status_var.set("Отключено")
            self.connection_status_label.config(foreground="red")
            self.update_control_buttons()
            
    def update_status_message(self, message):
        self.status_var.set(message)
        
    def update_connection_status(self, status_text, is_connected):
        self.connection_status_var.set(status_text)
        self.connection_status_label.config(foreground="green" if is_connected else "red")
        self.is_connected = is_connected
        self.connect_btn.config(text="Отключиться" if is_connected else "Подключиться")
        self.update_control_buttons()
        
    def send_gcode_to_device(self):
        if not self.is_connected:
            messagebox.showwarning("Не подключено", "Сначала подключитесь к устройству")
            return
            
        if not self.gcode:
            messagebox.showwarning("Нет G-кода", "Сначала сгенерируйте G-код")
            return
            
        if not messagebox.askyesno("Отправить G-код", 
                                  "Вы уверены, что хотите отправить G-код на устройство?\n"
                                  "Убедитесь, что область для рисования свободна и устройство готово к работе."):
            return
            
        self.emergency_stop_activated = False
            
        self.status_var.set("Отправка G-кода на устройство...")
        self.progress.pack(fill=tk.X, padx=5, pady=2)
        self.progress.start()
        self.processing = True
        
        send_btn = self.get_send_button()
        if send_btn:
            send_btn.config(state="disabled")
            
        threading.Thread(target=self._send_gcode_thread, daemon=True).start()
        
    def _send_gcode_thread(self):
        try:
            gcode_lines = self.gcode.strip().split('\n')
            
            if self.emergency_stop_activated:
                self.root.after(0, lambda: self.status_var.set("Отправка отменена: активирована экстренная остановка"))
                return
            
            success, message = self.connection_manager.send_gcode(gcode_lines)
            
            if success:
                self.root.after(0, lambda: self.status_var.set("G-код успешно отправлен на устройство"))
            else:
                if not self.emergency_stop_activated:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка отправки", message))
                    self.root.after(0, lambda: self.status_var.set(f"Ошибка отправки: {message}"))
        except Exception as e:
            if not self.emergency_stop_activated:
                self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось отправить G-код: {str(e)}"))
                self.root.after(0, lambda: self.status_var.set(f"Ошибка отправки: {str(e)}"))
        finally:
            self.root.after(0, self._finish_gcode_sending)
    
    def _finish_gcode_sending(self):
        self.processing = False
        self.progress.stop()
        self.progress.pack_forget()
        
        self.emergency_stop_activated = False
        
        send_btn = self.get_send_button()
        if send_btn:
            send_btn.config(state="normal")
    
    def emergency_stop(self):
        if not self.is_connected:
            messagebox.showwarning("Не подключено", "Нет активного подключения для экстренной остановки")
            return
        
        if messagebox.askyesno("ЭКСТРЕННАЯ ОСТАНОВКА", 
                              "Вы уверены, что хотите активировать экстренную остановку?\n"
                              "Это немедленно остановит все движения устройства!"):
            self.emergency_stop_activated = True
            
            if self.processing:
                self.progress.stop()
                self.progress.pack_forget()
                self.processing = False
            
            success, message = self.connection_manager.emergency_stop()
            if success:
                messagebox.showwarning("ЭКСТРЕННАЯ ОСТАНОВКА", 
                                     "Команда экстренной остановки отправлена!\n"
                                     "Убедитесь, что устройство остановилось.")
                self.status_var.set("Активирована ЭКСТРЕННАЯ ОСТАНОВКА!")
                
                self._cancel_gcode_sending()
            else:
                messagebox.showerror("Ошибка", f"Не удалось отправить команду экстренной остановки:\n{message}")
    
    def _cancel_gcode_sending(self):
        if self.processing:
            self.processing = False
            self.progress.stop()
            self.progress.pack_forget()
            
            self.update_control_buttons()
            
            if hasattr(self.connection_manager.serial_conn, 'stop_send'):
                self.connection_manager.serial_conn.stop_send.set()
            
            self.status_var.set("Отправка G-кода прервана экстренной остановкой")
            
    def get_send_button(self):
        current_tab_index = self.notebook.index(self.notebook.select())
        current_tab_text = self.notebook.tab(current_tab_index, "text")
        
        for widget in self.control_button_frame.winfo_children():
            if hasattr(widget, 'cget') and widget.cget('text') == "Отправить на устройство":
                return widget
        return None
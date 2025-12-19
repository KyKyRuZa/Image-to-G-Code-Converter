from PIL import Image, ImageTk
import math
import numpy as np
from config import DEFAULT_CONFIG

def display_image_on_canvas(image, canvas):
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()
    
    if canvas_width <= 1 or canvas_height <= 1:
        canvas_width, canvas_height = 400, 400
        
    img_width, img_height = image.size
    ratio = min(canvas_width / img_width, canvas_height / img_height)
    new_width = int(img_width * ratio)
    new_height = int(img_height * ratio)
    
    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(resized_image)
    
    canvas.delete("all")
    canvas.create_image(canvas_width // 2, canvas_height // 2, image=photo)
    canvas.image = photo
    return photo

def auto_adjust_scale(image, config):
    width, height = image.size
    max_dimension = max(width, height)
    
    work_area_x = config.get("work_area_x", DEFAULT_CONFIG["work_area_x"])
    work_area_y = config.get("work_area_y", DEFAULT_CONFIG["work_area_y"])
    
    scale_x = work_area_x / width * 0.9
    scale_y = work_area_y / height * 0.9
    
    config["scale_factor"] = min(scale_x, scale_y, 0.3)
    return config["scale_factor"]

def transform_coordinates(x, y, image_width, image_height, scale_factor, work_area_x, work_area_y):
    y_inverted = image_height - y
    
    x_scaled = x * scale_factor
    y_scaled = y_inverted * scale_factor
    
    x_offset = (work_area_x - (image_width * scale_factor)) / 2
    y_offset = (work_area_y - (image_height * scale_factor)) / 2
    
    x_final = x_scaled + x_offset
    y_final = y_scaled + y_offset
    
    x_final = max(0, min(x_final, work_area_x))
    y_final = max(0, min(y_final, work_area_y))
    
    return x_final, y_final

def calculate_safe_z(pen_up_z, safety_margin=5.0):
    return max(pen_up_z, safety_margin)

def validate_numeric_input(value, min_val=None, max_val=None, default=0):
    try:
        num = float(value)
        if min_val is not None and num < min_val:
            return min_val
        if max_val is not None and num > max_val:
            return max_val
        return num
    except (ValueError, TypeError):
        return default
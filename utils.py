from PIL import Image, ImageTk
import math

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

def auto_adjust_scale(image, config):
    width, height = image.size
    max_dimension = max(width, height)
    
    if max_dimension > 2000:
        config["scale_factor"] = 0.15
    elif max_dimension > 1000:
        config["scale_factor"] = 0.2
    else:
        config["scale_factor"] = 0.3
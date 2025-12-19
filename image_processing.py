import cv2
import numpy as np
import math
from typing import Tuple, List, Optional
from config import DEFAULT_CONFIG

def preprocess_image(img: np.ndarray) -> np.ndarray:
    if img is None or img.size == 0:
        raise ValueError("Получено пустое изображение")
    
    if img.dtype != np.uint8:
        if img.max() <= 1.0:
            img = (img * 255).astype(np.uint8)
        else:
            img = img.astype(np.uint8)
    
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

def get_contours(
    img: np.ndarray,
    canny_min: int = 50,
    canny_max: int = 150,
    blur_kernel: int = 5,
    blur_sigma: float = 1.0,
    morph_kernel_size: int = 3,
    morph_iterations: int = 1,
    min_contour_length: Optional[int] = None
) -> Tuple[np.ndarray, List[np.ndarray]]:

    gray = preprocess_image(img)
    min_contour_length = min_contour_length or DEFAULT_CONFIG["min_contour_length"]

    blurred = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), blur_sigma)
    
    edges = cv2.Canny(blurred, canny_min, canny_max)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_kernel_size, morph_kernel_size))
    edges = cv2.morphologyEx(
        edges, 
        cv2.MORPH_CLOSE, 
        kernel, 
        iterations=morph_iterations
    )

    contours, _ = cv2.findContours(
        edges, 
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE
    )
    
    filtered_contours = [
        cnt for cnt in contours 
        if cv2.arcLength(cnt, closed=True) >= min_contour_length
    ]
    
    return edges, filtered_contours

def _generate_hatch_direction(
    lines: List[List[Tuple[int, int]]],
    img: np.ndarray,
    angle: float,
    spacing: int,
    height: int,
    width: int,
    min_line_length: int
) -> None:

    angle_rad = math.radians(angle)
    diag = int(math.sqrt(height**2 + width**2))
    
    for i in range(-diag, diag, spacing):
        current_line = []
        last_brightness = 0
        
        for t in range(-diag, diag):
            x = int(i * math.cos(angle_rad) - t * math.sin(angle_rad) + 0.5)
            y = int(i * math.sin(angle_rad) + t * math.cos(angle_rad) + 0.5)
            
            if 0 <= x < width and 0 <= y < height:
                brightness = img[y, x]
                threshold = 180 - brightness // 2
                
                if brightness > threshold:
                    if not current_line or last_brightness <= threshold:
                        current_line = [(x, y)]
                    else:
                        current_line.append((x, y))
                elif current_line:
                    if len(current_line) > min_line_length:
                        lines.append(current_line)
                    current_line = []
                
                last_brightness = brightness
            elif current_line:
                if len(current_line) > min_line_length:
                    lines.append(current_line)
                current_line = []
        
        if current_line and len(current_line) > min_line_length:
            lines.append(current_line)

def generate_hatching(
    img: np.ndarray,
    density: int,
    angle: float = 45.0,
    cross_hatch: bool = False,
    min_line_length: Optional[int] = None
) -> List[List[Tuple[int, int]]]:

    min_line_length = min_line_length or DEFAULT_CONFIG["min_line_length"]
    
    if img is None or img.size == 0:
        raise ValueError("Пустое изображение для генерации штриховки")
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
    normalized = 255 - gray
    
    height, width = gray.shape
    line_spacing = max(2, 100 // density)
    lines = []
    
    _generate_hatch_direction(
        lines, normalized, angle, line_spacing, height, width, min_line_length
    )
    
    if cross_hatch:
        _generate_hatch_direction(
            lines, normalized, angle + 90, line_spacing, height, width, min_line_length
        )
    
    return lines
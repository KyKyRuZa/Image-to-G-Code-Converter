import cv2
import numpy as np
import math

def generate_hatching(img, density, angle, cross_hatch):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    normalized = 255 - gray
    
    lines = []
    line_spacing = max(2, 100 // density)
    
    _generate_hatch_direction(lines, normalized, angle, line_spacing, height, width)
    
    if cross_hatch:
        cross_angle = angle + 90
        _generate_hatch_direction(lines, normalized, cross_angle, line_spacing, height, width)
    
    return lines

def _generate_hatch_direction(lines, img, angle, spacing, height, width):
    angle_rad = math.radians(angle)
    diag = int(math.sqrt(height**2 + width**2))
    
    for i in range(-diag, diag, spacing):
        line_points = []
        
        for t in range(-diag, diag):
            x = int(i * math.cos(angle_rad) - t * math.sin(angle_rad))
            y = int(i * math.sin(angle_rad) + t * math.cos(angle_rad))
            
            if 0 <= x < width and 0 <= y < height:
                brightness = img[y, x]
                threshold = 180 - brightness // 2
                
                if brightness > threshold:
                    if line_points:
                        line_points.append((x, y))
                    else:
                        line_points = [(x, y)]
                else:
                    if len(line_points) > 5:
                        lines.append(line_points.copy())
                    line_points = []
            else:
                if len(line_points) > 5:
                    lines.append(line_points.copy())
                line_points = []
        
        if len(line_points) > 5:
            lines.append(line_points.copy())
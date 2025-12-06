import datetime
import math
from typing import List, Tuple
import numpy as np

def generate_sketch_gcode(hatching_lines: List[List[Tuple[float, float]]], 
                         contours: List[np.ndarray],
                         scale_factor: float = 0.3, 
                         pen_up_z: float = 5.0, 
                         pen_down_z: float = -0.5,
                         feed_rate: float = 800, 
                         rapid_feed_rate: float = 2000,
                         draw_contours: bool = True, 
                         draw_hatching: bool = True,
                         work_area: Tuple[float, float] = (200, 200), 
                         start_point: Tuple[float, float] = (10, 10),
                         optimize_order: bool = True) -> str:
    
    gcode_parts = []
    
    gcode_parts.extend([
        "; Drawing G-code",
        f"; Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "G21 G90 G94",
        f"G0 Z{pen_up_z:.1f} F{rapid_feed_rate}",
        f"G0 X{start_point[0]:.1f} Y{start_point[1]:.1f}",
        ""
    ])
    
    if draw_contours and contours:
        if optimize_order and len(contours) > 1:
            contours = _optimize_contour_order(contours)
        
        for i, contour in enumerate(contours):
            if len(contour) < 3:
                continue
            
            first_point = contour[0][0]
            start_x = first_point[0] * scale_factor
            start_y = first_point[1] * scale_factor
            
            gcode_parts.extend([
                f"G0 X{start_x:.1f} Y{start_y:.1f} F{rapid_feed_rate}",
                f"G1 Z{pen_down_z:.1f} F{feed_rate//2}"
            ])
            
            last_x, last_y = start_x, start_y
            min_dist_sq = 0.5 * 0.5 / (scale_factor * scale_factor)
            
            for j in range(1, len(contour)):
                point = contour[j][0]
                x, y = point[0] * scale_factor, point[1] * scale_factor
                
                dx, dy = x - last_x, y - last_y
                if dx*dx + dy*dy > min_dist_sq:
                    gcode_parts.append(f"G1 X{x:.1f} Y{y:.1f} F{feed_rate}")
                    last_x, last_y = x, y
            
            if len(contour) > 2:
                gcode_parts.append(f"G1 X{start_x:.1f} Y{start_y:.1f} F{feed_rate}")
            
            gcode_parts.append(f"G1 Z{pen_up_z:.1f} F{rapid_feed_rate}")
    
    if draw_hatching and hatching_lines:
        if optimize_order and len(hatching_lines) > 1:
            hatching_lines = _optimize_hatching_order(hatching_lines, scale_factor)
        
        for i, line in enumerate(hatching_lines):
            if len(line) < 2:
                continue
            
            start_x = line[0][0] * scale_factor
            start_y = line[0][1] * scale_factor
            
            gcode_parts.extend([
                f"G0 X{start_x:.1f} Y{start_y:.1f} F{rapid_feed_rate}",
                f"G1 Z{pen_down_z*0.7:.1f} F{feed_rate//2}"
            ])
            
            last_x, last_y = start_x, start_y
            min_dist_sq = 0.3 * 0.3 / (scale_factor * scale_factor)
            
            for j in range(1, len(line)):
                x, y = line[j][0] * scale_factor, line[j][1] * scale_factor
                dx, dy = x - last_x, y - last_y
                
                if dx*dx + dy*dy > min_dist_sq:
                    gcode_parts.append(f"G1 X{x:.1f} Y{y:.1f} F{feed_rate}")
                    last_x, last_y = x, y
            
            gcode_parts.append(f"G1 Z{pen_up_z:.1f} F{rapid_feed_rate}")
    
    gcode_parts.extend([
        "",
        "G0 X0 Y0",
        f"G1 Z{pen_up_z + 15:.1f} F1000",
        "M30"
    ])
    
    return "\n".join(gcode_parts)

def _optimize_contour_order(contours: List[np.ndarray]) -> List[np.ndarray]:
    if len(contours) <= 2:
        return contours
    
    start_points = []
    for contour in contours:
        if len(contour) > 0:
            start_points.append(tuple(contour[0][0]))
        else:
            start_points.append((0, 0))
    
    optimized = []
    visited = [False] * len(contours)
    
    current_idx = 0
    optimized.append(contours[current_idx])
    visited[current_idx] = True
    
    while len(optimized) < len(contours):
        min_dist = float('inf')
        nearest_idx = -1
        
        for j in range(len(contours)):
            if not visited[j]:
                last_point = contours[current_idx][-1][0]
                next_start = start_points[j]
                
                dx = last_point[0] - next_start[0]
                dy = last_point[1] - next_start[1]
                dist = dx*dx + dy*dy
                
                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = j
        
        if nearest_idx != -1:
            current_idx = nearest_idx
            optimized.append(contours[current_idx])
            visited[current_idx] = True
        else:
            for j in range(len(contours)):
                if not visited[j]:
                    optimized.append(contours[j])
                    visited[j] = True
                    current_idx = j
                    break
    
    return optimized

def _optimize_hatching_order(lines: List[List[Tuple[float, float]]], 
                           scale_factor: float) -> List[List[Tuple[float, float]]]:
    if len(lines) <= 2:
        return lines
    
    start_points = [(line[0][0] * scale_factor, line[0][1] * scale_factor) 
                    for line in lines if len(line) > 0]
    
    optimized = []
    visited = [False] * len(lines)
    
    current_idx = 0
    optimized.append(lines[current_idx])
    visited[current_idx] = True
    
    while len(optimized) < len(lines):
        min_dist = float('inf')
        nearest_idx = -1
        
        for j in range(len(lines)):
            if not visited[j] and len(lines[j]) > 0:
                last_point = lines[current_idx][-1]
                last_x, last_y = last_point[0] * scale_factor, last_point[1] * scale_factor
                next_start = start_points[j]
                
                dx = last_x - next_start[0]
                dy = last_y - next_start[1]
                dist = dx*dx + dy*dy
                
                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = j
        
        if nearest_idx != -1:
            current_idx = nearest_idx
            optimized.append(lines[current_idx])
            visited[current_idx] = True
        else:
            for j in range(len(lines)):
                if not visited[j]:
                    optimized.append(lines[j])
                    visited[j] = True
                    current_idx = j
                    break
    
    return optimized
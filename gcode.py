import datetime

def generate_gcode(contours, scale_factor, pen_up_z, pen_down_z, feed_rate):
    gcode_lines = [
        "G21",
        "G90",
        f"G1 Z{pen_up_z} F1000",
        "G0 X10 Y10 F3000",
    ]
    
    for i, contour in enumerate(contours):
        if len(contour) < 3:
            continue
            
        x, y = contour[0][0]
        gcode_lines.append(f"G0 X{x * scale_factor} Y{y * scale_factor} F3000")
        gcode_lines.append(f"G1 Z{pen_down_z} F1000")
        
        for point in contour[1:]:
            x, y = point[0]
            gcode_lines.append(f"G1 X{x * scale_factor} Y{y * scale_factor} F{feed_rate}")
        
        first_x, first_y = contour[0][0]
        last_x, last_y = contour[-1][0]
        if abs(last_x - first_x) > 2 or abs(last_y - first_y) > 2:
            gcode_lines.append(f"G1 X{first_x * scale_factor} Y{first_y * scale_factor} F{feed_rate}")
        
        gcode_lines.append(f"G1 Z{pen_up_z} F3000")
    
    gcode_lines.extend([
        "G0 X0 Y0 F3000",
        f"G1 Z{pen_up_z} F1000",
        "M84",
    ])
    
    return "\n".join(gcode_lines)
import numpy as np
import cv2

def auto_canny_thresholds(image):
    v = np.median(image)
    
    sigma = 0.33
    if v < 128:
        sigma = 0.25
    else:
        sigma = 0.35
        
    image_std = np.std(image)
    if image_std < 20:
        sigma = 0.15
    elif image_std > 60:
        sigma = 0.4
        
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    
    return lower, upper

def process_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    canny_min, canny_max = auto_canny_thresholds(gray)
    
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    edges = cv2.Canny(blurred, canny_min, canny_max)
    
    contours, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    contour_img = np.zeros_like(img)
    cv2.drawContours(contour_img, contours, -1, (0, 0, 255), 1)
    
    return contour_img, contours, canny_min, canny_max
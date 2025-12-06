import numpy as np
import cv2

def get_contours(img, canny_min=50, canny_max=150, blur_kernel=5, blur_sigma=1.0):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), blur_sigma)
    edges = cv2.Canny(blurred, canny_min, canny_max)
    
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    edges = cv2.erode(edges, kernel, iterations=1)
    
    contours, hierarchy = cv2.findContours(
        edges, 
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_NONE
    )
    
    min_contour_length = 30
    filtered_contours = []
    
    if len(contours) > 0 and hierarchy is not None:
        for i, contour in enumerate(contours):
            if len(contour) >= min_contour_length:
                filtered_contours.append(contour)
    
    return edges, filtered_contours
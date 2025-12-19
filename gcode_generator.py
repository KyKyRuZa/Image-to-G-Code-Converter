import datetime
import math
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from abc import ABC, abstractmethod
from utils import transform_coordinates, calculate_safe_z, validate_numeric_input
from config import DEFAULT_CONFIG


class OptimizationStrategy(ABC):
    
    @abstractmethod
    def optimize(self, items: List[Any], scale_factor: float = 1.0) -> List[Any]:
        pass
    
    @abstractmethod
    def _extract_points(self, items: List[Any]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        pass
    
    def _greedy_sort(self, points: List[Tuple[Tuple[float, float], Tuple[float, float]]]) -> List[int]:
        n = len(points)
        if n <= 1:
            return list(range(n))
        
        visited = [False] * n
        order = [0]
        visited[0] = True
        
        for _ in range(1, n):
            last_idx = order[-1]
            last_end = points[last_idx][1]
            
            min_dist = float('inf')
            next_idx = -1
            
            for i in range(n):
                if not visited[i]:
                    start = points[i][0]
                    dist = math.hypot(last_end[0] - start[0], last_end[1] - start[1])
                    if dist < min_dist:
                        min_dist = dist
                        next_idx = i
            
            if next_idx != -1:
                order.append(next_idx)
                visited[next_idx] = True
            else:
                for i in range(n):
                    if not visited[i]:
                        order.append(i)
                        visited[i] = True
                        break
        
        return order


class ContourOptimization(OptimizationStrategy):

    def optimize(self, contours: List[np.ndarray], scale_factor: float = 1.0) -> List[np.ndarray]:
        if len(contours) <= 1:
            return contours
        points = self._extract_points(contours)
        if not points:
            return contours
        optimized_indices = self._greedy_sort(points)
        return [contours[i] for i in optimized_indices]
    
    def _extract_points(self, contours: List[np.ndarray]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        points = []
        for contour in contours:
            if len(contour) >= 2:
                start = (float(contour[0][0][0]), float(contour[0][0][1]))
                end = (float(contour[-1][0][0]), float(contour[-1][0][1]))
                points.append((start, end))
        return points


class HatchingOptimization(OptimizationStrategy):

    def optimize(self, lines: List[List[Tuple[float, float]]], scale_factor: float = 1.0) -> List[List[Tuple[float, float]]]:
        if len(lines) <= 1:
            return lines
        points = self._extract_points(lines)
        if not points:
            return lines
        optimized_indices = self._greedy_sort(points)
        return [lines[i] for i in optimized_indices]
    
    def _extract_points(self, lines: List[List[Tuple[float, float]]]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        points = []
        for line in lines:
            if len(line) >= 2:
                start = (float(line[0][0]), float(line[0][1]))
                end = (float(line[-1][0]), float(line[-1][1]))
                points.append((start, end))
        return points


class GCodeBuilder:
    
    def __init__(self):
        self.lines = []
        self.indent = ""
    
    def add_line(self, line: str):
        if line.strip():
            self.lines.append(f"{self.indent}{line}")
        else:
            self.lines.append("")
    
    def add_comment(self, comment: str):
        self.add_line(f"; {comment}")
    
    def add_section_header(self, title: str):
        self.add_line("")
        self.add_comment("=" * 50)
        self.add_comment(title)
        self.add_comment("=" * 50)
        self.add_line("")
    
    def add_movement(self, x: float, y: float, z: Optional[float] = None, 
                    feed_rate: int = 0, comment: str = ""):
        cmd_parts = ["G0" if feed_rate == 0 else "G1"]
        
        x = max(0.0, min(x, 1000.0))  
        y = max(0.0, min(y, 1000.0))
        
        cmd_parts.append(f"X{x:.2f}")
        cmd_parts.append(f"Y{y:.2f}")
        
        if z is not None:
            z = max(-20.0, min(z, 50.0))
            cmd_parts.append(f"Z{z:.2f}")
        
        if feed_rate > 0:
            cmd_parts.append(f"F{feed_rate}")
        
        cmd = " ".join(cmd_parts)
        if comment:
            cmd += f" ; {comment}"
        
        self.add_line(cmd)
    
    def get_gcode(self) -> str:
        return "\n".join(self.lines)


class GCodeGenerator:
    
    def __init__(self, config: Dict[str, Any]):
        self.config = self._validate_config(config)
        self.safe_z = calculate_safe_z(self.config["pen_up_z"])
        self.builder = GCodeBuilder()
    
    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        validated = {}
        
        numeric_params = {
            "scale_factor": (0.01, 1.0),
            "pen_up_z": (1.0, 50.0),
            "pen_down_z": (-10.0, -0.1),
            "hatch_depth": (-10.0, -0.1),
            "feed_rate": (100, 5000),
            "rapid_feed_rate": (500, 10000),
            "work_area_x": (50, 1000),
            "work_area_y": (50, 1000),
        }
        
        for param, (min_val, max_val) in numeric_params.items():
            validated[param] = validate_numeric_input(
                config.get(param, DEFAULT_CONFIG[param]),
                min_val, max_val
            )
        
        boolean_params = ["draw_contours", "draw_hatching", "optimize_order"]
        for param in boolean_params:
            validated[param] = config.get(param, DEFAULT_CONFIG[param])
        
        return validated
    
    def generate(self, hatching_lines: List[List[Tuple[float, float]]], 
                contours: List[np.ndarray],
                image_width: int,
                image_height: int) -> str:
        self._add_header(image_width, image_height)
        
        if self.config["draw_contours"] and contours:
            self._add_contours(contours, image_width, image_height)
        
        if self.config["draw_hatching"] and hatching_lines:
            self._add_hatching(hatching_lines, image_width, image_height)
        
        self._add_footer()
        return self.builder.get_gcode()
    
    def _add_header(self, image_width: int, image_height: int):
    
        self.builder.add_line("")
        self.builder.add_line("G21 ; Миллиметры")
        self.builder.add_line("G90 ; Абсолютные координаты")
        self.builder.add_line("G94 ; Единицы измерения в минуту")
        self.builder.add_movement(0, 0, self.safe_z, self.config["rapid_feed_rate"], 
                                 "Подъем пера на безопасную высоту")
        self.builder.add_movement(0, 0, comment="Возврат в начало координат")
        self.builder.add_line("")
    
    def _add_contours(self, contours: List[np.ndarray], image_width: int, image_height: int):
        self.builder.add_section_header("КОНТУРЫ")
        
        if self.config["optimize_order"] and len(contours) > 1:
            optimizer = ContourOptimization()
            contours = optimizer.optimize(contours)
        
        for i, contour in enumerate(contours):
            if len(contour) < 3:
                continue
            
            self.builder.add_comment(f"Контур #{i+1}, точек: {len(contour)}")
            self._process_contour(contour, image_width, image_height)
            self.builder.add_line("")
    
    def _process_contour(self, contour: np.ndarray, image_width: int, image_height: int):
        first_point = contour[0][0]
        x_mm, y_mm = transform_coordinates(
            first_point[0], first_point[1],
            image_width, image_height,
            self.config["scale_factor"],
            self.config["work_area_x"],
            self.config["work_area_y"]
        )
        
        self.builder.add_movement(x_mm, y_mm, feed_rate=self.config["rapid_feed_rate"],
                                comment="Быстрое перемещение к началу контура")
        self.builder.add_movement(x_mm, y_mm, self.config["pen_down_z"], 
                                feed_rate=self.config["feed_rate"] // 2,
                                comment="Опускание пера")
        
        last_x, last_y = x_mm, y_mm
        min_dist = 0.3
        
        for j in range(1, len(contour)):
            point = contour[j][0]
            x_mm, y_mm = transform_coordinates(
                point[0], point[1],
                image_width, image_height,
                self.config["scale_factor"],
                self.config["work_area_x"],
                self.config["work_area_y"]
            )
            
            if math.hypot(x_mm - last_x, y_mm - last_y) > min_dist:
                self.builder.add_movement(x_mm, y_mm, feed_rate=self.config["feed_rate"])
                last_x, last_y = x_mm, y_mm
        
        if len(contour) > 2:
            x_mm, y_mm = transform_coordinates(
                first_point[0], first_point[1],
                image_width, image_height,
                self.config["scale_factor"],
                self.config["work_area_x"],
                self.config["work_area_y"]
            )
            if math.hypot(x_mm - last_x, y_mm - last_y) > min_dist:
                self.builder.add_movement(x_mm, y_mm, feed_rate=self.config["feed_rate"])
        
        self.builder.add_movement(x_mm, y_mm, self.safe_z, 
                                feed_rate=self.config["rapid_feed_rate"],
                                comment="Подъем пера после контура")
    
    def _add_hatching(self, lines: List[List[Tuple[float, float]]], 
                     image_width: int, image_height: int):
        self.builder.add_section_header("ШТРИХОВКА")
        
        if self.config["optimize_order"] and len(lines) > 1:
            optimizer = HatchingOptimization()
            lines = optimizer.optimize(lines, self.config["scale_factor"])
        
        for i, line in enumerate(lines):
            if len(line) < 2:
                continue
            
            self.builder.add_comment(f"Линия штриховки #{i+1}, точек: {len(line)}")
            self._process_hatching_line(line, image_width, image_height)
            self.builder.add_line("")
    
    def _process_hatching_line(self, line: List[Tuple[float, float]], 
                             image_width: int, image_height: int):
        start_x, start_y = line[0]
        x_mm, y_mm = transform_coordinates(
            start_x, start_y,
            image_width, image_height,
            self.config["scale_factor"],
            self.config["work_area_x"],
            self.config["work_area_y"]
        )
        
        self.builder.add_movement(x_mm, y_mm, feed_rate=self.config["rapid_feed_rate"],
                                comment="Быстрое перемещение к началу линии")
        self.builder.add_movement(x_mm, y_mm, self.config["hatch_depth"], 
                                feed_rate=self.config["feed_rate"] // 2,
                                comment="Опускание пера для штриховки")
        
        last_x, last_y = x_mm, y_mm
        min_dist = 0.2
        
        for j in range(1, len(line)):
            x, y = line[j]
            x_mm, y_mm = transform_coordinates(
                x, y,
                image_width, image_height,
                self.config["scale_factor"],
                self.config["work_area_x"],
                self.config["work_area_y"]
            )
            
            if math.hypot(x_mm - last_x, y_mm - last_y) > min_dist:
                self.builder.add_movement(x_mm, y_mm, feed_rate=self.config["feed_rate"])
                last_x, last_y = x_mm, y_mm
        
        self.builder.add_movement(x_mm, y_mm, self.safe_z, 
                                feed_rate=self.config["rapid_feed_rate"],
                                comment="Подъем пера после штриховки")
    
    def _add_footer(self):
        self.builder.add_section_header("ЗАВЕРШЕНИЕ ПРОГРАММЫ")
        
        self.builder.add_movement(0, 0, feed_rate=self.config["rapid_feed_rate"],
                                comment="Возврат в начало координат")
        self.builder.add_movement(0, 0, self.safe_z + 10, 
                                feed_rate=self.config["rapid_feed_rate"] // 2,
                                comment="Дополнительный подъем")
        self.builder.add_line("M5 ; Выключить шпиндель (если используется)")
        self.builder.add_line("M30 ; Конец программы")


def generate_sketch_gcode(
    hatching_lines: List[List[Tuple[float, float]]], 
    contours: List[np.ndarray],
    image_width: int,
    image_height: int,
    config: dict,
    optimize_order: bool = True
) -> str:
    config = config.copy()
    config["optimize_order"] = optimize_order
    
    generator = GCodeGenerator(config)
    return generator.generate(hatching_lines, contours, image_width, image_height)
import numpy as np
from typing import List, Tuple, Dict, Optional, Protocol, runtime_checkable
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

CYRILLIC_WIDTHS = {
    'А': 16, 'Б': 16, 'В': 16, 'Г': 12, 'Д': 18, 'Е': 12, 'Ё': 12,
    'Ж': 24, 'З': 14, 'И': 16, 'Й': 16, 'К': 16, 'Л': 16, 'М': 18,
    'Н': 16, 'О': 16, 'П': 16, 'Р': 14, 'С': 14, 'Т': 18, 'У': 16,
    'Ф': 20, 'Х': 16, 'Ц': 18, 'Ч': 16, 'Ш': 24, 'Щ': 26, 'Ъ': 18,
    'Ы': 20, 'Ь': 14, 'Э': 16, 'Ю': 24, 'Я': 16,
    
    'а': 14, 'б': 14, 'в': 14, 'г': 10, 'д': 16, 'е': 12, 'ё': 12,
    'ж': 20, 'з': 12, 'и': 14, 'й': 14, 'к': 14, 'л': 14, 'м': 16,
    'н': 14, 'о': 14, 'п': 14, 'р': 14, 'с': 12, 'т': 16, 'у': 14,
    'ф': 18, 'х': 14, 'ц': 16, 'ч': 14, 'ш': 22, 'щ': 24, 'ъ': 16,
    'ы': 18, 'ь': 12, 'э': 14, 'ю': 22, 'я': 14,
    
    '0': 14, '1': 8, '2': 14, '3': 14, '4': 14, '5': 14, '6': 14,
    '7': 14, '8': 14, '9': 14,
    
    ' ': 8, '!': 4, '?': 14, ',': 4, '.': 4, ':': 4, ';': 6,
    '-': 12, '_': 16, '+': 16, '=': 16, '(': 10, ')': 10,
    '/': 12, '\\': 12, '|': 4, '[': 10, ']': 10,
    '"': 10, "'": 4, '№': 20, '—': 16, '…': 10,
}

class TextAlignment(Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"

@dataclass
class FontMetrics:
    base_width: float
    base_height: float
    line_height: float
    spacing: float
    char_widths: Dict[str, float]

class FontRenderer(ABC):
    
    @abstractmethod
    def get_character_path(self, char: str) -> List[List[Tuple[float, float]]]:
        pass
    
    @abstractmethod
    def get_character_width(self, char: str) -> float:
        pass
    
    @abstractmethod
    def get_metrics(self) -> FontMetrics:
        pass

class HersheyFont(FontRenderer):
    
    def __init__(self, font_dict: Dict[str, List[Tuple[int, int]]], 
                 scale: float = 1.0, spacing: float = 1.2, line_height: float = 1.5):
        self.font_dict = font_dict
        self.scale = scale
        self.spacing = spacing
        self.line_height = line_height
        self.char_widths = {}
        self._init_metrics()
    
    def _init_metrics(self):
        self.base_char_width = 16 * self.scale
        self.base_char_height = 30 * self.scale
    
    def get_character_width(self, char: str) -> float:
        return self.char_widths.get(char, self.base_char_width)
    
    def get_metrics(self) -> FontMetrics:
        return FontMetrics(
            base_width=self.base_char_width,
            base_height=self.base_char_height,
            line_height=self.line_height,
            spacing=self.spacing,
            char_widths=self.char_widths
        )
    
    def _scale_points(self, points: List[Tuple[int, int]]) -> List[Tuple[float, float]]:
        return [(x * self.scale, y * self.scale) for x, y in points]
    
    def _get_fallback_char(self, char: str) -> str:
        fallbacks = {
            'ё': 'е', 'Ё': 'Е',
            'ґ': 'г', 'Ґ': 'Г',
        }
        return fallbacks.get(char.lower(), char.upper())

class CyrillicHersheyFont(HersheyFont):
    
    def __init__(self, font_dict: Optional[Dict] = None, 
                 scale: float = 1.0, spacing: float = 1.2, line_height: float = 1.5):
        super().__init__(font_dict or self._load_default_font(), scale, spacing, line_height)
        self.char_widths = {char: width * scale for char, width in CYRILLIC_WIDTHS.items()}
    
    def _load_default_font(self) -> Dict:
        from hershey_cyrillic import HERSHEY_CYRILLIC_CALLIGRAPHIC
        return HERSHEY_CYRILLIC_CALLIGRAPHIC
    
    def get_character_path(self, char: str) -> List[List[Tuple[float, float]]]:
        char_to_use = char
        if char not in self.font_dict:
            char_to_use = self._get_fallback_char(char)
        
        if char_to_use not in self.font_dict:
            return []
        
        points = self.font_dict[char_to_use]
        if not points:
            return []
        
        scaled_points = self._scale_points(points)
        
        return [scaled_points] if len(scaled_points) > 1 else []

class TextLayoutEngine:
    
    def __init__(self, font: FontRenderer):
        self.font = font
        self.metrics = font.get_metrics()
    
    def layout_text(self, text: str, start_x: float = 0, start_y: float = 0,
                   max_width: Optional[float] = None) -> List[List[Tuple[float, float]]]:
        all_lines = []
        x_offset = start_x
        y_offset = start_y
        
        text_lines = text.split('\n') if '\n' in text else [text]
        
        for line in text_lines:
            x_offset = start_x
            words = line.split(' ')
            
            for i, word in enumerate(words):
                if i > 0:
                    space_width = self.font.get_character_width(' ')
                    if max_width and (x_offset + space_width) > (start_x + max_width):
                        self._new_line(y_offset, start_x)
                        y_offset = self._new_line(y_offset, start_x)
                    else:
                        x_offset += space_width
                
                for char in word:
                    char_width = self.font.get_character_width(char)
                    
                    if max_width and (x_offset + char_width) > (start_x + max_width):
                        y_offset = self._new_line(y_offset, start_x)
                    
                    char_paths = self.font.get_character_path(char)
                    for path in char_paths:
                        offset_path = [(x + x_offset, y + y_offset) for x, y in path]
                        all_lines.append(offset_path)
                    
                    x_offset += char_width * self.metrics.spacing
            
            y_offset = self._new_line(y_offset, start_x)
        
        return all_lines
    
    def _new_line(self, current_y: float, start_x: float) -> float:
        return current_y - self.metrics.base_height * self.metrics.line_height
    
    def calculate_text_size(self, text: str) -> Tuple[float, float]:
        max_width = 0
        lines = text.split('\n') if '\n' in text else [text]
        line_count = len(lines)
        
        for line in lines:
            line_width = self._calculate_line_width(line)
            max_width = max(max_width, line_width)
        
        height = self.metrics.base_height * line_count * self.metrics.line_height
        return (max_width, height)
    
    def _calculate_line_width(self, line: str) -> float:
        width = 0
        words = line.split(' ')
        
        for i, word in enumerate(words):
            if i > 0:
                width += self.font.get_character_width(' ')
            
            for char in word:
                width += self.font.get_character_width(char) * self.metrics.spacing
        
        return width

class TextToContoursConverter:
    
    @staticmethod
    def convert(text_paths: List[List[Tuple[float, float]]]) -> List[np.ndarray]:
        contours = []
        
        for path in text_paths:
            if len(path) < 2:
                continue
            
            contour = np.array([[[int(x), int(y)]] for x, y in path], dtype=np.int32)
            contours.append(contour)
        
        return contours

class TextGCodeGenerator:
    
    def __init__(self, font: FontRenderer, config: Dict):
        self.font = font
        self.config = config
        self.metrics = font.get_metrics()
    
    def generate(self, text: str, start_x: float = 0, start_y: float = 0,
                align: TextAlignment = TextAlignment.LEFT) -> str:
        start_x = self._adjust_position_for_alignment(text, start_x, align)
        
        layout_engine = TextLayoutEngine(self.font)
        text_paths = layout_engine.layout_text(
            text, 
            start_x / self.metrics.base_width, 
            start_y / self.metrics.base_height
        )
        
        return self._build_gcode(text_paths, text, start_x, start_y, align)
    
    def _adjust_position_for_alignment(self, text: str, start_x: float, 
                                      align: TextAlignment) -> float:
        if align == TextAlignment.LEFT:
            return start_x
        
        layout_engine = TextLayoutEngine(self.font)
        text_width, _ = layout_engine.calculate_text_size(text)
        text_width_mm = text_width * self.metrics.base_width
        
        if align == TextAlignment.CENTER:
            return start_x - text_width_mm / 2
        elif align == TextAlignment.RIGHT:
            return start_x - text_width_mm
        return start_x
    
    def _build_gcode(self, text_paths: List[List[Tuple[float, float]]], 
                    text: str, start_x: float, start_y: float, 
                    align: TextAlignment) -> str:
        gcode_lines = []
        pen_up = True
        
        gcode_lines.extend([
            "; === РУССКИЙ ТЕКСТ ===",
            f"; Текст: {text}",
            f"; Позиция: X={start_x:.2f}mm Y={start_y:.2f}mm",
            f"; Масштаб: {self.metrics.base_width:.2f}, Выравнивание: {align.value}",
            "",
            "G21 ; мм",
            "G90 ; абсолютные координаты",
            f"G0 Z{self.config['pen_up_z']:.2f} F{self.config['rapid_feed_rate']}"
        ])
        
        for path in text_paths:
            if not path:
                continue
            
            for i, (x, y) in enumerate(path):
                x_mm = x * self.metrics.base_width
                y_mm = y * self.metrics.base_height
                
                if i == 0:
                    if not pen_up:
                        gcode_lines.append(f"G0 Z{self.config['pen_up_z']:.2f}")
                        pen_up = True
                    
                    gcode_lines.append(
                        f"G0 X{x_mm:.2f} Y{y_mm:.2f} F{self.config['rapid_feed_rate']}"
                    )
                    gcode_lines.append(
                        f"G1 Z{self.config['pen_down_z']:.2f} F{self.config['feed_rate']}"
                    )
                    pen_up = False
                else:
                    gcode_lines.append(
                        f"G1 X{x_mm:.2f} Y{y_mm:.2f} F{self.config['feed_rate']}"
                    )
        
        if not pen_up:
            gcode_lines.append(f"G0 Z{self.config['pen_up_z']:.2f} F{self.config['rapid_feed_rate']}")
        
        return "\n".join(gcode_lines)

class TextComposer:
 
    def __init__(self, font: FontRenderer, config: Dict):
        self.font = font
        self.config = config
        self.metrics = font.get_metrics()
    
    def add_text(self, text: str, existing_contours: List[np.ndarray], 
                position: Tuple[float, float] = (0.5, 0.5),
                align: TextAlignment = TextAlignment.LEFT) -> List[np.ndarray]:
        if not text.strip():
            return existing_contours
        
        text_pos = self._calculate_text_position(existing_contours, position, text, align)
        
        layout_engine = TextLayoutEngine(self.font)
        text_paths = layout_engine.layout_text(
            text, 
            text_pos[0] / self.metrics.base_width, 
            text_pos[1] / self.metrics.base_height
        )
        
        converter = TextToContoursConverter()
        text_contours = converter.convert(text_paths)
        
        return existing_contours + text_contours
    
    def _calculate_text_position(self, contours: List[np.ndarray], 
                               position: Tuple[float, float], text: str,
                               align: TextAlignment) -> Tuple[float, float]:
        if contours:
            all_points = np.vstack([c.reshape(-1, 2) for c in contours if len(c) > 0])
            min_x, min_y = all_points.min(axis=0)
            max_x, max_y = all_points.max(axis=0)
            
            text_x = min_x + (max_x - min_x) * position[0]
            text_y = min_y + (max_y - min_y) * position[1]
        else:
            work_x = self.config.get("work_area_x", 100)
            work_y = self.config.get("work_area_y", 100)
            text_x = work_x * position[0]
            text_y = work_y * position[1]
        
        if align != TextAlignment.LEFT:
            layout_engine = TextLayoutEngine(self.font)
            text_width, _ = layout_engine.calculate_text_size(text)
            text_width_px = text_width * self.metrics.base_width
            
            if align == TextAlignment.CENTER:
                text_x -= text_width_px / 2
            elif align == TextAlignment.RIGHT:
                text_x -= text_width_px
        
        return (text_x, text_y)

def text_to_gcode_cyrillic(text: str, config: dict, 
                          start_x: float = 0, start_y: float = 0,
                          align: str = 'left') -> str:
    try:
        alignment = TextAlignment(align.lower())
    except ValueError:
        alignment = TextAlignment.LEFT
    
    font_scale = config.get("font_scale", 0.1)
    font_spacing = config.get("font_spacing", 1.2)
    
    font = CyrillicHersheyFont(scale=font_scale, spacing=font_spacing)
    generator = TextGCodeGenerator(font, config)
    
    return generator.generate(text, start_x, start_y, alignment)

def add_cyrillic_text_to_contours(text: str, contours: List[np.ndarray], config: dict, 
                                 position: Tuple[float, float] = (0.5, 0.5),
                                 align: str = 'left') -> List[np.ndarray]:
    try:
        alignment = TextAlignment(align.lower())
    except ValueError:
        alignment = TextAlignment.LEFT
    
    font_scale = config.get("font_scale", 0.15)
    font = CyrillicHersheyFont(scale=font_scale)
    
    composer = TextComposer(font, config)
    return composer.add_text(text, contours, position, alignment)
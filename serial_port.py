import serial
import serial.tools.list_ports
import threading
import time
import asyncio
import logging
from datetime import datetime
from bleak import BleakScanner, BleakClient
import os

class Connection:
    def __init__(self, gui_app=None):
        self.gui_app = gui_app
        self.is_connected = False
        self.setup_logger()
    
    def setup_logger(self):
        logging.basicConfig(
            filename='connection.log',
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def update_gui_status(self, message, success=True):
        if hasattr(self.gui_app, 'update_status_message'):
            self.gui_app.root.after(0, lambda: self.gui_app.update_status_message(message))
    
    def update_gui_connection_status(self, status_text, is_connected):
        if hasattr(self.gui_app, 'update_connection_status'):
            self.gui_app.root.after(0, lambda: self.gui_app.update_connection_status(status_text, is_connected))

class SerialConnection(Connection):
    def __init__(self, gui_app=None):
        super().__init__(gui_app)
        self.serial_connection = None
        self.receive_queue = []
        self.receive_thread = None
        self.send_thread = None
        self.stop_receive = threading.Event()
        self.stop_send = threading.Event()  
        self.send_queue = []
        self.send_lock = threading.Lock()
    
    def get_available_ports(self):
        ports = []
        try:
            available_ports = serial.tools.list_ports.comports()
            for port in available_ports:
                ports.append({
                    'id': port.device,
                    'name': f"{port.device} - {port.description.split(' (')[0]}"
                })
            self.logger.info(f"Найдено последовательных портов: {len(ports)}")
            return ports
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка портов: {e}")
            return []
    
    def connect(self, port_name):
        try:
            if self.is_connected:
                self.disconnect()
                
            self.logger.info(f"Попытка подключения к {port_name} с baudrate=115200")
            
            self.stop_receive.clear()
            self.stop_send.clear()
            
            self.serial_connection = serial.Serial(
                port=port_name,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,
                write_timeout=1
            )
            
            if self.serial_connection.is_open:
                self.is_connected = True
                
                self.stop_receive.clear()
                self.receive_thread = threading.Thread(target=self._receive_data, daemon=True)
                self.receive_thread.start()
                
                status_msg = f"Успешное подключение к {port_name}"
                self.logger.info(status_msg)
                self.update_gui_connection_status(status_msg, True)
                self.update_gui_status("Подключение установлено", True)
                return True, status_msg
            else:
                error_msg = f"Не удалось открыть порт {port_name}"
                self.logger.error(error_msg)
                return False, error_msg
                
        except serial.SerialException as e:
            error_msg = f"Ошибка SerialException: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Ошибка подключения: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def disconnect(self):
        self.stop_send.set()
        self.stop_receive.set()
        
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.join(timeout=1.0)
        
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)
        
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
                self.logger.info("Соединение закрыто")
            except Exception as e:
                self.logger.error(f"Ошибка при закрытии соединения: {e}")
        
        prev_connected = self.is_connected
        self.is_connected = False
        self.serial_connection = None
        self.send_queue.clear()
        
        if prev_connected:
            status_msg = "Отключено от последовательного порта"
            self.update_gui_connection_status(status_msg, False)
            self.update_gui_status(status_msg, False)
        
        return True, "Отключено"
    
    def _receive_data(self):
        while not self.stop_receive.is_set() and self.serial_connection and self.serial_connection.is_open:
            try:
                if self.serial_connection.in_waiting > 0:
                    data = self.serial_connection.read(self.serial_connection.in_waiting)
                    if data:
                        decoded_data = data.decode('utf-8', errors='ignore').strip()
                        if decoded_data:
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            self.receive_queue.append(f"[{timestamp}] {decoded_data}")
                            
                            if len(self.receive_queue) > 20:
                                self.receive_queue.pop(0)
                            
                            self.update_gui_status(decoded_data, True)
                            self.logger.info(f"Получено: {decoded_data}")
            
            except serial.SerialException:
                self.logger.warning("Соединение разорвано")
                break
            except Exception as e:
                self.logger.error(f"Ошибка при чтении данных: {e}")
            
            time.sleep(0.05)
    
    def send_gcode(self, gcode_lines):
        if not self.is_connected or not self.serial_connection:
            error_msg = "Нет подключения к устройству"
            self.logger.warning(error_msg)
            return False, error_msg
        
        self.stop_send.clear()
        
        with self.send_lock:
            self.send_queue = gcode_lines.copy()
        
        self.send_thread = threading.Thread(target=self._send_gcode_thread, daemon=True)
        self.send_thread.start()
        
        return True, "Отправка G-кода начата"
    
    def _send_gcode_thread(self):
        if not self.is_connected or not self.serial_connection:
            return
        
        try:
            self.update_gui_status("Начало отправки G-кода...", True)
            
            init_commands = [
                "M110 N0",
                "G90",
                "G21",
            ]
            
            for cmd in init_commands:
                if self.stop_send.is_set():
                    self.logger.info("Отправка прервана (инициализация)")
                    return
                success, message = self._send_line(cmd + '\n')
                if not success:
                    self.logger.warning(f"Ошибка отправки инициализационной команды: {cmd}")
                time.sleep(0.1)
            
            total_lines = len(self.send_queue)
            sent_lines = 0
            errors = 0
            
            with self.send_lock:
                for i, line in enumerate(self.send_queue, 1):
                    if self.stop_send.is_set():
                        self.logger.info(f"Отправка прервана на строке {i}")
                        self.update_gui_status(f"Отправка прервана на строке {i}/{total_lines}", False)
                        break
                    
                    line = line.strip()
                    
                    if not line or line.startswith(';') or line.startswith('('):
                        continue
                    
                    success, message = self._send_line(line + '\n')
                    
                    if not success:
                        errors += 1
                        self.logger.error(f"Ошибка отправки строки {i}: {line}")
                    
                    if i % 5 == 0:
                        progress = f"Отправлено: {i}/{total_lines} строк"
                        self.update_gui_status(progress, True)
                    
                    time.sleep(0.03)
                    sent_lines += 1
            
            if not self.stop_send.is_set():
                end_commands = [
                    "G0 X0 Y0 F1500",
                    "M30"
                ]
                
                for cmd in end_commands:
                    success, message = self._send_line(cmd + '\n')
                    if not success:
                        self.logger.warning(f"Ошибка отправки завершающей команды: {cmd}")
                    time.sleep(0.1)
            
            result_msg = f"Отправлено {sent_lines} строк, ошибок: {errors}"
            if self.stop_send.is_set():
                result_msg += " (ПРЕРВАНО)"
            self.logger.info(result_msg)
            self.update_gui_status(result_msg, errors == 0)
            
        except Exception as e:
            error_msg = f"Ошибка отправки G-кода: {str(e)}"
            self.logger.exception(error_msg)
            self.update_gui_status(error_msg, False)
    
    def _send_line(self, line):
        if not self.is_connected or not self.serial_connection:
            return False, "Нет подключения"
        
        if self.stop_send.is_set():
            return False, "Отправка прервана"
        
        try:
            self.serial_connection.write(line.encode('utf-8'))
            self.serial_connection.flush()
            self.logger.debug(f"Отправлено: {line.strip()}")
            return True, "Данные отправлены"
        except serial.SerialTimeoutException as e:
            error_msg = f"Таймаут отправки: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Ошибка отправки: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def get_received_data(self):
        if self.receive_queue:
            return "\n".join(self.receive_queue)
        return ""
    
    def emergency_stop(self):
        if not self.is_connected:
            return False, "Нет подключения"
        
        try:
            self.stop_send.set()
            
            emergency_commands = [
                '\x18',  
                '!',     
                'M112',  
                'M0',   
                'M5',   
                'M999', 
            ]
            
            success_count = 0
            for cmd in emergency_commands:
                try:
                    if cmd == '\x18':
                        self.serial_connection.write(b'\x18')
                    else:
                        self.serial_connection.write((cmd + '\n').encode('utf-8'))
                    self.serial_connection.flush()
                    success_count += 1
                    time.sleep(0.01)
                except:
                    pass
            
            try:
                while self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)
                    time.sleep(0.001)
            except:
                pass
            
            status_msg = f"Экстренная остановка отправлена ({success_count}/6 команд)"
            self.logger.warning(status_msg)
            self.update_gui_status("ЭКСТРЕННАЯ ОСТАНОВКА! Устройство должно остановиться", False)
            
            if hasattr(self.gui_app, 'emergency_stop_activated'):
                self.gui_app.root.after(0, lambda: setattr(self.gui_app, 'emergency_stop_activated', True))
            
            return True, status_msg
            
        except Exception as e:
            error = f"Ошибка экстренной остановки: {e}"
            self.logger.error(error)
            return False, error

class BluetoothConnection(Connection):
    def __init__(self, gui_app=None):
        super().__init__(gui_app)
        self.client = None
        self.device_address = None
        self.characteristic_uuid = None
        self.stop_send = asyncio.Event()
    
    async def get_available_devices(self):
        try:
            self.logger.info("Сканирование Bluetooth устройств...")
            devices = await BleakScanner.discover(timeout=5.0)
            
            cnc_devices = []
            for device in devices:
                name = device.name or ""
                device_name_lower = name.lower()
                if any(kw in device_name_lower for kw in [
                    'cnc', 'plotter', 'grbl', 'marlin', 'printer', 'serial',
                    'arduino', 'stm32', 'esp32', 'controller', 'machine'
                ]):
                    cnc_devices.append({
                        'id': device.address,
                        'name': f"{name} ({device.address})"
                    })
            
            if not cnc_devices:
                cnc_devices = [{
                    'id': device.address,
                    'name': f"{device.name or 'Unknown'} ({device.address})"
                } for device in devices]
            
            self.logger.info(f"Найдено Bluetooth устройств: {len(cnc_devices)}")
            return cnc_devices
            
        except Exception as e:
            self.logger.error(f"Ошибка сканирования Bluetooth: {str(e)}")
            return []
    
    async def connect(self, device_address):
        try:
            if self.is_connected:
                await self.disconnect()
            
            self.logger.info(f"Подключение к Bluetooth устройству: {device_address}")
            self.update_gui_status(f"Подключение к {device_address}...", True)
            
            self.client = BleakClient(device_address)
            await self.client.connect(timeout=15.0)
            
            if self.client.is_connected:
                self.is_connected = True
                self.device_address = device_address
                
                self.characteristic_uuid = await self._find_write_characteristic()
                
                status_msg = f"Успешное подключение к {device_address}"
                self.logger.info(status_msg)
                self.update_gui_connection_status(status_msg, True)
                self.update_gui_status("Bluetooth подключение установлено", True)
                return True, status_msg
            else:
                error_msg = f"Не удалось подключиться к {device_address}"
                self.logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Ошибка Bluetooth подключения: {str(e)}"
            self.logger.exception(error_msg)
            self.update_gui_status(error_msg, False)
            return False, error_msg
    
    async def _find_write_characteristic(self):
        if not self.client:
            return None
        
        try:
            standard_uuids = [
                "0000fff1-0000-1000-8000-00805f9b34fb",
                "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
                "0000fe02-0000-1000-8000-00805f9b34fb",
                "0000ff02-0000-1000-8000-00805f9b34fb",
            ]
            
            for service in self.client.services:
                for char in service.characteristics:
                    char_uuid_lower = char.uuid.lower()
                    if 'write' in char.properties and any(std_uuid in char_uuid_lower for std_uuid in standard_uuids):
                        self.logger.info(f"Найдена стандартная характеристика для записи: {char.uuid}")
                        return char.uuid
            
            for service in self.client.services:
                for char in service.characteristics:
                    properties = [prop.lower() for prop in char.properties]
                    if 'write' in properties or 'write-without-response' in properties:
                        self.logger.info(f"Используется первая доступная характеристика для записи: {char.uuid}")
                        return char.uuid
            
            self.logger.warning("Не найдено характеристик для записи")
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка поиска характеристики: {str(e)}")
            return None
    
    async def disconnect(self):
        try:
            self.stop_send.set()
            
            if self.client and self.client.is_connected:
                await self.client.disconnect()
                self.logger.info("Bluetooth соединение закрыто")
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии Bluetooth соединения: {e}")
        
        prev_connected = self.is_connected
        self.is_connected = False
        self.client = None
        self.device_address = None
        self.characteristic_uuid = None
        self.stop_send.clear()
        
        if prev_connected:
            status_msg = "Отключено от Bluetooth устройства"
            self.update_gui_connection_status(status_msg, False)
            self.update_gui_status(status_msg, False)
        
        return True, "Отключено"
    
    async def send_gcode(self, gcode_lines):
        if not self.is_connected or not self.client or not self.characteristic_uuid:
            error_msg = "Нет подключения или не определена характеристика для записи"
            self.logger.warning(error_msg)
            return False, error_msg
        
        try:
            self.stop_send.clear()
            
            self.update_gui_status("Начало отправки G-кода через Bluetooth...", True)
            
            init_commands = [
                "M110 N0\n",
                "G90\n",
                "G21\n",
            ]
            
            for cmd in init_commands:
                if self.stop_send.is_set():
                    return False, "Отправка прервана экстренной остановкой"
                success, message = await self._send_line(cmd)
                if not success:
                    self.logger.warning(f"Ошибка отправки инициализационной команды: {cmd}")
                await asyncio.sleep(0.1)
            
            total_lines = len(gcode_lines)
            sent_lines = 0
            errors = 0
            
            for i, line in enumerate(gcode_lines, 1):
                if self.stop_send.is_set():
                    return False, "Отправка прервана экстренной остановкой"
                
                line = line.strip()
                
                if not line or line.startswith(';') or line.startswith('('):
                    continue
                
                success, message = await self._send_line(line + '\n')
                
                if not success:
                    errors += 1
                    self.logger.error(f"Ошибка отправки строки {i}: {line}")
                
                if i % 5 == 0:
                    progress = f"Bluetooth: Отправлено {i}/{total_lines} строк"
                    self.update_gui_status(progress, True)
                
                await asyncio.sleep(0.05)
                sent_lines += 1
            
            if not self.stop_send.is_set():
                end_commands = [
                    "G0 X0 Y0 F1500\n",
                    "M30\n"
                ]
                
                for cmd in end_commands:
                    success, message = await self._send_line(cmd)
                    if not success:
                        self.logger.warning(f"Ошибка отправки завершающей команды: {cmd}")
                    await asyncio.sleep(0.1)
            
            result_msg = f"Отправлено {sent_lines} строк через Bluetooth, ошибок: {errors}"
            if self.stop_send.is_set():
                result_msg += " (ПРЕРВАНО)"
            self.logger.info(result_msg)
            self.update_gui_status(result_msg, errors == 0)
            return True, result_msg
            
        except Exception as e:
            error_msg = f"Ошибка отправки G-кода через Bluetooth: {str(e)}"
            self.logger.exception(error_msg)
            self.update_gui_status(error_msg, False)
            return False, error_msg
    
    async def _send_line(self, line):
        if not self.is_connected or not self.client or not self.characteristic_uuid:
            return False, "Нет подключения"
        
        if self.stop_send.is_set():
            return False, "Отправка прервана"
        
        try:
            await self.client.write_gatt_char(self.characteristic_uuid, line.encode('utf-8'), response=False)
            self.logger.debug(f"Bluetooth отправлено: {line.strip()}")
            return True, "Данные отправлены"
        except Exception as e:
            error_msg = f"Ошибка Bluetooth отправки: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
    
    async def emergency_stop(self):
        if not self.is_connected:
            error_msg = "Нет Bluetooth подключения для экстренной остановки"
            self.logger.warning(error_msg)
            return False, error_msg
        
        self.stop_send.set()
        
        emergency_commands = [
            "M112\n",
            "!\n",
            "\x18",
            "M5\n",
        ]
        
        success_count = 0
        for cmd in emergency_commands:
            try:
                success, _ = await self._send_line(cmd)
                if success:
                    success_count += 1
                await asyncio.sleep(0.01)
            except:
                pass
        
        status_msg = f"Bluetooth: Экстренная остановка отправлена ({success_count}/{len(emergency_commands)} команд)"
        self.logger.warning(status_msg)
        self.update_gui_status("ЭКСТРЕННАЯ ОСТАНОВКА (Bluetooth) АКТИВИРОВАНА!", False)
        
        if hasattr(self.gui_app, 'emergency_stop_activated'):
            self.gui_app.root.after(0, lambda: setattr(self.gui_app, 'emergency_stop_activated', True))
        
        return success_count > 0, status_msg

class ConnectionManager:
    def __init__(self, gui_app):
        self.gui_app = gui_app
        self.connection_type = "serial"
        self.serial_conn = SerialConnection(gui_app)
        self.bluetooth_conn = BluetoothConnection(gui_app)
        self.is_connected = False
        self.last_received = ""
    
    def get_available_devices(self, connection_type="serial"):
        try:
            if connection_type == "serial":
                devices = self.serial_conn.get_available_ports()
                home_dir = os.path.expanduser('~')
                return devices
            elif connection_type == "bluetooth" and self.bluetooth_conn:
                return asyncio.run(self.bluetooth_conn.get_available_devices())
            return []
        except Exception as e:
            error_msg = f"Ошибка получения доступных устройств: {str(e)}"
            logging.error(error_msg)
            return []
    
    def connect(self, device_id, connection_type="serial"):
        try:
            if self.is_connected:
                self.disconnect()
            
            self.connection_type = connection_type
            
            if connection_type == "serial":
                success, message = self.serial_conn.connect(device_id)
                self.is_connected = success
                return success, message
            elif connection_type == "bluetooth" and self.bluetooth_conn:
                success, message = asyncio.run(self.bluetooth_conn.connect(device_id))
                self.is_connected = success
                return success, message
            
            return False, "Неподдерживаемый тип подключения"
            
        except Exception as e:
            error_msg = f"Ошибка подключения: {str(e)}"
            logging.exception(error_msg)
            return False, error_msg
    
    def disconnect(self):
        try:
            if self.connection_type == "serial":
                return self.serial_conn.disconnect()
            elif self.connection_type == "bluetooth" and self.bluetooth_conn:
                return asyncio.run(self.bluetooth_conn.disconnect())
            
            return False, "Нет активного подключения"
            
        except Exception as e:
            error_msg = f"Ошибка при отключении: {str(e)}"
            logging.exception(error_msg)
            return False, error_msg
    
    def send_gcode(self, gcode_lines):
        if not self.is_connected:
            return False, "Нет подключения к устройству"
        
        try:
            if self.connection_type == "serial":
                return self.serial_conn.send_gcode(gcode_lines)
            elif self.connection_type == "bluetooth" and self.bluetooth_conn:
                return asyncio.run(self.bluetooth_conn.send_gcode(gcode_lines))
            
            return False, "Неподдерживаемый тип подключения"
            
        except Exception as e:
            error_msg = f"Ошибка отправки G-кода: {str(e)}"
            logging.exception(error_msg)
            return False, error_msg
    
    def emergency_stop(self):
        if not self.is_connected:
            return False, "Нет подключения"
        
        try:
            if self.connection_type == "serial":
                if hasattr(self.serial_conn, 'stop_send'):
                    self.serial_conn.stop_send.set()
                
                return self.serial_conn.emergency_stop()
            elif self.connection_type == "bluetooth" and self.bluetooth_conn:
                return asyncio.run(self.bluetooth_conn.emergency_stop())
            
            return False, "Неподдерживаемый тип подключения"
            
        except Exception as e:
            error_msg = f"Ошибка экстренной остановки: {str(e)}"
            logging.exception(error_msg)
            return False, error_msg
    
    def get_received_data(self):
        if self.connection_type == "serial":
            return self.serial_conn.get_received_data()
        return ""
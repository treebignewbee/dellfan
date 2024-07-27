import sys
import subprocess
import re
import os
import configparser
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
                             QCheckBox, QSpinBox, QHeaderView, QAction, QMenu, QFileDialog, QMessageBox, QDialog,
                             QDialogButtonBox)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QIcon

# Configuration file name
CONFIG_FILE = "DellFanController.ini"


# Function to get the absolute path of the script
def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))


# Get ipmitool path, default to script directory if not found
def get_default_ipmitool_path():
    script_path = get_script_path()
    ipmitool_path = os.path.join(script_path, "ipmitool", "ipmitool.exe")
    if os.path.exists(ipmitool_path):
        return ipmitool_path
    else:
        return ""


class SensorDataThread(QThread):
    data_ready = pyqtSignal(list)
    error_occurred = pyqtSignal()  # Signal to indicate error

    def __init__(self, ipmitool_path, ip, user, password):
        super().__init__()
        self.ipmitool_path = ipmitool_path
        self.ip = ip
        self.user = user
        self.password = password

    def run(self):
        while True:
            sensor_data = self.get_sensor_data()
            if sensor_data is not None:  # Check if sensor_data is not None
                if sensor_data:  # Check if sensor_data is not empty
                    self.data_ready.emit(sensor_data)
                else:
                    self.error_occurred.emit()  # Emit error signal
            self.sleep(5)

    def get_sensor_data(self):
        if not self.ip or not self.user or not self.password:
            return None  # Don't attempt to fetch data if credentials are not set

        try:
            format_sensor = "-I lanplus -H {0} -U {1} -P {2} sensor"
            parameters_sensor = format_sensor.format(self.ip, self.user, self.password)
            full_command_sensor = f"{self.ipmitool_path} {parameters_sensor}"
            result = self.execute_cmd(full_command_sensor)

            if result:
                sensor_data = self.parse_sensor_data(result)
                return sensor_data
            else:
                print("Failed to retrieve sensor data.")
                return []  # Return empty list to indicate error
        except Exception as e:
            print(f"Exception occurred: {e}")
            return None

    def parse_sensor_data(self, raw_output):
        sensor_list = []
        lines = raw_output.splitlines()
        for line in lines:
            if re.search(r'Temp|RPM', line):
                sensor_list.append(line.split('|'))
        return sensor_list

    def execute_cmd(self, command):
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Error executing command: {result.stderr}")
            return result.stdout.strip()
        except Exception as e:
            print(f"Exception occurred: {e}")
            return None


class FanControlThread(QThread):
    def __init__(self, ipmitool_path, function, args):
        super().__init__()
        self.ipmitool_path = ipmitool_path
        self.function = function
        self.args = args

    def run(self):
        self.function(*self.args)


class DellFanControllerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ipmitool_path = get_default_ipmitool_path()
        self.ip = ""
        self.user = ""
        self.password = ""
        self.sensor_thread = None
        self.load_settings()  # Load settings from file
        self.loading_label = QLabel("正在加载传感器数据...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.initUI()
        # Attempt to load sensor data on startup (after initUI)
        self.start_sensor_thread()

    def initUI(self):
        self.setWindowTitle('Dell Fan Controller/Dell服务器风扇控制器')
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(QIcon('fan_icon.png'))

        # Menu bar
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('文件')
        settingsAction = QAction('设置iDRAC信息', self)
        settingsAction.triggered.connect(self.open_settings)
        fileMenu.addAction(settingsAction)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)  # 在这里创建 main_layout

        # 添加加载提示标签
        main_layout.addWidget(self.loading_label)

        # Sensor data table
        self.sensor_table = QTableWidget()
        self.sensor_table.setStyleSheet("QTableWidget {border: 1px solid gray;}")
        self.sensor_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sensor_table.verticalHeader().setVisible(False)
        main_layout.addWidget(self.sensor_table)

        # Fan control buttons
        button_layout = QHBoxLayout()
        self.reset_button = QPushButton('重置为默认风扇调速')
        self.reset_button.setToolTip(
            '点击将风扇控制重置为戴尔的默认设置模式。戴尔会基于各项参数自动调节风扇速度，对于家用来说声音较大。')
        self.reset_button.clicked.connect(self.reset_fan_control)
        button_layout.addWidget(self.reset_button)

        self.set_speed_button = QPushButton('手动设置风扇速度')
        self.set_speed_button.setToolTip('点击手动设置风扇速度百分比，如果不填写，默认静音模式10')
        self.set_speed_button.clicked.connect(self.set_fan_speed)
        button_layout.addWidget(self.set_speed_button)

        self.speed_input = QLineEdit()
        self.speed_input.setPlaceholderText('风扇速度%')
        button_layout.addWidget(self.speed_input)

        main_layout.addLayout(button_layout)

        # Auto-adjust configuration
        auto_adjust_layout = QHBoxLayout()
        self.auto_adjust_checkbox = QCheckBox('按温度自动调速')
        self.auto_adjust_checkbox.setToolTip(
            '启用或禁用基于温度的自动风扇速度调节，如果超出阈值温度，则启动风扇降温，如果温度正常，则设置为静音模式。')
        self.auto_adjust_checkbox.stateChanged.connect(self.toggle_auto_adjust)
        auto_adjust_layout.addWidget(self.auto_adjust_checkbox)

        self.temp_threshold_label = QLabel('温度阈值 (°C):')
        auto_adjust_layout.addWidget(self.temp_threshold_label)

        self.temp_threshold_input = QSpinBox()
        self.temp_threshold_input.setRange(0, 100)
        self.temp_threshold_input.setValue(70)
        auto_adjust_layout.addWidget(self.temp_threshold_input)

        main_layout.addLayout(auto_adjust_layout)

        # Set font
        font = QFont("Arial", 10)
        self.setFont(font)

        # Center the window
        self.center()

    def center(self):
        qr = self.frameGeometry()
        cp = QApplication.desktop().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def update_sensor_data(self, sensor_data):
        self.populate_sensor_table(sensor_data)
        self.loading_label.hide()  # 数据加载完成后隐藏加载提示
        if self.auto_adjust_checkbox.isChecked():
            self.auto_adjust_fan_speed(sensor_data)

    def populate_sensor_table(self, sensor_data):
        headers = ['传感器', '读数', '单位', '状态']
        self.sensor_table.setRowCount(len(sensor_data))
        self.sensor_table.setColumnCount(len(headers))
        self.sensor_table.setHorizontalHeaderLabels(headers)

        for row, sensor in enumerate(sensor_data):
            for col, value in enumerate(sensor):
                if col == 0:  # Sensor name
                    value = f"{self.translate_sensor_name(value)}"
                elif col == 2:  # Units
                    value = f"{self.translate_unit(value)}"

                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.sensor_table.setItem(row, col, item)

        self.sensor_table.resizeColumnsToContents()

    def translate_sensor_name(self, sensor_name):
        translations = {
            "Exhaust Temp": "排出空气温度",
            "Inlet Temp": "进入空气温度",
            "Temp": "CPU温度",
            "Fan1 RPM": "风扇1转速",
            "Fan2 RPM": "风扇2转速",
            "Fan3 RPM": "风扇3转速",
            "Fan4 RPM": "风扇4转速",
            "Fan5 RPM": "风扇5转速",
            "Fan6 RPM": "风扇6转速",
        }

        for key, value in translations.items():
            if key in sensor_name:
                return value

        return sensor_name

    def translate_unit(self, unit):
        if "RPM" in unit:
            return "转/分钟"
        elif "degrees C" in unit:
            return "摄氏度°C"
        else:
            return unit

    def reset_fan_control(self):
        self.fan_control_thread = FanControlThread(self.ipmitool_path, self.execute_reset_fan_control,
                                                   (self.ip, self.user, self.password))
        self.fan_control_thread.start()

    def set_fan_speed(self):
        speed = self.speed_input.text() or "10"
        self.fan_control_thread = FanControlThread(self.ipmitool_path, self.execute_set_fan_speed,
                                                   (self.ip, self.user, self.password, speed))
        self.fan_control_thread.start()

    def toggle_auto_adjust(self, state):
        if state:
            self.start_sensor_thread()  # Try to start when auto-adjust is checked
        else:
            if self.sensor_thread:
                self.sensor_thread.quit()
                self.sensor_thread = None

    def auto_adjust_fan_speed(self, sensor_data):
        threshold = self.temp_threshold_input.value()
        max_temp = 0
        for sensor in sensor_data:
            if 'Temp' in sensor[0]:
                try:
                    temp = float(sensor[1])
                    max_temp = max(max_temp, temp)
                except ValueError:
                    pass

        if max_temp > threshold:
            self.fan_control_thread = FanControlThread(self.ipmitool_path, self.execute_reset_fan_control,
                                                       (self.ip, self.user, self.password))
        else:
            self.fan_control_thread = FanControlThread(self.ipmitool_path, self.execute_set_fan_speed,
                                                       (self.ip, self.user, self.password, "10"))
        self.fan_control_thread.start()

    def execute_reset_fan_control(self, ip, user, password):
        parameters_reset = f"-I lanplus -H {ip} -U {user} -P {password} raw 0x30 0x30 0x01 0x01"
        full_command = f"{self.ipmitool_path} {parameters_reset}"
        result = subprocess.run(full_command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Reset fan control succeeded: {result.stdout}")
        else:
            print(f"Reset fan control failed: {result.stderr}")

    def execute_set_fan_speed(self, ip, user, password, percent):
        try:
            percent_num = int(percent)
            parameters_disable_auto_mode = f"-I lanplus -H {ip} -U {user} -P {password} raw 0x30 0x30 0x01 0x00"
            full_command_disable_auto_mode = f"{self.ipmitool_path} {parameters_disable_auto_mode}"
            result_disable_auto_mode = subprocess.run(full_command_disable_auto_mode, shell=True,
                                                     capture_output=True, text=True)

            parameters_set_speed = f"-I lanplus -H {ip} -U {user} -P {password} raw 0x30 0x30 0x02 0xff 0x{percent_num:02x}"
            full_command_set_speed = f"{self.ipmitool_path} {parameters_set_speed}"
            result_set_speed = subprocess.run(full_command_set_speed, shell=True, capture_output=True, text=True)

            if result_disable_auto_mode.returncode == 0 and result_set_speed.returncode == 0:
                print(f"Set fan speed to {percent}% succeeded.")
            else:
                print("Set fan speed failed.")
        except Exception as e:
            print(f"Exception occurred: {e}")

    def start_sensor_thread(self):
        if self.sensor_thread:
            self.sensor_thread.quit()
            self.sensor_thread = None

        self.sensor_thread = SensorDataThread(self.ipmitool_path, self.ip, self.user, self.password)
        self.sensor_thread.data_ready.connect(self.update_sensor_data)
        # Connect the error signal to the warning function
        self.sensor_thread.error_occurred.connect(self.show_settings_warning)
        self.sensor_thread.start()

    def show_settings_warning(self):
        message = "你需要设置你的IDRAC信息后才能继续使用，检查并确认你的设置！"
        QMessageBox.warning(self, "配置账户信息提醒", message)
        self.open_settings()  # Open settings dialog if data retrieval fails

    def open_settings(self):
        # Create a dialog for settings
        dialog = QDialog(self)
        dialog.setWindowTitle("设置Idrac信息后继续")
        dialog.resize(500, 400)  # Set size

        # Create input fields for IP, username, password, and ipmitool path
        ip_label = QLabel("IP地址:")
        ip_input = QLineEdit(self.ip)
        ip_input.setText("192.168.1.1")
        ip_input.setMinimumWidth(200)  # Set minimum width

        user_label = QLabel("用户名:")
        user_input = QLineEdit(self.user)
        user_input.setText("root")
        user_input.setMinimumWidth(200)  # Set minimum width

        password_label = QLabel("密码:")
        password_input = QLineEdit(self.password)
        password_input.setEchoMode(QLineEdit.Password)
        password_input.setMinimumWidth(200)  # Set minimum width

        ipmitool_label = QLabel("ipmitool Path:")
        ipmitool_input = QLineEdit(self.ipmitool_path)
        ipmitool_input.setMinimumWidth(200)  # Set minimum width
        browse_button = QPushButton("浏览")
        browse_button.clicked.connect(lambda: self.browse_for_ipmitool(ipmitool_input))

        # Create layout for the dialog
        layout = QVBoxLayout()
        layout.addWidget(ip_label)
        layout.addWidget(ip_input)
        layout.addWidget(user_label)
        layout.addWidget(user_input)
        layout.addWidget(password_label)
        layout.addWidget(password_input)
        layout.addWidget(ipmitool_label)
        layout.addWidget(ipmitool_input)
        layout.addWidget(browse_button)

        # Add OK and Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(
            lambda: self.save_settings(ip_input.text(), user_input.text(), password_input.text(),
                                       ipmitool_input.text(), dialog))
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        dialog.exec_()

    def browse_for_ipmitool(self, ipmitool_input):
        # Open file dialog to choose ipmitool.exe
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileName(self, "Select ipmitool.exe", "", "Executable Files (*.exe)",
                                                  options=options)
        if file_name:
            ipmitool_input.setText(file_name)

    def save_settings(self, ip, user, password, ipmitool_path, dialog):
        # Update settings and close the dialog
        self.ip = ip
        self.user = user
        self.password = password
        self.ipmitool_path = ipmitool_path
        self._save_settings_to_file()  # Save settings to file, note the underscore in the method name
        self.start_sensor_thread() # This line is crucial, it refreshes the sensor data after settings are saved
        dialog.accept()



    def load_settings(self):
        config = configparser.ConfigParser()
        config_path = os.path.join(get_script_path(), CONFIG_FILE)
        if config.read(config_path):
            try:
                self.ip = config.get("Settings", "IP")
                self.user = config.get("Settings", "Username")
                self.password = config.get("Settings", "Password")
                self.ipmitool_path = config.get("Settings", "ipmitool_path")
            except configparser.NoOptionError:
                print("Error reading options from configuration file.")
                self.show_settings_warning()
        else:
            self.show_settings_warning()

    def _save_settings_to_file(self): # Renamed method to avoid recursive call
        config = configparser.ConfigParser()
        config["Settings"] = {
            "IP": self.ip,
            "Username": self.user,
            "Password": self.password,
            "ipmitool_path": self.ipmitool_path
        }

        config_path = os.path.join(get_script_path(), CONFIG_FILE)
        with open(config_path, 'w') as configfile:
            config.write(configfile)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = DellFanControllerGUI()
    ex.show()
    sys.exit(app.exec_())
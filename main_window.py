import os
import sys
import time
from PySide6.QtWidgets import (
    QMainWindow, QTextEdit, QVBoxLayout, QWidget, QLabel, 
    QProgressBar, QMessageBox, QHBoxLayout, QPushButton, QGroupBox
)
from PySide6.QtCore import Qt, QTimer, QElapsedTimer
from PySide6.QtGui import QFont, QColor, QPalette
from crack_thread import CrackThread
from utils import find_tool

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZIP Cracker2.0.1.2 by阿修")
        self.setAcceptDrops(True)
        self.setMinimumSize(600, 400)
        
        # 添加模式选择
        self.mode = 'cpu'  # 默认 CPU 模式
        self.is_running = False
        self.current_file_path = None  # 添加当前文件路径变量
        
        self.setup_ui()
        
        # 在初始化完成后检查工具
        self.log_area.append("正在检查必要工具...")
        self.tools_available = self.check_tools()
        if not self.tools_available:
            self.start_button.setEnabled(False)
            self.log_area.append("警告: 缺少必要工具，无法开始破解")
            self.status_label.setText("状态: 工具检查失败")
        else:
            self.log_area.append("工具检查完成，可以开始使用")
            self.status_label.setText("状态: 等待文件拖入...")

    def setup_ui(self):
        """设置用户界面"""
        # 创建主窗口布局
        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # 添加模式选择组
        mode_group = QGroupBox("选择破解模式")
        mode_layout = QHBoxLayout()
        
        self.cpu_button = QPushButton("CPU模式")
        self.gpu_button = QPushButton("GPU模式")
        self.cpu_button.setCheckable(True)
        self.gpu_button.setCheckable(True)
        self.cpu_button.setChecked(True)  # 默认选中 CPU 模式
        
        # 设置按钮样式
        style = """
        QPushButton {
            min-width: 100px;
            min-height: 30px;
            font-size: 14px;
        }
        QPushButton:checked {
            background-color: #4CAF50;
            color: white;
        }
        """
        self.cpu_button.setStyleSheet(style)
        self.gpu_button.setStyleSheet(style)
        
        self.cpu_button.clicked.connect(lambda: self.set_mode('cpu'))
        self.gpu_button.clicked.connect(lambda: self.set_mode('gpu'))
        
        mode_layout.addWidget(self.cpu_button)
        mode_layout.addWidget(self.gpu_button)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # 添加开始和停止按钮
        control_layout = QHBoxLayout()
        self.start_button = QPushButton("开始破解")
        self.stop_button = QPushButton("停止破解")
        self.start_button.setStyleSheet("""
            QPushButton {
                min-width: 120px;
                min-height: 35px;
                font-size: 14px;
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_button.setStyleSheet("""
            QPushButton {
                min-width: 120px;
                min-height: 35px;
                font-size: 14px;
                background-color: #f44336;
                color: white;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_cracking)
        self.stop_button.clicked.connect(self.stop_cracking)
        
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        layout.addLayout(control_layout)
        
        # 添加日志区域
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont('Consolas', 10))
        layout.addWidget(self.log_area)
        
        # 添加进度条
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # 添加时间标签
        self.time_label = QLabel("已用时间: 00:00:00")
        layout.addWidget(self.time_label)
        
        # 添加状态标签
        self.status_label = QLabel("状态: 等待文件拖入...")
        layout.addWidget(self.status_label)
        
        # 添加结果标签
        self.result_label = QLabel("结果: 未开始")
        layout.addWidget(self.result_label)
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        self.setup_ui_style()

    def setup_ui_style(self):
        """设置UI样式"""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.Text, Qt.white)
        self.setPalette(palette)
        font = QFont("Microsoft YaHei", 10)
        self.setFont(font)

    def set_mode(self, mode):
        """设置破解模式"""
        self.mode = mode
        self.cpu_button.setChecked(mode == 'cpu')
        self.gpu_button.setChecked(mode == 'gpu')
        self.log_area.append(f"[{time.strftime('%H:%M:%S')}] 已切换至 {mode.upper()} 模式")

    def start_cracking(self):
        """开始破解按钮点击事件"""
        if not self.current_file_path:
            self.log_area.append("错误: 请先拖入需要破解的文件")
            return

        self.is_running = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log_area.append(f"[{time.strftime('%H:%M:%S')}] 开始{self.mode.upper()}模式破解")
        self.status_label.setText("状态: 破解进行中...")
        self.progress_bar.setValue(0)

        # 创建破解线程
        self.crack_thread = CrackThread(self.current_file_path, self.mode)
        self.crack_thread.update_log.connect(self.log_area.append)
        self.crack_thread.update_progress.connect(self.progress_bar.setValue)
        self.crack_thread.crack_result.connect(self.show_result)
        self.crack_thread.start()

    def stop_cracking(self):
        """停止破解按钮点击事件"""
        self.is_running = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.log_area.append(f"[{time.strftime('%H:%M:%S')}] 破解已手动停止")
        self.status_label.setText("状态: 已停止")
        
        if hasattr(self, 'crack_thread') and self.crack_thread.isRunning():
            self.crack_thread.terminate()
            self.crack_thread.wait()

    def show_result(self, result):
        """显示破解结果"""
        self.is_running = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        if result.startswith("破解失败"):
            self.log_area.append(f"[{time.strftime('%H:%M:%S')}] {result}")
            self.status_label.setText("状态: 破解失败")
            self.result_label.setText(f"结果: {result}")
        else:
            self.log_area.append(f"[{time.strftime('%H:%M:%S')}] 破解成功! 密码: {result}")
            self.status_label.setText("状态: 破解成功")
            self.result_label.setText(f"结果: 密码 = {result}")
            
            # 显示成功消息框
            QMessageBox.information(self, "破解成功", f"文件密码: {result}")

    def dragEnterEvent(self, event):
        """处理拖入事件"""
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            supported_formats = [
                '.zip', '.rar', '.7z', 
                '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', 
                '.pdf', 
                '.kdb', '.kdbx',  # KeePass
                '.gpg', '.pgp',   # GPG
                '.vhd', '.vhdx',  # BitLocker
                '.hccap', '.hccapx',  # WiFi
                '.pcap', '.pcapng',   # VNC
                '.pem', '.key', '.ppk'  # SSH
            ]
            
            # 特殊处理shadow文件
            if os.path.basename(file_path).lower() == 'shadow':
                event.acceptProposedAction()
                self.log_area.append(f"[{time.strftime('%H:%M:%S')}] 检测到支持的文件: shadow")
                return
            
            if ext in supported_formats:
                event.acceptProposedAction()
                self.log_area.append(f"[{time.strftime('%H:%M:%S')}] 检测到支持的文件格式: {ext}")
            else:
                self.log_area.append(f"[{time.strftime('%H:%M:%S')}] 不支持的文件格式: {ext}")
                event.ignore()
        else:
            event.ignore()

    def dropEvent(self, event):
        """处理文件拖放"""
        try:
            file_path = event.mimeData().urls()[0].toLocalFile()
            if not os.path.exists(file_path):
                raise FileNotFoundError("文件不存在")
            if not os.path.isfile(file_path):
                raise IsADirectoryError("不能拖放文件夹")
            
            self.current_file_path = file_path
            ext = os.path.splitext(file_path)[1].upper()
            self.log_area.append(f"[{time.strftime('%H:%M:%S')}] 已加载{ext}文件: {file_path}")
            self.status_label.setText(f"状态: 已加载{ext}文件，点击开始按钮开始破解")
            self.result_label.setText("结果: 未开始")
            self.progress_bar.setValue(0)
            
            # 启用开始按钮
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            
            event.accept()
        except Exception as e:
            self.log_area.append(f"错误: {str(e)}")
            event.ignore()

    def check_tools(self):
        """检查必要的工具文件是否存在"""
        required_tools = ['hashcat.exe', 'rar2john.exe', 'zip2john.exe']
        optional_tools = [
            '7z2john.pl',            # 修正: 确保只使用 .pl 扩展名
            'office2john.py', 
            'pdf2john.pl',           # 修正: 确保只使用 .pl 扩展名
            'ssh2john.py', 
            'keepass2john.exe', 
            'gpg2john.exe',
            'bitlocker2john.exe',
            'hccap2john.exe'
            # 移除: vncpcap2john.exe
        ]
        missing_tools = []
        missing_optional_tools = []
        
        for tool in required_tools:
            tool_path = find_tool(tool)
            if not tool_path:
                missing_tools.append(tool)
                self.log_area.append(f"警告: 找不到必要工具 {tool}")
            else:
                self.log_area.append(f"找到工具: {tool} 位置: {tool_path}")
        
        for tool in optional_tools:
            tool_path = find_tool(tool)
            if not tool_path:
                missing_optional_tools.append(tool)
                self.log_area.append(f"提示: 找不到可选工具 {tool}，相关格式文件将无法处理")
            else:
                self.log_area.append(f"找到工具: {tool} 位置: {tool_path}")
        
        if missing_tools:
            self.log_area.append(f"缺少以下必要工具: {', '.join(missing_tools)}")
            return False
        
        if missing_optional_tools:
            self.log_area.append(f"缺少以下可选工具: {', '.join(missing_optional_tools)}")
            self.log_area.append("注意: 缺少的可选工具会导致对应格式的文件无法处理")
        
        return True
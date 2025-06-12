#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ZIP Cracker - 应用程序主类
包含主窗口和核心业务逻辑
"""

import os
import sys
import time
import traceback
import json
import datetime
import subprocess
import webbrowser
import queue
import threading
import urllib.request
import zipfile
import shutil
import tempfile
import glob
import re
import atexit
import logging

from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import pyqtSignal, QMetaType, Qt, QProcess, QIODevice

# 导入自定义模块
from zipcracker_models import TaskManager, TaskType, TaskStatus, HashcatThread, CrackHistory
from zipcracker_models import SUPPORTED_EXTS, HASHCAT_MODE_MAP, JOHN_FORMAT_MAP
from zipcracker_utils import log_error, safe_ui_update, extract_hash_safe, run_cmd_with_output
from zipcracker_utils import get_formatted_time, format_duration, is_supported_file, has_chinese
from zipcracker_utils import init_logging, show_error_dialog, show_info_dialog  # 新增
from zipcracker_config import config
from zipcracker_dialogs import ToolPathsDialog, AboutDialog, HelpDialog, MaskGeneratorDialog, DictManagerDialog, PerformanceSettingsDialog, HistoryDialog
from zipcracker_models import DownloadThread

class MarqueeLabel(QtWidgets.QLabel):
    def __init__(self, text, color="#4CAF50", parent=None):
        super().__init__(text, parent)
        self.full_text = text
        self.pos = 0
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.scroll_text)
        self.timer.start(200)
        self.setMinimumWidth(180)
        self.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.color = color
    def setTextColor(self, color):
        self.color = color
        self.setStyleSheet(f"color: {color}; font-size: 12px;")
    def setText(self, text):
        self.full_text = text
        super().setText(text)
    def scroll_text(self):
        if len(self.full_text) <= 20:
            super().setText(self.full_text)
            return
        self.pos = (self.pos + 1) % len(self.full_text)
        show = self.full_text[self.pos:] + '   ' + self.full_text[:self.pos]
        super().setText(show[:24])

class MainWindow(QtWidgets.QMainWindow):
    """应用程序主窗口类"""
    
    # 添加信号用于线程安全的日志更新
    log_signal = QtCore.pyqtSignal(str, str)
    # 添加哈希更新信号
    hash_update_signal = QtCore.pyqtSignal(str, str)
    
    # 在MainWindow类开头添加UI常量
    BUTTON_HEIGHT = 22
    BUTTON_WIDTH = 50
    PASSWORD_EDIT_HEIGHT = 28
    COPY_BTN_HEIGHT = 26
    
    def __init__(self):
        """初始化主窗口"""
        super().__init__()
        
        # 状态变量
        self.selected_file = ""
        self.hash_value = ""
        self.hash_file = ""
        self.file_ext = ""
        self.is_cracking = False
        self.hashcat_thread = None
        self.moving = False
        self.last_pos = None
        self.start_time = None
        self.current_attack_mode = 0  # 默认为字典攻击
        self.is_paused = False  # 新增：是否处于暂停状态
        self.hashcat_session_name = None  # 新增：当前破解session名
        
        # 创建任务管理器
        self.task_manager = TaskManager()
        
        # 创建历史记录管理器
        self.history_manager = CrackHistory()
        
        # 设置界面
        self.setup_ui()
        
        # 读取配置
        self.john_path = config.get("john_path", "")
        self.hashcat_path = config.get("hashcat_path", "")
        self.opencl_path = config.get("opencl_path", "")
        self.perl_path = config.get("perl_path", "")
        
        # 加载性能设置并应用
        self.load_performance_settings()
        
        # 连接信号
        self.log_signal.connect(self.safe_log_message)
        # 连接哈希更新信号
        self.hash_update_signal.connect(self.update_hash_ui)
        
        # 检测工具路径 - 使用同步检测更直接地更新UI
        self.force_detect_tools()
        
        # 设置计时器
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_crack_time)
        self.timer.start(1000)  # 每秒更新一次
        
        # 状态更新计时器
        self.status_timer = QtCore.QTimer(self)
        self.status_timer.timeout.connect(self.update_active_tasks)
        self.status_timer.start(2000)  # 每2秒更新一次
        
        # 检查当前工作目录是否包含中文
        cwd = os.getcwd()
        if has_chinese(cwd):
            QtWidgets.QMessageBox.warning(self, "路径警告", "当前软件运行目录包含中文字符，建议将程序放在纯英文路径下，否则可能导致部分功能异常！")
    
        # 延迟依赖检测，主窗口显示后再提示
        QtCore.QTimer.singleShot(500, self.check_dependencies)
    
    def check_dependencies(self):
        """检测依赖环境，缺失时日志和弹窗提示"""
        import shutil
        from zipcracker_utils import log_error
        logger = logging.getLogger("zipcracker")
        # 检查 hashcat
        hashcat_exe = self.find_hashcat_executable(self.hashcat_path) if self.hashcat_path else None
        if not hashcat_exe or not os.path.exists(hashcat_exe):
            msg = "未检测到 Hashcat 可执行文件，请在设置中配置路径。"
            show_error_dialog(self, msg, suggestion="请在'设置'中正确配置 Hashcat 路径，并确保文件存在。")
        # 检查 john
        john_exe = self.find_john_executable(self.john_path) if self.john_path else None
        if not john_exe or not os.path.exists(john_exe):
            msg = "未检测到 John the Ripper 可执行文件，请在设置中配置路径。"
            show_error_dialog(self, msg, suggestion="请在'设置'中正确配置 John 路径，并确保文件存在。")
        # 检查 OpenCL（仅在GPU破解时）
        if self.gpuRadio.isChecked():
            opencl_path = self.opencl_path or os.path.join(os.path.dirname(self.hashcat_path), "OpenCL")
            if not os.path.exists(opencl_path):
                msg = "未检测到 OpenCL 运行库，GPU 破解可能无法使用。建议安装 OpenCL 驱动或切换到 CPU 破解。"
                show_error_dialog(self, msg, suggestion="请安装 OpenCL 驱动，或在设置中切换为 CPU 破解。")
        # 检查 Perl（如需 office2john/r2john 脚本）
        perl_needed = False
        for ext in ["doc", "docx", "xls", "xlsx", "ppt", "pptx", "7z", "pdf", "rar", "zip"]:
            if ext in self.file_ext:
                perl_needed = True
                break
        if perl_needed and not shutil.which("perl"):
            msg = "未检测到 Perl 解释器，部分哈希提取脚本（如 office2john.pl、rar2john.pl）需要 Perl 支持。"
            show_error_dialog(self, msg, suggestion="请安装 Strawberry Perl 并确保其已加入系统 PATH 环境变量。")
    
    def load_performance_settings(self):
        """加载性能设置并应用"""
        performance_settings = config.get("performance_settings", {})
        
        # 应用GPU设置
        if "use_gpu" in performance_settings:
            if performance_settings["use_gpu"]:
                self.gpuRadio.setChecked(True)
            else:
                self.cpuRadio.setChecked(True)
            
        # 记录其他设置以便后续使用
        # 这些设置将在start_crack中被使用
        if performance_settings:
            self.log_message("已加载性能设置", "success")
            
            # 记录工作负载设置
            if "workload" in performance_settings:
                workload = performance_settings["workload"]
                workload_names = ["", "低负载", "标准负载", "高负载", "极高负载"]
                if 0 < workload < len(workload_names):
                    self.log_message(f"工作负载配置: {workload_names[workload]}")
            
            # 记录线程数设置
            if "threads" in performance_settings:
                threads = performance_settings["threads"]
                self.log_message(f"线程数配置: {threads}")
            
            # 记录GPU设备设置
            if "gpu_device" in performance_settings and performance_settings["use_gpu"]:
                device = performance_settings["gpu_device"] - 1
                if device >= 0:
                    self.log_message(f"GPU设备配置: {device}")
            
            # 记录内存限制设置
            if "memory_limit" in performance_settings:
                memory_limit = performance_settings["memory_limit"]
                self.log_message(f"内存限制配置: {memory_limit}")
    
    def setup_ui(self):
        """设置用户界面"""
        # 设置窗口属性
        self.setObjectName("MainWindow")
        self.resize(700, 530)
        self.setWindowTitle("ZIP Cracker 4.0.5")
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)  # 无边框窗口
        self.setFixedSize(700, 530)
        
        # 应用全局样式表
        qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zipcracker.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        
        # 中央窗口部件
        self.centralwidget = QtWidgets.QWidget(self)
        self.centralwidget.setObjectName("centralwidget")
        
        # 主布局
        self.mainLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)
        
        # 标题栏
        self.titleBar = QtWidgets.QWidget()
        self.titleBar.setFixedHeight(26)
        
        titleLayout = QtWidgets.QHBoxLayout(self.titleBar)
        titleLayout.setContentsMargins(8, 0, 8, 0)
        
        # 标题文本
        logoLabel = QtWidgets.QLabel()
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
        if os.path.exists(icon_path):
            pixmap = QtGui.QPixmap(icon_path)
            logoLabel.setPixmap(pixmap.scaled(20, 20, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            logoLabel.setFixedSize(22, 22)
        titleLayout.addWidget(logoLabel)
        titleLabel = QtWidgets.QLabel("ZIP Cracker 4.0.5")
        titleLabel.setProperty("class", "title")
        titleLayout.addWidget(titleLabel)
        titleLayout.addStretch()
        
        # 文件按钮
        self.openFileBtn = QtWidgets.QPushButton("文件")
        self.openFileBtn.setFixedWidth(60)
        self.openFileBtn.setProperty("menuButton", True)
        self.openFileBtn.setCheckable(True)
        self.openFileBtn.clicked.connect(self.show_file_menu)
        titleLayout.addWidget(self.openFileBtn)
        
        # 设置按钮
        self.settingsBtn = QtWidgets.QPushButton("设置")
        self.settingsBtn.setFixedWidth(60)
        self.settingsBtn.setProperty("menuButton", True)
        self.settingsBtn.setCheckable(True)
        self.settingsBtn.clicked.connect(self.show_settings_menu)
        titleLayout.addWidget(self.settingsBtn)
        
        # 工具按钮
        self.toolsBtn = QtWidgets.QPushButton("工具")
        self.toolsBtn.setFixedWidth(60)
        self.toolsBtn.setProperty("menuButton", True)
        self.toolsBtn.setCheckable(True)
        self.toolsBtn.clicked.connect(self.show_tools_menu)
        titleLayout.addWidget(self.toolsBtn)
        
        # 帮助按钮
        self.helpBtn = QtWidgets.QPushButton("帮助")
        self.helpBtn.setFixedWidth(60)
        self.helpBtn.setProperty("menuButton", True)
        self.helpBtn.setCheckable(True)
        self.helpBtn.clicked.connect(self.show_help_menu)
        titleLayout.addWidget(self.helpBtn)
        
        # 最小化按钮
        self.minBtn = QtWidgets.QPushButton("—")
        self.minBtn.setFixedWidth(30)
        self.minBtn.clicked.connect(self.showMinimized)
        titleLayout.addWidget(self.minBtn)
        
        # 关闭按钮
        self.closeBtn = QtWidgets.QPushButton("×")
        self.closeBtn.setFixedWidth(30)
        self.closeBtn.clicked.connect(self.close)
        titleLayout.addWidget(self.closeBtn)
        
        self.mainLayout.addWidget(self.titleBar)
        
        # 拖动窗口设置
        self.titleBar.mousePressEvent = self.titleBarMousePressEvent
        self.titleBar.mouseMoveEvent = self.titleBarMouseMoveEvent
        self.titleBar.mouseReleaseEvent = self.titleBarMouseReleaseEvent
        
        # 内容区域
        self.contentWidget = QtWidgets.QWidget()
        self.contentLayout = QtWidgets.QHBoxLayout(self.contentWidget)
        self.contentLayout.setContentsMargins(10, 10, 10, 10)
        self.contentLayout.setSpacing(5)
        
        # 左侧区域 - 所有操作控制
        self.leftPanel = QtWidgets.QVBoxLayout()
        # 关键：设置间距为0，手动控制
        self.leftPanel.setSpacing(0)
        self.leftPanel.setContentsMargins(0, 0, 0, 0)
        
        # 创建一个包装左侧面板的小部件，并设置固定宽度
        self.leftPanelWidget = QtWidgets.QWidget()
        self.leftPanelWidget.setLayout(self.leftPanel)
        self.leftPanelWidget.setFixedWidth(320)  # 设置固定宽度为320像素
        
        # 哈希提取卡片
        self.hashCard = QtWidgets.QFrame()
        self.hashCard.setProperty("class", "card")
        self.hashCard.setMinimumHeight(150)  # 增加高度，确保有足够空间
        
        # 使用简单的垂直布局
        hashCardLayout = QtWidgets.QVBoxLayout(self.hashCard)
        hashCardLayout.setContentsMargins(8, 8, 8, 8)
        hashCardLayout.setSpacing(5)  # 标题与哈希值显示框间距为5px
        
        # 标题
        hashCardTitle = QtWidgets.QLabel("哈希提取")
        hashCardTitle.setProperty("class", "sectionTitle")
        hashCardLayout.addWidget(hashCardTitle)
        
        # 哈希值输入框 - 直接使用QTextEdit
        self.hashValueEdit = QtWidgets.QTextEdit()
        self.hashValueEdit.setPlaceholderText("哈希值在此显示...")
        self.hashValueEdit.setFixedHeight(83)
        self.hashValueEdit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.hashValueEdit.setWordWrapMode(QtGui.QTextOption.WrapAnywhere)
        self.hashValueEdit.textChanged.connect(self.on_hash_text_changed)
        hashCardLayout.addWidget(self.hashValueEdit)
        
        # 按钮水平布局
        buttonLayout = QtWidgets.QHBoxLayout()
        buttonLayout.setSpacing(6)
        
        # 原"提取哈希"按钮改为"打开文件"
        self.extractHashBtn = QtWidgets.QPushButton("打开文件")
        self.extractHashBtn.setFixedHeight(25)
        self.extractHashBtn.setEnabled(True)
        self.extractHashBtn.clicked.connect(self.choose_file)
        buttonLayout.addWidget(self.extractHashBtn)
        
        # 原"复制哈希"按钮改为"提取哈希"
        self.copyHashBtn = QtWidgets.QPushButton("提取哈希")
        self.copyHashBtn.setFixedHeight(25)
        self.copyHashBtn.setEnabled(False)
        self.copyHashBtn.clicked.connect(self.extract_hash_async)
        buttonLayout.addWidget(self.copyHashBtn)
        
        # 添加按钮布局
        hashCardLayout.addLayout(buttonLayout)
        
        # 添加哈希卡片
        self.leftPanel.addWidget(self.hashCard)
        
        # 添加卡片间的间距
        spacer1 = QtWidgets.QSpacerItem(20, 5, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        self.leftPanel.addItem(spacer1)
        
        # 攻击模式卡片
        self.attackCard = QtWidgets.QFrame()
        self.attackCard.setProperty("class", "card")
        self.attackCard.setMinimumHeight(130)  # 从125px增加到130px
        
        attackCardLayout = QtWidgets.QVBoxLayout(self.attackCard)
        attackCardLayout.setContentsMargins(8, 8, 8, 8)
        
        # 攻击模式标题
        attackCardTitle = QtWidgets.QLabel("攻击模式")
        attackCardTitle.setProperty("class", "sectionTitle")
        attackCardLayout.addWidget(attackCardTitle)
        
        # 攻击模式选择 - 使用FormLayout替代HBoxLayout
        attackModeFormLayout = QtWidgets.QFormLayout()
        attackModeFormLayout.setContentsMargins(0, 1, 0, 0)  # 将下边距从3px减少到0px，进一步减少与下方元素的间距
        attackModeFormLayout.setSpacing(3)  # 与其他FormLayout保持一致的间距
        
        self.attackModeCombo = QtWidgets.QComboBox()
        self.attackModeCombo.addItem("字典攻击")
        self.attackModeCombo.addItem("组合攻击")
        self.attackModeCombo.addItem("掩码攻击")
        self.attackModeCombo.addItem("混合攻击")
        self.attackModeCombo.addItem("暴力攻击")  # 新增暴力攻击模式
        self.attackModeCombo.setFixedHeight(self.BUTTON_HEIGHT)
        
        self.attackModeCombo.currentIndexChanged.connect(self.on_attack_mode_changed)
        
        attackModeFormLayout.addRow("模式:", self.attackModeCombo)
        attackCardLayout.addLayout(attackModeFormLayout)
        
        # 使用堆叠小部件来显示不同的攻击模式设置
        self.attackModeStack = QtWidgets.QStackedWidget()
        
        # 添加一个负上边距，使所有内容向上移动
        attackStackLayout = QtWidgets.QVBoxLayout()
        attackStackLayout.setContentsMargins(0, -13, 0, 0)  # 负上边距从-8px增加到-13px，使内容再向上移动5px
        attackStackLayout.addWidget(self.attackModeStack)
        attackCardLayout.addLayout(attackStackLayout)
        
        # 先定义所有攻击模式相关Widget
        # 掩码攻击模式
        maskWidget = QtWidgets.QWidget()
        maskLayout = QtWidgets.QFormLayout(maskWidget)
        maskLayout.setContentsMargins(0, 0, 0, 0)
        maskLayout.setSpacing(2)  # 从3减小到2
        # 掩码输入框和生成按钮
        maskPathLayout = QtWidgets.QHBoxLayout()
        maskPathLayout.setContentsMargins(0, 0, 0, 0)
        maskPathLayout.setSpacing(6)
        self.maskEdit = QtWidgets.QLineEdit()
        self.maskEdit.setPlaceholderText("例如: ?l?l?l?l?d?d")
        self.maskGenBtn = QtWidgets.QPushButton("生成")
        self.maskGenBtn.setFixedWidth(self.BUTTON_WIDTH)
        self.maskGenBtn.setFixedHeight(self.BUTTON_HEIGHT)
        self.maskGenBtn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        maskPathLayout.addWidget(self.maskEdit)
        maskPathLayout.addWidget(self.maskGenBtn)
        self.maskGenBtn.clicked.connect(self.show_mask_gen)
        maskLayout.addRow("掩码:", maskPathLayout)
        self.hashModeEdit = QtWidgets.QLineEdit()
        self.hashModeEdit.setPlaceholderText("如 17220")
        self.hashModeEdit.setFixedWidth(80)
        self.hashModeEdit.setStyleSheet('margin:0;padding:0;')
        maskLayout.addRow("编号：", self.hashModeEdit)
        self.workloadCombo = QtWidgets.QComboBox()
        self.workloadCombo.clear()
        self.workloadCombo.addItems(["最轻", "默认", "高", "极限"])
        self.workloadCombo.setFixedWidth(80)
        self.workloadCombo.setStyleSheet('margin:0;padding:0;')
        maskLayout.addRow("负载：", self.workloadCombo)
        # 字典+规则攻击模式
        ruleWidget = QtWidgets.QWidget()
        ruleLayout = QtWidgets.QFormLayout(ruleWidget)
        ruleLayout.setContentsMargins(0, 0, 0, 0)
        ruleLayout.setSpacing(2)
        self.dictRulePathEdit = QtWidgets.QLineEdit()
        self.dictRulePathEdit.setPlaceholderText("选择字典文件...")
        self.dictRulePathLayout = QtWidgets.QHBoxLayout()
        self.dictRulePathLayout.setContentsMargins(0, 0, 0, 0)
        self.dictRulePathLayout.setSpacing(6)
        self.dictRulePathLayout.addWidget(self.dictRulePathEdit)
        self.browseDictRuleBtn = QtWidgets.QPushButton("浏览")
        self.browseDictRuleBtn.setFixedWidth(self.BUTTON_WIDTH)
        self.browseDictRuleBtn.setFixedHeight(self.BUTTON_HEIGHT)
        self.dictRulePathLayout.addWidget(self.browseDictRuleBtn, alignment=Qt.AlignVCenter)
        self.browseDictRuleBtn.clicked.connect(self.show_dict_manager)
        ruleLayout.addRow("词典:", self.dictRulePathLayout)
        self.rulePathEdit = QtWidgets.QLineEdit()
        self.rulePathEdit.setPlaceholderText("选择规则文件...")
        self.rulePathLayout = QtWidgets.QHBoxLayout()
        self.rulePathLayout.setContentsMargins(0, 0, 0, 0)
        self.rulePathLayout.setSpacing(6)
        self.rulePathLayout.addWidget(self.rulePathEdit)
        self.browseRuleBtn = QtWidgets.QPushButton("浏览")
        self.browseRuleBtn.setFixedWidth(self.BUTTON_WIDTH)
        self.browseRuleBtn.setFixedHeight(self.BUTTON_HEIGHT)
        self.rulePathLayout.addWidget(self.browseRuleBtn, alignment=Qt.AlignVCenter)
        self.browseRuleBtn.clicked.connect(self.browse_rule_file)
        ruleLayout.addRow("规则:", self.rulePathLayout)
        # 字典攻击模式
        dictionaryWidget = QtWidgets.QWidget()
        dictionaryLayout = QtWidgets.QFormLayout(dictionaryWidget)
        dictionaryLayout.setContentsMargins(0, 0, 0, 0)
        dictionaryLayout.setSpacing(2)
        self.dictPathEdit = QtWidgets.QLineEdit()
        self.dictPathEdit.setPlaceholderText("选择字典文件...")
        self.dictPathLayout = QtWidgets.QHBoxLayout()
        self.dictPathLayout.setContentsMargins(0, 0, 0, 0)
        self.dictPathLayout.setSpacing(6)
        self.dictPathLayout.addWidget(self.dictPathEdit)
        self.browseDictBtn = QtWidgets.QPushButton("浏览")
        self.browseDictBtn.setFixedWidth(self.BUTTON_WIDTH)
        self.dictPathLayout.addWidget(self.browseDictBtn, alignment=Qt.AlignVCenter)
        self.browseDictBtn.clicked.connect(self.show_dict_manager)
        dictionaryLayout.addRow("词典:", self.dictPathLayout)
        # 组合攻击模式
        combiWidget = QtWidgets.QWidget()
        combiLayout = QtWidgets.QFormLayout(combiWidget)
        combiLayout.setContentsMargins(0, 0, 0, 0)
        combiLayout.setSpacing(2)
        self.dict1PathEdit = QtWidgets.QLineEdit()
        self.dict1PathEdit.setPlaceholderText("选择第一个字典文件...")
        self.dict1PathLayout = QtWidgets.QHBoxLayout()
        self.dict1PathLayout.setContentsMargins(0, 0, 0, 0)
        self.dict1PathLayout.setSpacing(6)
        self.dict1PathLayout.addWidget(self.dict1PathEdit)
        self.browseDict1Btn = QtWidgets.QPushButton("浏览")
        self.browseDict1Btn.setFixedWidth(self.BUTTON_WIDTH)
        self.dict1PathLayout.addWidget(self.browseDict1Btn, alignment=Qt.AlignVCenter)
        self.browseDict1Btn.clicked.connect(self.browse_dict1_file)
        combiLayout.addRow("词典1:", self.dict1PathLayout)
        self.dict2PathEdit = QtWidgets.QLineEdit()
        self.dict2PathEdit.setPlaceholderText("选择第二个字典文件...")
        self.dict2PathLayout = QtWidgets.QHBoxLayout()
        self.dict2PathLayout.setContentsMargins(0, 0, 0, 0)
        self.dict2PathLayout.setSpacing(6)
        self.dict2PathLayout.addWidget(self.dict2PathEdit)
        self.browseDict2Btn = QtWidgets.QPushButton("浏览")
        self.browseDict2Btn.setFixedWidth(self.BUTTON_WIDTH)
        self.dict2PathLayout.addWidget(self.browseDict2Btn, alignment=Qt.AlignVCenter)
        self.browseDict2Btn.clicked.connect(self.browse_dict2_file)
        combiLayout.addRow("词典2:", self.dict2PathLayout)
        # 混合攻击模式
        height_style = f"font-size: 12px; padding: 0; border: 1px solid #3F3F46; border-radius: 2px; min-height: {self.BUTTON_HEIGHT}px; max-height: {self.BUTTON_HEIGHT}px; height: {self.BUTTON_HEIGHT}px;"
        hybridWidget = QtWidgets.QWidget()
        hybridLayout = QtWidgets.QFormLayout(hybridWidget)
        hybridLayout.setContentsMargins(0, 0, 0, 0)
        hybridLayout.setSpacing(2)
        self.dictHybridPathEdit = QtWidgets.QLineEdit()
        self.dictHybridPathEdit.setPlaceholderText("选择字典文件...")
        self.dictHybridPathEdit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.dictHybridPathEdit.setFixedHeight(self.BUTTON_HEIGHT)
        self.browseDictHybridBtn = QtWidgets.QPushButton("浏览")
        self.browseDictHybridBtn.setFixedWidth(self.BUTTON_WIDTH)
        self.browseDictHybridBtn.setFixedHeight(self.BUTTON_HEIGHT)
        self.browseDictHybridBtn.clicked.connect(self.browse_dict_hybrid_file)
        self.dictHybridPathEdit.setStyleSheet(height_style)
        self.maskHybridEdit = QtWidgets.QLineEdit()
        self.maskHybridEdit.setFixedHeight(self.BUTTON_HEIGHT)
        self.maskHybridGenBtn = QtWidgets.QPushButton("生成")
        self.maskHybridGenBtn.setFixedWidth(self.BUTTON_WIDTH)
        self.maskHybridGenBtn.setFixedHeight(self.BUTTON_HEIGHT)
        self.maskHybridGenBtn.clicked.connect(self.show_mask_gen)
        self.maskHybridEdit.setStyleSheet(height_style)
        self.dictHybridPathLayout = QtWidgets.QHBoxLayout()
        self.dictHybridPathLayout.setContentsMargins(0, 0, 0, 0)
        self.dictHybridPathLayout.setSpacing(6)
        self.dictHybridPathLayout.addWidget(self.dictHybridPathEdit)
        self.browseDictHybridBtn.setFixedWidth(self.BUTTON_WIDTH)
        self.dictHybridPathLayout.addWidget(self.browseDictHybridBtn, alignment=Qt.AlignVCenter)
        hybridLayout.addRow("词典:", self.dictHybridPathLayout)
        self.maskHybridPosCombo = QtWidgets.QComboBox()
        self.maskHybridPosCombo.addItem("后缀")
        self.maskHybridPosCombo.addItem("前缀")
        class CustomComboStyle(QtWidgets.QProxyStyle):
            def sizeFromContents(self, type, option, size, widget):
                size = super().sizeFromContents(type, option, size, widget)
                if type == QtWidgets.QStyle.CT_ComboBox:
                    size.setHeight(20)
                return size
        self.maskHybridPosCombo.setStyle(CustomComboStyle())
        self.maskHybridPosCombo.setMinimumHeight(self.BUTTON_HEIGHT)
        self.maskHybridPosCombo.setMaximumHeight(self.BUTTON_HEIGHT)
        self.maskHybridPosCombo.setFixedHeight(self.BUTTON_HEIGHT)
        self.maskHybridPosCombo.setStyleSheet("""
            QComboBox {
                min-height: 20px;
                max-height: 20px;
                height: 20px;
                padding: 0px;
                padding-left: 3px;
                margin: 0px;
                border: 1px solid #333333;
                font-size: 12px;
                line-height: 20px;
            }
            QComboBox::drop-down {
                width: 20px;
                height: 20px;
                border: none;
            }
            QComboBox QAbstractItemView {
                min-height: 20px;
                selection-background-color: #0078D7;
            }
        """)
        self.maskHybridEdit.setPlaceholderText("例如: ?l?l?l?l?d?d")
        maskHybridLayout = QtWidgets.QHBoxLayout()
        maskHybridLayout.setContentsMargins(0, 0, 0, 0)
        maskHybridLayout.setSpacing(6)
        maskHybridLayout.addWidget(self.maskHybridEdit)
        maskHybridLayout.addWidget(self.maskHybridGenBtn, alignment=Qt.AlignVCenter)
        hybridLayout.addRow("掩码:", maskHybridLayout)
        hybridLayout.addRow("位置:", self.maskHybridPosCombo)
        # 暴力攻击模式
        bruteForceWidget = QtWidgets.QWidget()
        bruteLayout = QtWidgets.QFormLayout(bruteForceWidget)
        bruteLayout.setContentsMargins(0, 0, 0, 0)
        bruteLayout.setSpacing(2)
        self.bruteMinLen = QtWidgets.QSpinBox()
        self.bruteMinLen.setRange(1, 32)
        self.bruteMinLen.setValue(4)
        self.bruteMaxLen = QtWidgets.QSpinBox()
        self.bruteMaxLen.setRange(1, 32)
        self.bruteMaxLen.setValue(6)
        bruteLenLayout = QtWidgets.QHBoxLayout()
        bruteLenLayout.addWidget(QtWidgets.QLabel("最小长度:"))
        bruteLenLayout.addWidget(self.bruteMinLen)
        bruteLenLayout.addWidget(QtWidgets.QLabel("最大长度:"))
        bruteLenLayout.addWidget(self.bruteMaxLen)
        bruteLayout.addRow("密码长度:", bruteLenLayout)
        self.bruteCharsetCombo = QtWidgets.QComboBox()
        self.bruteCharsetCombo.addItems(["全字符集 (数字+大小写+符号)", "数字 (0-9)", "小写字母 (a-z)", "大写字母 (A-Z)", "数字+小写", "数字+大写", "自定义"])
        bruteLayout.addRow("字符集:", self.bruteCharsetCombo)
        self.bruteCustomCharset = QtWidgets.QLineEdit()
        self.bruteCustomCharset.setPlaceholderText("自定义字符集，如 abc123!@#")
        bruteLayout.addRow("自定义:", self.bruteCustomCharset)
        self.bruteCustomCharset.setEnabled(False)
        def on_charset_changed(idx):
            self.bruteCustomCharset.setEnabled(idx == 6)
        self.bruteCharsetCombo.currentIndexChanged.connect(on_charset_changed)
        # 统一添加到attackModeStack
        self.attackModeStack.addWidget(maskWidget)         # 0 掩码攻击
        self.attackModeStack.addWidget(ruleWidget)         # 1 字典+规则
        self.attackModeStack.addWidget(dictionaryWidget)   # 2 字典攻击
        self.attackModeStack.addWidget(combiWidget)        # 3 组合攻击
        self.attackModeStack.addWidget(hybridWidget)       # 4 混合攻击
        self.attackModeStack.addWidget(bruteForceWidget)   # 5 暴力攻击
        
        # 添加攻击模式卡片
        self.leftPanel.addWidget(self.attackCard)
        
        # 添加固定大小的间距 - 5px
        spacer2 = QtWidgets.QSpacerItem(20, 5, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        self.leftPanel.addItem(spacer2)
        
        # 破解操作卡片
        self.crackCard = QtWidgets.QFrame()
        self.crackCard.setProperty("class", "card")
        self.crackCard.setMinimumHeight(168)  # 从173px降低到168px
        
        crackCardLayout = QtWidgets.QVBoxLayout(self.crackCard)
        crackCardLayout.setContentsMargins(8, 8, 8, 11)
        crackCardLayout.setSpacing(6)
        
        # 破解设置标题
        crackCardTitle = QtWidgets.QLabel("破解操作")
        crackCardTitle.setProperty("class", "sectionTitle")
        crackCardLayout.addWidget(crackCardTitle)
        
        # GPU设置
        gpuLayout = QtWidgets.QHBoxLayout()
        gpuLayout.setContentsMargins(0, 6, 0, 6)
        
        # 创建单选按钮组，并使用方形样式
        self.engineGroup = QtWidgets.QButtonGroup(self)
        engineLabel = QtWidgets.QLabel("破解引擎:")
        gpuLayout.addWidget(engineLabel)
        
        # 使用方形复选框样式
        checkbox_style = """
        QRadioButton {
            color: #CCCCCC;
            spacing: 5px;
        }
        QRadioButton::indicator {
            width: 14px;
            height: 14px;
            border: 1px solid #777777;
            border-radius: 2px;
            background-color: #1E1E1E;
        }
        QRadioButton::indicator:checked {
            background-color: #4C9EDE;
            border: 1px solid #777777;
        }
        QRadioButton::indicator:checked:hover {
            background-color: #5CADF2;
        }
        QRadioButton::indicator:unchecked:hover {
            background-color: #252525;
            border: 1px solid #999999;
        }
        """
        
        # CPU 单选按钮
        self.cpuRadio = QtWidgets.QRadioButton("CPU")
        self.cpuRadio.setStyleSheet(checkbox_style)
        self.engineGroup.addButton(self.cpuRadio, 0)
        gpuLayout.addWidget(self.cpuRadio)
        
        # GPU 单选按钮
        self.gpuRadio = QtWidgets.QRadioButton("GPU")
        self.gpuRadio.setStyleSheet(checkbox_style)
        self.engineGroup.addButton(self.gpuRadio, 1)
        gpuLayout.addWidget(self.gpuRadio)
        
        # 新增：修复引擎按钮
        self.fixEngineBtn = QtWidgets.QPushButton("修复引擎")
        gpuLayout.addWidget(self.fixEngineBtn)
        self.fixEngineBtn.clicked.connect(self.on_fix_engine)
        
        # 默认选择GPU
        self.gpuRadio.setChecked(True)
        
        gpuLayout.addStretch()
        
        crackCardLayout.addLayout(gpuLayout)
        
        # 密码显示
        passwordLayout = QtWidgets.QHBoxLayout()
        passwordLayout.setContentsMargins(0, 0, 0, 0)
        passwordLayout.setSpacing(6)  # 设置合适的间距
        
        passwordLabel = QtWidgets.QLabel("密码:")
        passwordLayout.addWidget(passwordLabel)
        
        self.passwordEdit = QtWidgets.QLineEdit()
        self.passwordEdit.setReadOnly(True)
        self.passwordEdit.setPlaceholderText("未找到")
        self.passwordEdit.setFixedHeight(self.PASSWORD_EDIT_HEIGHT)
        self.copyPasswordBtn = QtWidgets.QPushButton("复制")
        self.copyPasswordBtn.setFixedHeight(self.COPY_BTN_HEIGHT)
        self.copyPasswordBtn.setFixedWidth(self.BUTTON_WIDTH)
        self.copyPasswordBtn.clicked.connect(self.copy_password)  # 添加点击回调
        passwordLayout.addWidget(self.passwordEdit)
        passwordLayout.addWidget(self.copyPasswordBtn, alignment=Qt.AlignVCenter)
        
        crackCardLayout.addLayout(passwordLayout)
        
        # 破解状态和时间
        self.crackTimeLabel = QtWidgets.QLabel("破解时间: 00:00:00")
        crackCardLayout.addWidget(self.crackTimeLabel)
        
        # 操作按钮 - 两个按钮：开始/停止 和 暂停/继续
        btnLayout = QtWidgets.QHBoxLayout()
        btnLayout.setContentsMargins(0, 3, 0, 0)
        btnLayout.setSpacing(4)
        self.startCrackBtn = QtWidgets.QPushButton("开始破解")
        self.startCrackBtn.setProperty("class", "darkButton")
        self.startCrackBtn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.startCrackBtn.setMinimumHeight(20)
        self.startCrackBtn.setMaximumHeight(20)
        self.startCrackBtn.setFixedHeight(20)
        self.startCrackBtn.setEnabled(False)
        self.startCrackBtn.clicked.connect(self.on_start_stop_clicked)
        btnLayout.addWidget(self.startCrackBtn)
        self.pauseResumeBtn = QtWidgets.QPushButton("暂停破解")
        self.pauseResumeBtn.setProperty("class", "darkButton")
        self.pauseResumeBtn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.pauseResumeBtn.setMinimumHeight(20)
        self.pauseResumeBtn.setMaximumHeight(20)
        self.pauseResumeBtn.setFixedHeight(20)
        self.pauseResumeBtn.setEnabled(False)
        self.pauseResumeBtn.clicked.connect(self.on_pause_resume_clicked)
        btnLayout.addWidget(self.pauseResumeBtn)
        crackCardLayout.addLayout(btnLayout)
        
        # 添加破解操作卡片
        self.leftPanel.addWidget(self.crackCard)
        
        # 右侧区域 - 日志输出
        self.rightPanel = QtWidgets.QVBoxLayout()
        self.rightPanel.setSpacing(5)  # 调整为与左侧面板一致的间距
        
        # 日志输出卡片
        self.logCard = QtWidgets.QFrame()
        self.logCard.setProperty("class", "card")
        # 设置日志卡片的固定高度为445像素
        self.logCard.setFixedHeight(445)
        
        logCardLayout = QtWidgets.QVBoxLayout(self.logCard)
        logCardLayout.setContentsMargins(8, 8, 8, 8)
        
        # 日志标题
        logTitleLayout = QtWidgets.QHBoxLayout()
        
        logTitle = QtWidgets.QLabel("日志输出")
        logTitle.setProperty("class", "sectionTitle")
        logTitleLayout.addWidget(logTitle)
        
        logTitleLayout.addStretch()
        
        self.clearLogBtn = QtWidgets.QPushButton("清空")
        self.clearLogBtn.clicked.connect(self.clear_log)
        logTitleLayout.addWidget(self.clearLogBtn)
        
        self.exportLogBtn = QtWidgets.QPushButton("导出")
        self.exportLogBtn.clicked.connect(self.export_log)
        logTitleLayout.addWidget(self.exportLogBtn)
        
        logCardLayout.addLayout(logTitleLayout)
        
        # 日志文本框
        self.logText = QtWidgets.QTextEdit()
        self.logText.setReadOnly(True)
        self.logText.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        logCardLayout.addWidget(self.logText)
        
        # 设置文本拖放事件
        self.logText.setAcceptDrops(True)
        self.logText.dragEnterEvent = self.logTextDragEnterEvent
        self.logText.dropEvent = self.logTextDropEvent
        
        # 添加日志卡片
        self.rightPanel.addWidget(self.logCard)
        
        # 添加状态栏卡片
        self.statusCard = QtWidgets.QFrame()
        self.statusCard.setProperty("class", "card")
        statusCardLayout = QtWidgets.QHBoxLayout(self.statusCard)
        statusCardLayout.setContentsMargins(8, 2, 8, 2)
        class ClickableLabel(QtWidgets.QLabel):
            clicked = QtCore.pyqtSignal()
            def mousePressEvent(self, event):
                if event.button() == QtCore.Qt.LeftButton:
                    self.clicked.emit()
                super().mousePressEvent(event)
        self.statusLabel = ClickableLabel("就绪")
        self.statusLabel.clicked.connect(self.on_status_label_clicked)
        statusCardLayout.addWidget(self.statusLabel)
        statusCardLayout.addStretch()
        gpu_info = self.get_gpu_info()
        self.gpuLabel = QtWidgets.QLabel(f"显卡: {gpu_info}")
        self.gpuLabel.setCursor(Qt.PointingHandCursor)
        self.gpuLabel.mousePressEvent = self.on_gpu_label_clicked
        statusCardLayout.addWidget(self.gpuLabel)
        self.rightPanel.addWidget(self.statusCard)
        
        # 添加左右面板到内容布局
        self.contentLayout.addWidget(self.leftPanelWidget)  # 使用包装小部件而不是直接添加布局
        self.contentLayout.addLayout(self.rightPanel)
        
        self.mainLayout.addWidget(self.contentWidget)
        
        # 设置中央窗口部件
        self.setCentralWidget(self.centralwidget)
        
        # 设置焦点
        self.openFileBtn.setFocus()
        
        # 初始状态下设置默认的攻击模式为字典攻击
        self.attackModeCombo.setCurrentIndex(0)
        self.on_attack_mode_changed(0)
        
        # 使用QTimer在UI完全加载后强制应用哈希值输入框的高度
        QtCore.QTimer.singleShot(100, lambda: self.hashValueEdit.setFixedHeight(83))
    
    def detect_tools_async(self):
        """异步检测工具路径"""
        QtWidgets.QApplication.processEvents()
        def detect_tools():
            try:
                # 检测John the Ripper
                john_installed = False
                if self.john_path:
                    try:
                        john_exe = self.find_john_executable(self.john_path)
                        if john_exe and os.path.exists(john_exe):
                            result = run_cmd_with_output([john_exe], timeout=2)
                            if "John the Ripper" in result:
                                safe_ui_update(lambda: setattr(self.johnStatusLabel, "text", "John: 已安装"))
                                safe_ui_update(lambda: setattr(self.johnStatusLabel, "styleSheet", "color: #4CAF50;"))
                                john_installed = True
                    except Exception as e:
                        log_error(e)
                # 如果John未安装，尝试查找默认路径
                if not john_installed:
                    default_paths = ["john", "john.exe", "./john", "/usr/bin/john", "/usr/local/bin/john"]
                    for path in default_paths:
                        try:
                            result = run_cmd_with_output([path], timeout=2)
                            if "John the Ripper" in result:
                                self.john_path = path
                                config.set("john_path", path)
                                # 更新UI
                                safe_ui_update(lambda: setattr(self.johnStatusLabel, "text", "John: 已安装"))
                                safe_ui_update(lambda: setattr(self.johnStatusLabel, "styleSheet", "color: #4CAF50;"))
                                john_installed = True
                                break
                        except Exception:
                            continue
                
                # 如果仍未找到John
                if not john_installed:
                    # 未找到John
                    safe_ui_update(lambda: setattr(self.johnStatusLabel, "text", "John: 未安装"))
                    safe_ui_update(lambda: setattr(self.johnStatusLabel, "styleSheet", "color: #F44336;"))
                
                # 检测Hashcat
                hashcat_installed = False
                if self.hashcat_path:
                    try:
                        # 获取Hashcat可执行文件路径
                        hashcat_exe = self.find_hashcat_executable(self.hashcat_path)
                        
                        if hashcat_exe and os.path.exists(hashcat_exe):
                            # 尝试运行hashcat --version命令
                            result = run_cmd_with_output([hashcat_exe, "--version"], timeout=2)
                            # 判断条件更精确，检查输出是否包含版本号格式(vX.X.X)
                            if result and ('v' in result.lower() or 'version' in result.lower()):
                                # 更新UI
                                safe_ui_update(lambda: setattr(self.hashcatStatusLabel, "text", "Hashcat: 已安装"))
                                safe_ui_update(lambda: setattr(self.hashcatStatusLabel, "styleSheet", "color: #4CAF50;"))
                                hashcat_installed = True
                    except Exception as e:
                        log_error(e)
                
                # 如果Hashcat未安装，尝试查找默认路径
                if not hashcat_installed:
                    default_paths = ["hashcat", "hashcat.exe", "./hashcat", "/usr/bin/hashcat", "/usr/local/bin/hashcat"]
                    for path in default_paths:
                        try:
                            result = run_cmd_with_output([path, "--version"], timeout=2)
                            # 判断条件更精确，检查输出是否包含版本号格式(vX.X.X)
                            if result and ('v' in result.lower() or 'version' in result.lower()):
                                self.hashcat_path = path
                                config.set("hashcat_path", path)
                                # 更新UI
                                safe_ui_update(lambda: setattr(self.hashcatStatusLabel, "text", "Hashcat: 已安装"))
                                safe_ui_update(lambda: setattr(self.hashcatStatusLabel, "styleSheet", "color: #4CAF50;"))
                                hashcat_installed = True
                                break
                        except Exception:
                            continue
                
                # 如果仍未找到Hashcat
                if not hashcat_installed:
                    # 未找到Hashcat
                    safe_ui_update(lambda: setattr(self.hashcatStatusLabel, "text", "Hashcat: 未安装"))
                    safe_ui_update(lambda: setattr(self.hashcatStatusLabel, "styleSheet", "color: #F44336;"))
                
                # 更新状态
                safe_ui_update(lambda: self.set_status("检测", "success"))
                
            except Exception as e:
                # 确保设置默认状态
                safe_ui_update(lambda: setattr(self.johnStatusLabel, "text", "John: 检测错误"))
                safe_ui_update(lambda: setattr(self.johnStatusLabel, "styleSheet", "color: #F44336;"))
                safe_ui_update(lambda: setattr(self.hashcatStatusLabel, "text", "Hashcat: 检测错误"))
                safe_ui_update(lambda: setattr(self.hashcatStatusLabel, "styleSheet", "color: #F44336;"))
                safe_ui_update(lambda: self.set_status("工具检测出错", "error"))
                log_error(e)
            finally:
                # 自动修复：检测完成后强制刷新底部状态栏标签
                safe_ui_update(self.refresh_tool_status_labels)
        threading.Thread(target=detect_tools, daemon=True).start()

    def refresh_tool_status_labels(self):
        """根据当前状态刷新底部John/Hashcat状态栏标签，确保及时更新"""
        if hasattr(self, 'johnStatusLabel'):
            if self.johnStatusLabel.text() not in ["John: 已安装", "John: 未安装", "John: 检测错误"]:
                self.johnStatusLabel.setText("John: 未安装")
                self.johnStatusLabel.setStyleSheet("color: #F44336;")
        if hasattr(self, 'hashcatStatusLabel'):
            if self.hashcatStatusLabel.text() not in ["Hashcat: 已安装", "Hashcat: 未安装", "Hashcat: 检测错误"]:
                self.hashcatStatusLabel.setText("Hashcat: 未安装")
                self.hashcatStatusLabel.setStyleSheet("color: #F44336;")
    
    def find_john_executable(self, john_path):
        """增强版：递归查找John the Ripper可执行文件"""
        # 如果直接是可执行文件
        if os.path.isfile(john_path) and (john_path.lower().endswith("john.exe") or john_path.lower().endswith("john")):
            return john_path
        # 如果是目录，递归查找
        if os.path.isdir(john_path):
            # 常见路径
            possible_paths = [
                os.path.join(john_path, "john.exe"),
                os.path.join(john_path, "john"),
                os.path.join(john_path, "run", "john.exe"),
                os.path.join(john_path, "run", "john")
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    return path
            # 递归查找所有子目录
            for exe in glob.glob(os.path.join(john_path, '**', 'john.exe'), recursive=True):
                return exe
            for exe in glob.glob(os.path.join(john_path, '**', 'john'), recursive=True):
                return exe
        # 记录尝试过的路径
        self.log_message(f"未找到John the Ripper可执行文件，已尝试路径: {john_path}", "warning")
        return None

    def find_hashcat_executable(self, hashcat_path):
        """增强版：递归查找Hashcat可执行文件"""
        import glob
        if os.path.isfile(hashcat_path) and (hashcat_path.lower().endswith("hashcat.exe") or hashcat_path.lower().endswith("hashcat")):
            return hashcat_path
        if os.path.isdir(hashcat_path):
            possible_paths = [
                os.path.join(hashcat_path, "hashcat.exe"),
                os.path.join(hashcat_path, "hashcat")
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    return path
            for exe in glob.glob(os.path.join(hashcat_path, '**', 'hashcat.exe'), recursive=True):
                return exe
            for exe in glob.glob(os.path.join(hashcat_path, '**', 'hashcat'), recursive=True):
                return exe
        self.log_message(f"未找到Hashcat可执行文件，已尝试路径: {hashcat_path}", "warning")
        return None
    
    def show_tool_paths_dialog(self):
        dialog = ToolPathsDialog(self, self.john_path, self.hashcat_path, self.opencl_path, self.perl_path)
        def refresh_and_update_fields():
            import glob, os
            base_dir = os.getcwd()
            john_candidates = glob.glob(os.path.join(base_dir, '**', 'john.exe'), recursive=True)
            hashcat_candidates = glob.glob(os.path.join(base_dir, '**', 'hashcat.exe'), recursive=True)
            opencl_candidates = glob.glob(os.path.join(base_dir, '**', 'OpenCL*'), recursive=True)
            perl_candidates = glob.glob(os.path.join(base_dir, '**', 'perl.exe'), recursive=True)
            updated = False
            if john_candidates:
                john_dir = os.path.dirname(john_candidates[0])
                if os.path.basename(john_dir).lower() == 'run':
                    john_dir = os.path.dirname(john_dir)
                dialog.john_path_edit.setText(john_dir)
                updated = True
                self.log_message(f"自动检测到John路径: {john_dir}", "success")
            if hashcat_candidates:
                hashcat_path = hashcat_candidates[0]
                dialog.hashcat_path_edit.setText(hashcat_path)
                updated = True
                self.log_message(f"自动检测到Hashcat路径: {hashcat_path}", "success")
            if opencl_candidates:
                opencl_dir = os.path.dirname(opencl_candidates[0])
                dialog.opencl_path_edit.setText(opencl_dir)
            if perl_candidates:
                dialog.perl_path_edit.setText(perl_candidates[0])
            if updated:
                self.force_detect_tools()
            else:
                self.set_status("未在当前目录及子目录找到工具", "warning")
        dialog.refresh_btn.clicked.connect(refresh_and_update_fields)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            paths = dialog.get_paths()
            self.john_path = paths["john_path"]
            self.hashcat_path = paths["hashcat_path"]
            self.opencl_path = paths.get("opencl_path", "")
            self.perl_path = paths.get("perl_path", "")
            config.set("john_path", self.john_path)
            config.set("hashcat_path", self.hashcat_path)
            config.set("opencl_path", self.opencl_path)
            config.set("perl_path", self.perl_path)
            self.set_status("工具路径已更新", "success")
            self.force_detect_tools()
    
    def show_about(self):
        """显示关于对话框"""
        dialog = AboutDialog(self, "4.0.5")
        dialog.exec_()
    
    def show_help_menu(self):
        """显示帮助菜单"""
        menu = QtWidgets.QMenu(self)
        # 帮助文档
        helpAction = menu.addAction("帮助文档")
        helpAction.triggered.connect(self.show_help)
        # 在线帮助
        onlineHelpAction = menu.addAction("在线帮助")
        onlineHelpAction.triggered.connect(self.show_online_help)
        # 分割线
        menu.addSeparator()
        # 贡献名单
        contributorsAction = menu.addAction("贡献名单")
        contributorsAction.triggered.connect(self.show_contributors)
        # 检查更新
        menu.addSeparator()
        checkUpdateAction = menu.addAction("检查更新")
        checkUpdateAction.triggered.connect(self.check_update)
        # 关于
        menu.addSeparator()
        aboutAction = menu.addAction("关于")
        aboutAction.triggered.connect(self.show_about)
        # 在按钮下方显示菜单
        pos = self.helpBtn.mapToGlobal(QtCore.QPoint(0, self.helpBtn.height()))
        menu.exec_(pos)

    def show_contributors(self):
        """显示贡献名单对话框（普通弹窗，优化版）"""
        try:
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("贡献名单")
            dialog.resize(400, 340)
            layout = QtWidgets.QVBoxLayout(dialog)
            desc = QtWidgets.QLabel("感谢以下朋友对本项目的支持与贡献：")
            desc.setAlignment(QtCore.Qt.AlignCenter)
            desc.setStyleSheet("color: #FFFFFF; font-size: 12px; text-decoration: none;")
            layout.addWidget(desc)
            table = QtWidgets.QTableWidget()
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(["昵称", "QQ号"])
            table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            table.setStyleSheet("""
                QHeaderView::section {
                    background: #2D2D30;
                    color: #CCCCCC;
                    border: 1px solid #444444;
                }
                QTableWidget {
                    background: #1E1E1E;
                    color: #E0E0E0;
                    gridline-color: #444444;
                    border: none;
                    border-radius: 0px;
                }
                QTableWidget::viewport {
                    background: #1E1E1E;
                }
                QTableView QTableCornerButton::section {
                    background: #2D2D30;
                    border: 1px solid #444444;
                }
                QTableView::item {
                    background: #1E1E1E;
                }
            """)
            contributors = [
                ("小明", "12345678"),
                ("小红", "87654321"),
                ("CoderA", "11223344"),
                ("安全研究员B", "55667788"),
            ]
            table.setRowCount(len(contributors))
            for i, (name, qq) in enumerate(contributors):
                table.setItem(i, 0, QtWidgets.QTableWidgetItem(name))
                table.setItem(i, 1, QtWidgets.QTableWidgetItem(qq))
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            layout.addWidget(table)
            tip = QtWidgets.QLabel("如有遗漏请联系开发者补充。")
            tip.setAlignment(QtCore.Qt.AlignCenter)
            tip.setStyleSheet("color: #CCCCCC; font-size: 12px;")
            layout.addWidget(tip)
            dialog.exec_()
        except Exception as e:
            show_error_dialog(self, "显示贡献名单时发生异常", detail=str(e))
    
    def show_help(self):
        """显示帮助对话框"""
        dialog = HelpDialog(self)
        dialog.exec_()
    
    def show_online_help(self):
        """打开在线帮助网页"""
        try:
            # 打开在线帮助页面，已更新为新链接
            online_help_url = "https://www.axiu.xyz/index.php/archives/3/"
            webbrowser.open(online_help_url)
            self.set_status("正在打开在线帮助...", "success")
        except Exception as e:
            show_error_dialog(self, "打开在线帮助失败", detail=str(e), suggestion="请检查网络连接，或手动访问帮助网址。")
    
    def check_update(self):
        """检查软件更新"""
        # 获取当前版本
        current_version = "4.0.5"
        
        # 创建正在检查更新的对话框
        progress_dialog = QtWidgets.QProgressDialog("正在检查更新...", "取消", 0, 100, self)
        progress_dialog.setWindowTitle("更新检查")
        progress_dialog.setAutoClose(True)
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setFixedWidth(380)  # 设置固定宽度为380px
        progress_dialog.setValue(10)
        
        # 创建检查更新的线程
        def check_update_task():
            try:
                # 模拟网络请求延迟
                time.sleep(1)
                progress_dialog.setValue(50)
                
                # 这里应该是实际检查更新的逻辑，以下是模拟
                latest_version = "4.0.5"  # 模拟最新版本
                download_url = "https://www.zipcracker.org/download"
                
                # 关闭进度对话框
                progress_dialog.setValue(100)
                
                # 在主线程中显示结果
                def show_result():
                    if current_version == latest_version:
                        show_info_dialog(self, f"您当前使用的已经是最新版本 ({current_version})。", title="检查更新")
                    else:
                        reply = QtWidgets.QMessageBox.question(
                            self, "有新版本可用", 
                            f"发现新版本: {latest_version}\n"
                            f"您当前的版本: {current_version}\n\n"
                            "是否前往下载页面?", 
                            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, 
                            QtWidgets.QMessageBox.Yes
                        )
                        
                        if reply == QtWidgets.QMessageBox.Yes:
                            webbrowser.open(download_url)
                
                # 使用安全的UI更新方法
                safe_ui_update(show_result)
                
            except Exception as e:
                # 关闭进度对话框
                progress_dialog.setValue(100)
                
                # 显示错误消息
                error_msg = str(e)
                safe_ui_update(lambda: self.set_status(f"检查更新失败: {error_msg}", "error"))
                log_error(e)
        
        # 显示进度对话框
        progress_dialog.show()
        
        # 启动线程
        threading.Thread(target=check_update_task, daemon=True).start()
    
    def update_crack_time(self):
        """更新破解时间"""
        # 如果正在破解，更新时间
        if self.is_cracking and self.start_time:
            elapsed_time = time.time() - self.start_time
            formatted_time = format_duration(elapsed_time)
            self.crackTimeLabel.setText(f"破解时间: {formatted_time}")
            
            # 更新任务状态
            self.update_active_tasks()
    
    def update_active_tasks(self):
        """更新活动任务状态"""
        # 获取活动任务
        active_tasks = self.task_manager.get_active_tasks()
        
        # 如果有活动任务，更新进度
        if active_tasks:
            for task in active_tasks:
                # 如果是破解任务
                if task.task_type == TaskType.CRACK:
                    # 移除进度条更新代码
                    
                    # 如果任务已完成
                    if task.status == TaskStatus.COMPLETED:
                        self.is_cracking = False
                        self.timer.stop()
                        
                        # 如果任务有结果，显示密码
                        if task.result:
                            self.passwordEdit.setText(task.result)
                            self.copyPasswordBtn.setEnabled(True)
                            self.set_status(f"破解成功！密码: {task.result}", "success")
                            
                            # 添加到历史记录
                            self.history_manager.add_record(
                                file_path=self.selected_file,
                                hash_value=self.hash_value,
                                password=task.result,
                                crack_time=time.time() - self.start_time
                            )
                        else:
                            self.set_status("破解完成，未找到密码", "warning")
                        
                        # 更新按钮状态
                        self.startCrackBtn.setEnabled(True)
                        self.pauseResumeBtn.setEnabled(True)
                    
                    # 如果任务失败
                    elif task.status == TaskStatus.FAILED:
                        self.is_cracking = False
                        self.timer.stop()
                        self.set_status(f"破解失败: {task.error}", "error")
                        
                        # 更新按钮状态
                        self.startCrackBtn.setEnabled(True)
                        self.pauseResumeBtn.setEnabled(True)
    
    def set_status(self, message, status_type="normal"):
        """设置状态栏消息，支持跑马灯和不同颜色"""
        # 替换为跑马灯标签
        if not isinstance(self.statusLabel, MarqueeLabel):
            # 替换原有 QLabel
            parent = self.statusLabel.parent()
            layout = self.statusLabel.parentWidget().layout()
            idx = layout.indexOf(self.statusLabel)
            layout.removeWidget(self.statusLabel)
            self.statusLabel.deleteLater()
            self.statusLabel = MarqueeLabel(message)
            layout.insertWidget(idx, self.statusLabel)
        # 设置颜色
        if status_type == "normal":
            self.statusLabel.setTextColor("#4CAF50")
        elif status_type == "warning":
            self.statusLabel.setTextColor("#FF9800")
        elif status_type == "error":
            self.statusLabel.setTextColor("#F44336")
        else:
            self.statusLabel.setTextColor("#4CAF50")
        self.statusLabel.setText(message)
        # 记录到日志
        if status_type == "error":
            self.log_message(f"错误: {message}", "error")
        elif status_type == "warning":
            self.log_message(f"警告: {message}", "warning")
        elif status_type == "success":
            self.log_message(message, "success")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 如果正在破解，询问是否退出
        if self.is_cracking:
            reply = QtWidgets.QMessageBox.question(
                self, "确认退出", 
                "正在进行破解任务，确定要退出吗？", 
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, 
                QtWidgets.QMessageBox.No
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                # 停止破解
                self.stop_crack()
                # 关闭任务管理器
                self.task_manager.shutdown()
                # 停止定时器
                if hasattr(self, 'timer'):
                    self.timer.stop()
                if hasattr(self, 'status_timer'):
                    self.status_timer.stop()
                self.kill_hashcat_processes()  # 新增：关闭前杀死hashcat
                event.accept()
            else:
                event.ignore()
        else:
            # 关闭任务管理器
            self.task_manager.shutdown()
            # 停止定时器
            if hasattr(self, 'timer'):
                self.timer.stop()
            if hasattr(self, 'status_timer'):
                self.status_timer.stop()
            self.kill_hashcat_processes()  # 新增：关闭前杀死hashcat
            event.accept()
    
    # 窗口拖动相关方法
    def titleBarMousePressEvent(self, event):
        """处理标题栏鼠标按下事件"""
        if event.button() == QtCore.Qt.LeftButton:
            self.moving = True
            self.last_pos = event.globalPos()
    
    def titleBarMouseMoveEvent(self, event):
        """处理标题栏鼠标移动事件"""
        if self.moving and event.buttons() == QtCore.Qt.LeftButton:
            delta = event.globalPos() - self.last_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.last_pos = event.globalPos()
    
    def titleBarMouseReleaseEvent(self, event):
        """处理标题栏鼠标释放事件"""
        if event.button() == QtCore.Qt.LeftButton:
            self.moving = False
    
    # 文件拖放事件
    def logTextDragEnterEvent(self, event):
        """处理日志区域拖拽进入事件"""
        if event.mimeData().hasUrls():
            # 只接受文件URL
            event.acceptProposedAction()
    
    def logTextDropEvent(self, event):
        """处理日志区域拖拽释放事件"""
        if event.mimeData().hasUrls():
            # 获取第一个URL（只处理一个文件）
            url = event.mimeData().urls()[0]
            # 转换为本地路径
            file_path = url.toLocalFile()
            # 检查是否为支持的文件类型
            if is_supported_file(file_path):
                # 设置文件路径并更新UI
                self.select_file(file_path)
                # 拖入文件后自动检测对应辅助工具路径并写入日志
                ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                john_dir = self.john_path if self.john_path else ''
                tool_map = {
                    'rar': 'rar2john.exe',
                    'zip': 'zip2john.exe',
                    '7z': '7z2john.exe',
                    'pdf': 'pdf2john.exe',
                    'doc': 'office2john.py',
                    'docx': 'office2john.py',
                    'xls': 'office2john.py',
                    'xlsx': 'office2john.py',
                    'ppt': 'office2john.py',
                    'pptx': 'office2john.py',
                }
                tool_name = tool_map.get(ext)
                tool_path = None
                if tool_name and john_dir:
                    # 递归查找john目录下的辅助工具
                    import glob
                    candidates = glob.glob(os.path.join(john_dir, '**', tool_name), recursive=True)
                    if candidates:
                        tool_path = candidates[0]
                if tool_name:
                    if tool_path and os.path.exists(tool_path):
                        self.log_message(f"检测到{tool_name}路径: {tool_path}", "success")
                    else:
                        self.log_message(f"未检测到有效的{tool_name}，请检查John目录", "warning")
            else:
                # 不支持的文件类型
                self.set_status(f"不支持的文件类型，支持: {', '.join(SUPPORTED_EXTS)}", "error")
    
    def log_message(self, message, level="info"):
        """向日志文本框添加消息，线程安全版本
        
        Args:
            message (str): 日志消息
            level (str): 日志级别，可选值：info, success, warning, error
        """
        # 检查是否在主线程
        if QtCore.QThread.currentThread() == QtWidgets.QApplication.instance().thread():
            # 在主线程，直接调用
            self._actual_log_message(message, level)
        else:
            # 在子线程，使用信号-槽
            self.log_signal.emit(message, level)
    
    @QtCore.pyqtSlot(str, str)
    def safe_log_message(self, message, level="info"):
        """线程安全的日志更新槽函数
        
        Args:
            message (str): 日志消息
            level (str): 日志级别
        """
        self._actual_log_message(message, level)
    
    def _actual_log_message(self, message, level="info"):
        """实际实现日志更新的内部方法
        
        Args:
            message (str): 日志消息
            level (str): 日志级别
        """
        # 获取当前时间
        current_time = get_formatted_time()
        
        # 设置消息前缀和颜色
        prefix = "INFO"
        color = "#CCCCCC"
        if level == "success":
            prefix = "SUCCESS"
            color = "#4CAF50"
        elif level == "warning":
            prefix = "WARNING"
            color = "#FF9800"
        elif level == "error":
            prefix = "ERROR"
            color = "#F44336"
        
        # 格式化消息
        formatted_message = f"[{current_time}] [{prefix}] {message}"
        
        # 设置HTML格式以支持颜色
        html_message = f"<span style='color: {color};'>{formatted_message}</span>"
        
        # 添加到日志文本框
        self.logText.append(html_message)
        
        # 自动滚动到底部
        self.logText.moveCursor(QtGui.QTextCursor.End)
    
    def clear_log(self):
        """清空日志文本框"""
        self.logText.clear()
        self.log_message("日志已清空")
    
    def export_log(self):
        """导出日志到文件"""
        # 获取当前时间作为文件名的一部分
        current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"zipcracker_log_{current_time}.txt"
        
        # 显示保存文件对话框
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出日志", default_filename, "文本文件 (*.txt);;所有文件 (*)"
        )
        
        if filename:
            try:
                # 获取纯文本内容
                log_content = self.logText.toPlainText()
                
                # 写入文件
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(log_content)
                
                self.set_status(f"日志已导出到 {filename}", "success")
            except Exception as e:
                self.set_status(f"导出日志失败: {str(e)}", "error")
    
    def show_file_menu(self):
        """显示文件菜单"""
        menu = QtWidgets.QMenu(self)
        # 打开文件
        openAction = menu.addAction("打开文件")
        openAction.triggered.connect(self.choose_file)
        # 最近打开的文件
        recentFilesMenu = QtWidgets.QMenu("最近打开", self)
        recent_files = config.get("recent_files", [])
        if recent_files:
            for i, file_path in enumerate(recent_files[:5]):
                action = recentFilesMenu.addAction(os.path.basename(file_path))
                action.setData(file_path)
                action.triggered.connect(lambda checked, path=file_path: self.select_file(path))
        else:
            emptyAction = recentFilesMenu.addAction("无最近文件")
            emptyAction.setEnabled(False)
        menu.addMenu(recentFilesMenu)
        menu.addSeparator()
        saveResultAction = menu.addAction("保存破解结果")
        saveResultAction.triggered.connect(self.save_crack_result)
        saveResultAction.setEnabled(self.passwordEdit.text() != "")
        # 新增：保存破解进度、加载破解进度
        saveProgressAction = menu.addAction("保存破解进度")
        saveProgressAction.triggered.connect(self.save_crack_progress)
        loadProgressAction = menu.addAction("加载破解进度")
        loadProgressAction.triggered.connect(self.load_crack_progress)
        exportLogAction = menu.addAction("导出日志")
        exportLogAction.triggered.connect(self.export_log)
        menu.addSeparator()
        exitAction = menu.addAction("退出")
        exitAction.triggered.connect(self.close)
        self.openFileBtn.setChecked(True)
        menu.exec_(self.openFileBtn.mapToGlobal(QtCore.QPoint(0, self.openFileBtn.height())))
        self.openFileBtn.setChecked(False)

    def show_settings_menu(self):
        """显示设置菜单"""
        menu = QtWidgets.QMenu(self)
        toolPathsAction = menu.addAction("工具路径")
        toolPathsAction.triggered.connect(self.show_tool_paths_dialog)
        toolDownloadMenu = QtWidgets.QMenu("工具下载", self)
        downloadJohnAction = toolDownloadMenu.addAction("下载John the Ripper")
        downloadJohnAction.triggered.connect(self.download_john)
        downloadHashcatAction = toolDownloadMenu.addAction("下载Hashcat")
        downloadHashcatAction.triggered.connect(self.download_hashcat)
        menu.addMenu(toolDownloadMenu)
        dictAction = menu.addAction("字典管理")
        dictAction.triggered.connect(self.show_dict_manager)
        historyAction = menu.addAction("历史记录")
        historyAction.triggered.connect(self.show_history_dialog)
        perfAction = menu.addAction("性能设置")
        perfAction.triggered.connect(self.show_performance_settings)
        menu.addSeparator()
        aboutAction = menu.addAction("关于")
        aboutAction.triggered.connect(self.show_about)
        self.settingsBtn.setChecked(True)
        menu.exec_(self.settingsBtn.mapToGlobal(QtCore.QPoint(0, self.settingsBtn.height())))
        self.settingsBtn.setChecked(False)

    def show_tools_menu(self):
        """显示工具菜单"""
        menu = QtWidgets.QMenu(self)
        maskGenAction = menu.addAction("掩码生成器")
        maskGenAction.triggered.connect(self.show_mask_gen)
        ruleEditorAction = menu.addAction("密码规则编辑器")
        ruleEditorAction.triggered.connect(self.show_rule_editor)
        dictMergeAction = menu.addAction("字典合并工具")
        dictMergeAction.triggered.connect(self.show_dict_merge)
        # 新增 John破解 子菜单
        johnCrackAction = menu.addAction("John破解")
        johnCrackAction.triggered.connect(self.handle_john_crack_action)
        self.toolsBtn.setChecked(True)
        menu.exec_(self.toolsBtn.mapToGlobal(QtCore.QPoint(0, self.toolsBtn.height())))
        self.toolsBtn.setChecked(False)

    def handle_john_crack_action(self):
        print("[DEBUG] handle_john_crack_action called")
        self.show_john_crack_dialog()

    def show_john_crack_dialog(self, prefill_hash=None, prefill_file=None):
        """弹出 John 专业破解界面，支持预填哈希和独立文件选择/哈希提取，布局美化"""
        from PyQt5 import QtWidgets, QtCore
        import os
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("John 专业破解")
        dialog.resize(560, 480)
        mainLayout = QtWidgets.QVBoxLayout(dialog)
        mainLayout.setContentsMargins(12, 12, 12, 12)
        mainLayout.setSpacing(8)
        # 顶部表单区
        formLayout = QtWidgets.QFormLayout()
        formLayout.setLabelAlignment(QtCore.Qt.AlignRight)
        formLayout.setFormAlignment(QtCore.Qt.AlignTop)
        formLayout.setHorizontalSpacing(8)
        formLayout.setVerticalSpacing(6)
        # 文件选择
        fileEdit = QtWidgets.QLineEdit()
        fileEdit.setReadOnly(True)
        fileBtn = QtWidgets.QPushButton("打开文件")
        fileBtn.setFixedWidth(80)
        fileRow = QtWidgets.QHBoxLayout()
        fileRow.setSpacing(4)
        fileRow.addWidget(fileEdit)
        fileRow.addWidget(fileBtn)
        formLayout.addRow("加密文件：", fileRow)
        # 自动填充文件路径
        if prefill_file:
            fileEdit.setText(str(prefill_file))
        # 哈希区
        hashEdit = QtWidgets.QTextEdit()
        hashEdit.setReadOnly(False)
        hashEdit.setFixedHeight(36)
        hashBtn = QtWidgets.QPushButton("提取哈希")
        hashBtn.setFixedWidth(80)
        hashRow = QtWidgets.QHBoxLayout()
        hashRow.setSpacing(4)
        hashRow.addWidget(hashEdit)
        hashRow.addWidget(hashBtn)
        formLayout.addRow("哈希值：", hashRow)
        # 自动填充哈希
        if prefill_hash:
            hashEdit.setText(str(prefill_hash))
        # 攻击模式
        attackModeCombo = QtWidgets.QComboBox()
        attackModeCombo.addItems(["字典破解", "掩码破解", "规则破解", "暴力破解"])
        attackModeCombo.setMinimumWidth(180)
        formLayout.addRow("攻击模式：", attackModeCombo)
        # CPU/GPU切换
        engineLayout = QtWidgets.QHBoxLayout()
        cpuRadio = QtWidgets.QRadioButton("CPU")  # 局部变量
        gpuRadio = QtWidgets.QRadioButton("GPU")  # 局部变量
        cpuRadio.setChecked(True)
        radio_style = '''
QRadioButton {
    color: #CCCCCC;
    spacing: 5px;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #777777;
    border-radius: 7px;
    background-color: #1E1E1E;
}
QRadioButton::indicator:checked {
    background-color: #4C9EDE;
    border: 1px solid #777777;
}
QRadioButton::indicator:unchecked {
    background-color: #222222;
    border: 1px solid #777777;
}
'''
        cpuRadio.setStyleSheet(radio_style)
        gpuRadio.setStyleSheet(radio_style)
        engineLayout.addWidget(cpuRadio)
        engineLayout.addWidget(gpuRadio)
        formLayout.addRow("引擎：", engineLayout)
        mainLayout.addLayout(formLayout)
        # 参数区 QStackedWidget
        attackStack = QtWidgets.QStackedWidget()
        # 1. 字典破解
        dictWidget = QtWidgets.QWidget()
        dictForm = QtWidgets.QFormLayout(dictWidget)
        dictForm.setContentsMargins(0, 0, 0, 0)
        dictForm.setHorizontalSpacing(8)
        dictForm.setVerticalSpacing(4)
        dictEdit = QtWidgets.QLineEdit()
        dictBtn = QtWidgets.QPushButton("浏览")
        dictBtn.setFixedWidth(80)
        dictRow = QtWidgets.QHBoxLayout()
        dictRow.setSpacing(4)
        dictRow.addWidget(dictEdit)
        dictRow.addWidget(dictBtn)
        dictForm.addRow("字典文件：", dictRow)
        attackStack.addWidget(dictWidget)
        # 2. 掩码破解
        maskWidget = QtWidgets.QWidget()
        maskForm = QtWidgets.QFormLayout(maskWidget)
        maskForm.setContentsMargins(0, 0, 0, 0)
        maskForm.setHorizontalSpacing(8)
        maskForm.setVerticalSpacing(4)
        maskEdit = QtWidgets.QLineEdit()
        maskEdit.setPlaceholderText("如 ?l?l?l?d?d")
        maskGenBtn = QtWidgets.QPushButton("生成")
        maskGenBtn.setFixedWidth(80)
        maskRow = QtWidgets.QHBoxLayout()
        maskRow.setSpacing(4)
        maskRow.addWidget(maskEdit)
        maskRow.addWidget(maskGenBtn)
        maskForm.addRow("掩码：", maskRow)
        attackStack.addWidget(maskWidget)
        # 掩码生成器逻辑
        def on_mask_gen():
            from zipcracker_dialogs import MaskGeneratorDialog
            dialog = MaskGeneratorDialog(self)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                mask = dialog.get_mask()
                if mask:
                    maskEdit.setText(mask)
        maskGenBtn.clicked.connect(on_mask_gen)
        # 3. 规则破解
        ruleWidget = QtWidgets.QWidget()
        ruleForm = QtWidgets.QFormLayout(ruleWidget)
        ruleForm.setContentsMargins(0, 0, 0, 0)
        ruleForm.setHorizontalSpacing(8)
        ruleForm.setVerticalSpacing(4)
        ruleDictEdit = QtWidgets.QLineEdit()
        ruleDictBtn = QtWidgets.QPushButton("浏览字典")
        ruleDictBtn.setFixedWidth(80)
        ruleDictRow = QtWidgets.QHBoxLayout()
        ruleDictRow.setSpacing(4)
        ruleDictRow.addWidget(ruleDictEdit)
        ruleDictRow.addWidget(ruleDictBtn)
        ruleFileEdit = QtWidgets.QLineEdit()
        ruleFileBtn = QtWidgets.QPushButton("浏览规则")
        ruleFileBtn.setFixedWidth(80)
        ruleFileRow = QtWidgets.QHBoxLayout()
        ruleFileRow.setSpacing(4)
        ruleFileRow.addWidget(ruleFileEdit)
        ruleFileRow.addWidget(ruleFileBtn)
        ruleForm.addRow("字典文件：", ruleDictRow)
        ruleForm.addRow("规则文件：", ruleFileRow)
        attackStack.addWidget(ruleWidget)
        # 4. 暴力破解
        bruteWidget = QtWidgets.QWidget()
        bruteForm = QtWidgets.QFormLayout(bruteWidget)
        bruteForm.setContentsMargins(0, 0, 0, 0)
        bruteForm.setHorizontalSpacing(8)
        bruteForm.setVerticalSpacing(4)
        maxLenSpin = QtWidgets.QSpinBox()
        maxLenSpin.setRange(1, 32)
        maxLenSpin.setValue(6)
        charsetCombo = QtWidgets.QComboBox()
        charsetCombo.addItems(["All", "数字 (0-9)", "小写 (a-z)", "大写 (A-Z)", "数字+小写", "数字+大写", "自定义"])
        customCharsetEdit = QtWidgets.QLineEdit()
        customCharsetEdit.setPlaceholderText("自定义字符集，如 abc123!@#")
        customCharsetEdit.setEnabled(False)
        def on_charset_changed(idx):
            customCharsetEdit.setEnabled(idx == 6)
        charsetCombo.currentIndexChanged.connect(on_charset_changed)
        bruteRow1 = QtWidgets.QHBoxLayout()
        bruteRow1.setSpacing(4)
        bruteRow1.addWidget(QtWidgets.QLabel("最大长度："))
        bruteRow1.addWidget(maxLenSpin)
        bruteForm.addRow("", bruteRow1)
        bruteRow2 = QtWidgets.QHBoxLayout()
        bruteRow2.setSpacing(4)
        bruteRow2.addWidget(QtWidgets.QLabel("字符集："))
        bruteRow2.addWidget(charsetCombo)
        bruteRow2.addWidget(customCharsetEdit)
        bruteForm.addRow("", bruteRow2)
        attackStack.addWidget(bruteWidget)
        mainLayout.addWidget(attackStack)
        # 切换逻辑
        def on_attack_mode_changed(idx):
            attackStack.setCurrentIndex(idx)
        attackModeCombo.currentIndexChanged.connect(on_attack_mode_changed)
        attackStack.setCurrentIndex(0)
        # 按钮区
        btnLayout = QtWidgets.QHBoxLayout()
        btnLayout.setSpacing(8)
        startBtn = QtWidgets.QPushButton("开始破解")
        stopBtn = QtWidgets.QPushButton("停止")
        startBtn.setMinimumHeight(28)
        stopBtn.setMinimumHeight(28)
        btnLayout.addWidget(startBtn)
        btnLayout.addWidget(stopBtn)
        mainLayout.addLayout(btnLayout)
        # 日志输出前增加密码显示区
        pwdLayout = QtWidgets.QHBoxLayout()
        pwdLabel = QtWidgets.QLabel("密码:")
        pwdEdit = QtWidgets.QLineEdit()
        pwdEdit.setReadOnly(True)
        pwdEdit.setPlaceholderText("未找到")
        pwdCopyBtn = QtWidgets.QPushButton("复制")
        pwdCopyBtn.setFixedWidth(60)
        def on_copy_pwd():
            if pwdEdit.text():
                QtWidgets.QApplication.clipboard().setText(pwdEdit.text())
        pwdCopyBtn.clicked.connect(on_copy_pwd)
        pwdLayout.addWidget(pwdLabel)
        pwdLayout.addWidget(pwdEdit)
        pwdLayout.addWidget(pwdCopyBtn)
        mainLayout.addLayout(pwdLayout)
        # 日志输出
        logLabel = QtWidgets.QLabel("日志输出：")
        mainLayout.addWidget(logLabel)
        logEdit = QtWidgets.QTextEdit()
        logEdit.setReadOnly(True)
        logEdit.setFixedHeight(90)
        mainLayout.addWidget(logEdit)
        # 关闭按钮
        btnBox = QtWidgets.QDialogButtonBox()
        closeBtn = btnBox.addButton("关闭", QtWidgets.QDialogButtonBox.RejectRole)
        btnBox.rejected.connect(dialog.reject)
        mainLayout.addWidget(btnBox)
        # 文件选择逻辑
        def on_choose_file():
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(dialog, "选择加密文件", "", "加密文件 (*.zip *.rar *.7z *.doc *.docx *.xls *.xlsx *.ppt *.pptx *.pdf);;所有文件 (*)")
            if file_path:
                fileEdit.setText(file_path)
        fileBtn.clicked.connect(on_choose_file)
        # 提取哈希逻辑
        def on_extract_hash():
            file_path = fileEdit.text().strip()
            if not file_path or not os.path.exists(file_path):
                show_error_dialog(dialog, "请先选择有效的加密文件！")
                return
            try:
                from zipcracker_utils import extract_hash_safe
                file_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                hash_val = extract_hash_safe(self.john_path, file_path, file_ext)
                if hash_val:
                    hashEdit.setText(hash_val[0])
                    self.log_message(f"[John] 哈希提取成功: {hash_val[0][:60]}...", "success")
                else:
                    show_error_dialog(dialog, "未能提取到有效哈希！", suggestion="请检查文件类型和内容，或尝试手动提取哈希。")
            except Exception as e:
                self.log_message(f"[John] 哈希提取异常: {e}", "error")
                show_error_dialog(dialog, "哈希提取异常", detail=str(e))
        hashBtn.clicked.connect(on_extract_hash)
        # 字典/规则/掩码文件浏览逻辑
        def on_dict_manager():
            from zipcracker_dialogs import DictManagerDialog
            dialog = DictManagerDialog(self)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                selected_path = dialog.get_selected_dict_path()
                if selected_path:
                    dictEdit.setText(selected_path)
        dictBtn.clicked.connect(on_dict_manager)
        ruleDictBtn.clicked.connect(lambda: ruleDictEdit.setText(QtWidgets.QFileDialog.getOpenFileName(dialog, "选择字典文件", "", "文本文件 (*.txt *.dic);;所有文件 (*)")[0]))
        ruleFileBtn.clicked.connect(lambda: ruleFileEdit.setText(QtWidgets.QFileDialog.getOpenFileName(dialog, "选择规则文件", "", "规则文件 (*.rule);;所有文件 (*)")[0]))
        # 破解进程管理
        john_process = None
        def safe_append_log(msg):
            try:
                if logEdit and not hasattr(logEdit, 'wasDeleted'):
                    logEdit.append(msg)
            except Exception:
                pass
        def get_office_format():
            return "office-opencl" if gpuRadio.isChecked() else "office"
        def start_crack():
            nonlocal john_process
            if john_process is not None:
                safe_append_log("已有破解进程在运行，请先停止！")
                return
            hash_val = hashEdit.toPlainText().strip()
            mode_idx = attackModeCombo.currentIndex()
            cmd = []
            john_exe = self.find_john_executable(self.john_path) if hasattr(self, 'john_path') else "john"
            is_office = hash_val.strip().startswith("$office$")
            session_name = f"zipcracker_{int(time.time())}"
            import glob, os
            rec_dir = os.path.dirname(john_exe)
            for f in glob.glob(os.path.join(rec_dir, "*.rec")):
                try:
                    os.remove(f)
                except Exception:
                    pass
            if is_office:
                cmd.append(john_exe)
                cmd.append(f"--format={get_office_format()}")
            else:
                cmd.append(john_exe)
            cmd.append(f"--session={session_name}")
            if mode_idx == 0:
                cmd.append("--wordlist=" + dictEdit.text().strip())
            elif mode_idx == 1:
                cmd.append("--mask=" + maskEdit.text().strip())
            elif mode_idx == 2:
                cmd.append("--wordlist=" + ruleDictEdit.text().strip())
                cmd.append("--rules=" + ruleFileEdit.text().strip())
            elif mode_idx == 3:
                maxlen = maxLenSpin.value()
                charset_idx = charsetCombo.currentIndex()
                if charset_idx == 0:
                    inc_mode = "All"
                elif charset_idx == 1:
                    inc_mode = "Digits"
                elif charset_idx == 2:
                    inc_mode = "Alpha"
                elif charset_idx == 3:
                    inc_mode = "Alnum"
                elif charset_idx == 4:
                    inc_mode = "DigitsAlpha"
                elif charset_idx == 5:
                    inc_mode = "DigitsUpper"
                else:
                    inc_mode = "All"
                cmd += [f"--incremental={inc_mode}", f"--max-length={maxlen}"]
                if charset_idx == 6 and customCharsetEdit.text():
                    cmd += [f"--charset={customCharsetEdit.text().strip()}"]
            # 针对7z哈希，自动加--format参数
            if hash_val.strip().startswith("$7z$"):
                if gpuRadio.isChecked():
                    cmd.append("--format=7z-opencl")
                else:
                    cmd.append("--format=7z")
            import tempfile
            temp_hash = tempfile.NamedTemporaryFile(delete=False, mode="w", encoding="utf-8", suffix=".txt")
            temp_hash.write(hash_val)
            temp_hash.close()
            hashfile_path = temp_hash.name
            cmd.append(hashfile_path)
            safe_append_log(f"[启动] {' '.join(cmd)}")
            startBtn.setEnabled(False)
            stopBtn.setEnabled(True)
            from PyQt5.QtCore import QProcess, QIODevice
            john_process = QProcess(dialog)
            john_process.setProcessChannelMode(QProcess.MergedChannels)
            # 实时进度线程
            progress_stop = threading.Event()
            def progress_worker():
                import subprocess
                while not progress_stop.is_set() and john_process.state() == QProcess.Running:
                    try:
                        result = subprocess.run([john_exe, f"--status={session_name}"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
                        status = result.stdout.strip()
                        if status:
                            safe_append_log("[进度] " + status.splitlines()[-1])
                    except Exception:
                        pass
                    time.sleep(2)
            progress_thread = threading.Thread(target=progress_worker, daemon=True)
            # 新增：最大运行时长检测线程
            MAX_RUNTIME_SECONDS = 2 * 60 * 60  # 2小时
            def john_timeout_watcher():
                import time
                start_time = time.time()
                while john_process is not None and john_process.state() == QProcess.Running:
                    if time.time() - start_time > MAX_RUNTIME_SECONDS:
                        safe_append_log(f"<span style='color:#F44336;'><b>[超时] John破解进程已运行超过{MAX_RUNTIME_SECONDS//3600}小时，已自动终止！</b></span>")
                        john_process.kill()
                        QtWidgets.QMessageBox.warning(dialog, "破解超时", f"John破解进程已运行超过{MAX_RUNTIME_SECONDS//3600}小时，已自动终止！")
                        break
                    time.sleep(10)
            timeout_thread = threading.Thread(target=john_timeout_watcher, daemon=True)
            def on_ready():
                try:
                    if logEdit:
                        data = john_process.readAllStandardOutput().data().decode(errors="ignore")
                        if data:
                            # 检查常见报错并高亮输出
                            if "No OpenCL devices found" in data:
                                safe_append_log("<span style='color:#F44336;'><b>[错误] 未检测到OpenCL设备，无法使用GPU破解。请检查显卡驱动和OpenCL环境，或切换到CPU破解。</b></span>")
                                show_error_dialog(dialog, "未检测到OpenCL设备，无法使用GPU破解。", suggestion="请检查显卡驱动和OpenCL环境，或切换到CPU破解。")
                            elif "Invalid hash" in data or "No password hashes loaded" in data:
                                safe_append_log("<span style='color:#F44336;'><b>[错误] 哈希无效或未能加载。请检查哈希格式和完整性。</b></span>")
                                show_error_dialog(dialog, "哈希无效或未能加载。", suggestion="请检查哈希格式和完整性。")
                            else:
                                safe_append_log(data.rstrip())
                            if logEdit.document().blockCount() > 1000:
                                logEdit.clear()
                                safe_append_log("[日志已自动清空，防止卡顿]")
                except Exception:
                    pass
            john_process.readyReadStandardOutput.connect(on_ready)
            john_process.readyReadStandardError.connect(on_ready)
            def on_finished(exitCode, exitStatus):
                try:
                    progress_stop.set()
                    safe_append_log(f"[完成] 进程退出，代码: {exitCode}")
                    startBtn.setEnabled(True)
                    stopBtn.setEnabled(False)
                    nonlocal john_process
                    john_process = None
                    import subprocess
                    show_cmd = [john_exe, "--show", hashfile_path]
                    result = subprocess.run(show_cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
                    safe_append_log("[密码结果]")
                    safe_append_log(result.stdout.strip() or "未找到密码")
                    # 自动填入密码显示框
                    lines = result.stdout.strip().splitlines()
                    found = False
                    for line in lines:
                        if ':' in line:
                            parts = line.split(':', 2)
                            if len(parts) >= 2 and parts[1]:
                                password = parts[1].strip()
                                if password:
                                    pwdEdit.setText(password)
                                    found = True
                                    # --- 新增：同步到主界面 ---
                                    self.passwordEdit.setText(password)
                                    self.copyPasswordBtn.setEnabled(True)
                                    self.set_status("John破解获得密码，已自动填充", "success")
                                    for log_line in logEdit.toPlainText().splitlines():
                                        self.log_message(log_line)
                                    break
                    if not found:
                        pwdEdit.setText("未破解成功")
                    print(f"[DEBUG] on_finished: pwdEdit={pwdEdit.text()}, logEdit={logEdit.toPlainText()}")
                except Exception as e:
                    pwdEdit.setText("未破解成功")
                    safe_append_log(f"<span style='color:#F44336;'><b>[异常] 破解流程异常: {e}</b></span>")
                    show_error_dialog(dialog, "破解流程异常", detail=str(e))
                finally:
                    try:
                        os.remove(hashfile_path)
                    except Exception:
                        pass
            john_process.finished.connect(on_finished)
            try:
                john_process.start(cmd[0], cmd[1:])
                if not john_process.waitForStarted(2000):
                    raise RuntimeError("无法启动John进程！")
                progress_thread.start()
                timeout_thread.start()
            except Exception as e:
                safe_append_log(f"[错误] 启动John失败: {e}")
                QtWidgets.QMessageBox.critical(dialog, "John启动失败", f"无法启动John进程：{e}\n请检查路径、权限和依赖。")
                startBtn.setEnabled(True)
                stopBtn.setEnabled(False)
                try:
                    os.remove(hashfile_path)
                except Exception:
                    pass
                return
        def stop_crack():
            nonlocal john_process
            if john_process is not None:
                john_process.kill()
                safe_append_log("[操作] 已请求终止John进程")
                john_process = None
                startBtn.setEnabled(True)
                stopBtn.setEnabled(False)
            else:
                safe_append_log("[提示] 当前无运行中的破解进程")
        startBtn.clicked.connect(start_crack)
        stopBtn.clicked.connect(stop_crack)
        # 对话框关闭时安全回收进程，并收集密码和日志
        result = {"password": "", "log": ""}
        def on_dialog_close(event):
            nonlocal john_process
            if john_process is not None:
                john_process.kill()
                john_process = None
            # 收集密码和日志并同步到主界面
            password = pwdEdit.text()
            log_content = logEdit.toPlainText()
            print(f"[DEBUG] on_dialog_close: pwdEdit={password}, logEdit={log_content}")
            if password:
                self.passwordEdit.setText(password)
                self.copyPasswordBtn.setEnabled(True)
                self.set_status("John破解获得密码，已自动填充", "success")
            if log_content:
                for line in log_content.splitlines():
                    self.log_message(line)
            event.accept()
        dialog.closeEvent = on_dialog_close
        dialog.exec_()
        # 不再返回result
    
    def choose_file(self):
        """显示文件选择对话框"""
        file_filter = "支持文件 (" + " ".join([f"*.{ext.lstrip('.')}" for ext in SUPPORTED_EXTS]) + ");;所有文件 (*)"
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择文件", "", file_filter
        )
        if filename:
            self.select_file(filename)
            # 选中文件后，禁用"打开文件"，启用"提取哈希"，禁用"开始破解"
            self.extractHashBtn.setEnabled(False)
            self.copyHashBtn.setEnabled(True)
            self.startCrackBtn.setEnabled(False)
    
    def select_file(self, file_path):
        """设置选中的文件
        
        Args:
            file_path (str): 文件路径
        """
        try:
            from zipcracker_utils import has_chinese
            # 检查文件是否存在
            if not os.path.isfile(file_path):
                self.set_status("选中的文件不存在", "error")
                return
            # 检查文件路径和文件名是否包含中文
            file_name = os.path.basename(file_path)
            if has_chinese(file_path) or has_chinese(file_name):
                QtWidgets.QMessageBox.warning(self, "路径警告", f"检测到打开的文件路径或文件名包含中文字符，建议将文件移动到纯英文路径并重命名为英文，否则可能导致提取哈希或破解失败！\n\n当前路径: {file_path}")
            # 获取文件名和扩展名
            file_name = os.path.basename(file_path)
            file_ext = os.path.splitext(file_name)[1].lower().strip(".")
            
            # 检查文件扩展名是否支持
            if not is_supported_file(file_path):
                self.set_status(f"不支持的文件类型，支持: {', '.join(SUPPORTED_EXTS)}", "error")
                return
            
            # 设置状态
            self.selected_file = file_path
            self.file_ext = file_ext
            
            # 更新界面
            self.hashValueEdit.setPlainText("")  # 使用setPlainText替代clear
            self.hash_value = ""
            self.hash_file = ""
            self.passwordEdit.clear()
            self.passwordEdit.setPlaceholderText("未找到")
            self.copyPasswordBtn.setEnabled(False)
            # 选中文件后，禁用"打开文件"，启用"提取哈希"，禁用"开始破解"
            self.extractHashBtn.setEnabled(False)
            self.copyHashBtn.setEnabled(True)
            self.startCrackBtn.setEnabled(False)
            
            # 记录日志
            self.log_message(f"已选择文件: {file_path}")
            self.set_status("文件已选择，请提取哈希", "success")
            
            # 添加到最近文件列表
            self.add_to_recent_files(file_path)
        except Exception as e:
            self.set_status(f"设置文件失败: {str(e)}", "error")
            log_error(e)
    
    def add_to_recent_files(self, file_path):
        """添加文件到最近文件列表
        
        Args:
            file_path (str): 文件路径
        """
        try:
            # 获取当前最近文件列表
            recent_files = config.get("recent_files", [])
            
            # 如果文件已在列表中，先移除
            if file_path in recent_files:
                recent_files.remove(file_path)
                
            # 将新文件添加到列表开头
            recent_files.insert(0, file_path)
            
            # 限制列表长度，最多保存10个文件
            recent_files = recent_files[:10]
            
            # 保存到配置
            config.set("recent_files", recent_files)
        except Exception as e:
            log_error(e)
    
    def save_crack_result(self):
        """保存破解结果到文件"""
        if not self.passwordEdit.text():
            self.set_status("没有可保存的破解结果", "warning")
            return
        
        try:
            # 获取当前时间作为文件名的一部分
            current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 获取文件名（如果有）
            file_name = os.path.basename(self.selected_file) if self.selected_file else "unknown"
            
            # 默认文件名
            default_filename = f"crack_result_{file_name}_{current_time}.txt"
            
            # 显示保存文件对话框
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "保存破解结果", default_filename, "文本文件 (*.txt);;所有文件 (*)"
            )
            
            if filename:
                # 准备保存内容
                content = f"=== ZIP Cracker 破解结果 ===\n\n"
                content += f"文件: {self.selected_file}\n"
                content += f"哈希值: {self.hash_value}\n"
                content += f"密码: {self.passwordEdit.text()}\n"
                
                if self.start_time:
                    elapsed_time = time.time() - self.start_time
                    content += f"破解用时: {format_duration(elapsed_time)}\n"
                
                content += f"破解时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                
                # 写入文件
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                
                self.set_status(f"破解结果已保存到 {filename}", "success")
        except Exception as e:
            self.set_status(f"保存破解结果失败: {str(e)}", "error")
            log_error(e)
    
    def copy_hash(self):
        """复制哈希值到剪贴板"""
        hash_text = self.hashValueEdit.toPlainText()
        if hash_text and hash_text != "未提取":
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(hash_text)
            self.set_status("哈希值已复制到剪贴板", "success")
    
    def copy_password(self):
        """复制密码到剪贴板"""
        if self.passwordEdit.text():
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(self.passwordEdit.text())
            self.set_status("密码已复制到剪贴板", "success")
    
    def show_dict_manager(self):
        """显示字典管理对话框"""
        # 获取发送者对象
        sender = self.sender()
        
        # 根据发送者对象确定目标字段
        if sender == self.browseDictBtn:
            target_field = "dictPathEdit"
        elif sender == self.browseDictRuleBtn:
            target_field = "dictRulePathEdit"
        elif sender == self.browseDict1Btn:
            target_field = "dict1PathEdit"
        elif sender == self.browseDict2Btn:
            target_field = "dict2PathEdit"
        elif sender == self.browseDictHybridBtn:
            target_field = "dictHybridPathEdit"
        else:
            # 使用当前模式决定目标字段
            current_mode = self.attackModeCombo.currentIndex()
            if current_mode == 0:  # 字典攻击
                target_field = "dictPathEdit"
            elif current_mode == 1:  # 组合攻击
                # 检查哪个字典为空
                if not self.dict1PathEdit.text().strip():
                    target_field = "dict1PathEdit"
                else:
                    target_field = "dict2PathEdit"
            elif current_mode == 2:  # 掩码攻击 - 不需要字典
                target_field = "dictPathEdit"  # 默认
            elif current_mode == 3:  # 混合攻击
                target_field = "dictHybridPathEdit"
            else:
                target_field = "dictPathEdit"  # 默认
        
        # 调用专用方法显示字典管理器
        self.show_dict_manager_for(target_field)
    
    def show_performance_settings(self):
        """显示性能设置对话框"""
        from zipcracker_dialogs import PerformanceSettingsDialog
        dialog = PerformanceSettingsDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            settings = dialog.get_settings()
            config.set("performance_settings", settings)
            config.save()  # 立即保存
            self.log_message("性能设置已更新", "success")
            if settings["use_gpu"]:
                self.gpuRadio.setChecked(True)
            else:
                self.cpuRadio.setChecked(True)
            self.set_status("性能设置已更新", "success")
    
    def show_history_dialog(self):
        """显示历史记录对话框"""
        # 需要导入历史记录对话框类
        from zipcracker_dialogs import HistoryDialog
        
        dialog = HistoryDialog(self, self.history_manager)
        dialog.exec_()
    
    def on_attack_mode_changed(self, index):
        # 下拉框索引 -> 堆叠卡片索引
        ATTACK_MODE_TO_STACK_INDEX = {
            0: 2,  # 字典攻击 -> dictionaryWidget
            1: 3,  # 组合攻击 -> combiWidget
            2: 0,  # 掩码攻击 -> maskWidget
            3: 4,  # 混合攻击 -> hybridWidget
            4: 5,  # 暴力攻击 -> bruteForceWidget
        }
        stack_index = ATTACK_MODE_TO_STACK_INDEX.get(index, 2)
        self.attackModeStack.setCurrentIndex(stack_index)
        
        # 记录当前模式以方便其他方法引用
        self.current_attack_mode = index
    
    def check_and_install_john(self):
        """检查并安装John the Ripper"""
        import urllib.request
        import zipfile
        import shutil
        self.set_status("正在检查John the Ripper...", "normal")
        self.log_signal.emit("检查John the Ripper安装", "info")
        # 如果已经有John the Ripper，先检查是否可用
        if self.john_path and os.path.exists(self.john_path):
            john_exe = self.find_john_executable(self.john_path)
            if john_exe and os.path.exists(john_exe):
                self.log_signal.emit(f"John the Ripper已安装: {john_exe}", "success")
                self.set_status("John the Ripper已就绪", "success")
                return True
        # 否则，提示用户是否要下载
        msg_box = QtWidgets.QMessageBox()
        msg_box.setWindowTitle("未找到John the Ripper")
        msg_box.setText("未找到John the Ripper或配置不正确，这是提取哈希必需的工具。是否自动下载并安装？")
        msg_box.setIcon(QtWidgets.QMessageBox.Question)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        msg_box.setDefaultButton(QtWidgets.QMessageBox.Yes)
        # 如果用户选择安装
        if msg_box.exec() == QtWidgets.QMessageBox.Yes:
            try:
                def download_thread():
                    try:
                        if sys.platform == "win32":
                            download_url = "https://www.openwall.com/john/k/john-1.9.0-jumbo-1-win64.zip"
                        else:
                            safe_ui_update(lambda: QtWidgets.QMessageBox.information(
                                self, 
                                "手动安装", 
                                "请通过系统的包管理器安装John the Ripper，然后在设置中配置路径。\n"
                                "例如，在Ubuntu上: sudo apt-get install john"
                            ))
                            return
                        install_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "john-1.9.0-jumbo-1-win64")
                        if os.path.exists(install_dir):
                            shutil.rmtree(install_dir)
                        temp_dir = tempfile.mkdtemp(prefix="john_download_")
                        zip_path = os.path.join(temp_dir, "john.zip")
                        self.log_signal.emit(f"开始下载John the Ripper: {download_url}", "info")
                        safe_ui_update(lambda: self.set_status("正在下载John the Ripper...", "normal"))
                        urllib.request.urlretrieve(download_url, zip_path)
                        self.log_signal.emit("下载完成，正在解压...", "info")
                        safe_ui_update(lambda: self.set_status("正在解压John the Ripper...", "normal"))
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            zip_ref.extractall(os.path.dirname(install_dir))
                        shutil.rmtree(temp_dir)
                        self.john_path = install_dir
                        config.set("john_path", install_dir)
                        john_exe = self.find_john_executable(install_dir)
                        if john_exe and os.path.exists(john_exe):
                            self.log_signal.emit(f"John the Ripper安装成功: {john_exe}", "success")
                            safe_ui_update(lambda: self.set_status("John the Ripper安装成功", "success"))
                            safe_ui_update(lambda: setattr(self.johnStatusLabel, "text", "John: 已安装"))
                            safe_ui_update(lambda: setattr(self.johnStatusLabel, "styleSheet", "color: #4CAF50;"))
                            return True
                        else:
                            self.log_signal.emit("无法找到John the Ripper可执行文件", "error")
                            safe_ui_update(lambda: self.set_status("安装John the Ripper后无法找到可执行文件", "error"))
                            return False
                    except Exception as e:
                        error_msg = str(e)
                        self.log_signal.emit(f"安装John the Ripper失败: {error_msg}", "error")
                        safe_ui_update(lambda: self.set_status(f"安装失败: {error_msg}", "error"))
                        log_error(e)
                        return False
                
                # 启动下载线程
                thread = threading.Thread(target=download_thread, daemon=True)
                thread.start()
                
                # 返回True，表示正在安装
                return True
            except Exception as e:
                self.set_status(f"安装John the Ripper出错: {str(e)}", "error")
                log_error(e)
                return False
        else:
            # 用户选择不安装
            self.set_status("未安装John the Ripper，部分功能将不可用", "warning")
            return False

    def extract_hash_async(self):
        """异步提取哈希，提取时显示进度提示并禁用相关按钮"""
        if not self.selected_file or not os.path.exists(self.selected_file):
            self.set_status("请先选择一个有效的文件", "warning")
            return
        if not self.john_path:
            self.set_status("未找到John the Ripper，请在设置中配置路径", "error")
            if not self.check_and_install_john():
                self.show_tool_paths_dialog()
                return
        # 提取哈希时，禁用"提取哈希"，启用"打开文件"，禁用"开始破解"
        self.extractHashBtn.setEnabled(True)
        self.copyHashBtn.setEnabled(False)
        self.startCrackBtn.setEnabled(False)
        self.set_status("正在提取哈希，请稍候...", "normal")
        def extract_task():
            try:
                if not os.path.exists(self.selected_file):
                    self.log_signal.emit(f"文件不存在: {self.selected_file}", "error")
                    safe_ui_update(lambda: self.set_status(f"文件不存在", "error"))
                    return
                    
                file_ext = self.file_ext.lower().lstrip('.')
                if not file_ext or file_ext not in [ext.lstrip('.') for ext in SUPPORTED_EXTS]:
                    self.log_signal.emit(f"不支持的文件类型: {file_ext}", "error")
                    safe_ui_update(lambda: self.set_status(f"不支持的文件类型: {file_ext}", "error"))
                    return
                    
                self.log_signal.emit(f"正在提取哈希，文件类型: {file_ext}", "info")
                
                # 提取哈希
                hash_value, hash_file = extract_hash_safe(
                    self.john_path, self.selected_file, file_ext
                )
                
                if hash_value:
                    # 基本清理哈希值，移除空行和前后空白
                    hash_value = hash_value.strip()
                    if "\n" in hash_value:
                        lines = [line.strip() for line in hash_value.split("\n") if line.strip()]
                        hash_value = lines[0] if lines else ""
                    
                    # 对于RAR5哈希，进行额外验证
                    if file_ext == "rar" and "$rar5$" in hash_value:
                        import re
                        match = re.search(r'(\$rar5\$[^\s]+)', hash_value)
                        if match:
                            hash_value = match.group(1)
                    
                    self.log_signal.emit(f"哈希提取成功: {hash_value[:100]}...", "success")
                    self.hash_update_signal.emit(hash_value, hash_file)
                    # 提取成功后，禁用"提取哈希"，启用"开始破解"，启用"打开文件"
                    safe_ui_update(lambda: self.copyHashBtn.setEnabled(False))
                    safe_ui_update(lambda: self.startCrackBtn.setEnabled(True))
                    safe_ui_update(lambda: self.extractHashBtn.setEnabled(True))
                else:
                    # 失败时，启用"提取哈希"，禁用"开始破解"
                    safe_ui_update(lambda: self.copyHashBtn.setEnabled(True))
                    safe_ui_update(lambda: self.startCrackBtn.setEnabled(False))
                    # 新增：弹窗提示
                    from PyQt5 import QtWidgets
                    safe_ui_update(lambda: QtWidgets.QMessageBox.critical(
                        self,
                        "哈希提取失败",
                        "无法从该压缩包中提取哈希。\n\n可能原因：\n1. 文件已损坏或不完整\n2. 不是官方压缩软件生成的加密包\n3. 文件格式不受支持\n\n请尝试用官方压缩软件重新压缩，或检查文件完整性。"
                    ))
            except Exception as e:
                error_msg = str(e)
                safe_ui_update(lambda: self.set_status(f"哈希提取出错: {error_msg}", "error"))
                self.log_signal.emit(f"提取哈希出错: {error_msg}", "error")
                log_error(e)
            finally:
                pass  # 其他按钮状态已在上面处理
        threading.Thread(target=extract_task, daemon=True).start()
    
    @QtCore.pyqtSlot(str, str)
    def update_hash_ui(self, hash_value, hash_file):
        """线程安全地更新哈希UI，分批加载哈希内容，避免卡顿
        Args:
            hash_value (str): 哈希值
            hash_file (str): 哈希文件路径
        """
        try:
            self.hash_value = hash_value
            self.hash_file = hash_file

            # 检查哈希是否有效
            if hash_value and (
                hash_value.startswith("Invalid") or 
                hash_value.startswith("Error") or 
                hash_value.startswith("Usage") or
                "Valid options" in hash_value or
                "show switch" in hash_value
            ):
                self.log_message(f"提取的内容不是有效哈希: {hash_value[:100]}", "error")
                self.set_status("哈希提取失败，获取到错误信息", "error")
                self.hashValueEdit.clear()
                self.hashValueEdit.append("提取失败：" + hash_value[:200])
                self.copyHashBtn.setEnabled(False)
                self.startCrackBtn.setEnabled(False)
                QtWidgets.QMessageBox.critical(self, "哈希格式不支持", "提取的内容不是有效哈希，或该文件类型暂不支持自动破解。请检查文件或手动处理。")
                return

            # 处理哈希值，只保留$开头的真正哈希值部分
            if "$" in hash_value:
                dollar_pos = hash_value.find("$")
                display_hash = hash_value[dollar_pos:]
            else:
                display_hash = hash_value
                
            # 针对RAR5哈希进行额外验证
            if display_hash.startswith("$rar5$"):
                # 验证格式，确保格式正确: $rar5$16$salt$iterations$iv$ct_len$ct
                import re
                rar5_pattern = r'\$rar5\$\d+\$[a-fA-F0-9]+\$\d+\$[a-fA-F0-9]+\$\d+\$[a-fA-F0-9]+'
                if not re.match(rar5_pattern, display_hash):
                    self.log_message("警告: RAR5哈希格式不标准，破解可能失败", "warning")
                    # 尝试提取符合格式的部分
                    match = re.search(r'(\$rar5\$\d+\$[a-fA-F0-9]+\$\d+\$[a-fA-F0-9]+\$\d+\$[a-fA-F0-9]+)', display_hash)
                    if match:
                        fixed_hash = match.group(1)
                        self.log_message(f"已修复RAR5哈希格式，原始长度: {len(display_hash)}, 修复后: {len(fixed_hash)}", "info")
                        display_hash = fixed_hash
                        self.hash_value = fixed_hash
                        
                        # 重新写入哈希文件
                        if self.hash_file:
                            try:
                                hash_line = self.hash_value.strip().splitlines()[0] if self.hash_value.strip() else ''
                                with open(self.hash_file, "w", encoding="utf-8") as f:
                                    f.write(hash_line + "\n")
                                self.log_message("哈希文件已更新为修复后格式", "success")
                            except Exception as e:
                                self.log_message(f"更新哈希文件失败: {str(e)}", "error")
                else:
                    self.log_message("RAR5哈希格式验证通过", "success")

            # 分批加载到QTextEdit，避免一次性渲染大量文本
            self.hashValueEdit.clear()
            lines = display_hash.splitlines()
            batch_size = 1000
            total_lines = len(lines)
            if total_lines > batch_size:
                self.hashValueEdit.append(f"[仅显示前{batch_size}行/共{total_lines}行]")
            for i in range(0, min(total_lines, batch_size)):
                self.hashValueEdit.append(lines[i])
            if total_lines > batch_size:
                self.hashValueEdit.append("...（内容过多，已截断）")

            self.copyHashBtn.setEnabled(True)
            self.startCrackBtn.setEnabled(True)
            self.set_status("哈希提取成功，可以开始破解", "success")
            print(f"UI更新成功，哈希值: {display_hash[:100]}...")

            # 新增：日志输出哈希位数和加密类型
            hash_length = len(display_hash.replace('\n', '').replace('\r', ''))
            # 自动识别加密算法
            enc_algo = "未知"
            hashcat_mode = None  # 新增：自动识别的hashcat模式编号
            if self.file_ext.lower() == "zip":
                # 1. WinZip AES (23001)
                if display_hash.startswith("$pkzip2$") and 'AES' in display_hash.upper():
                    enc_algo = "ZIP AES 加密 (WinZip AE-2)"
                    hashcat_mode = 23001
                # 2. 传统ZipCrypto (13600)
                elif display_hash.startswith("$pkzip2$"):
                    enc_algo = "ZipCrypto (传统加密)"
                    hashcat_mode = 13600
                # 3. 7-Zip (17200/11600)（极少见zip哈希会这样，通常是.7z文件）
                elif display_hash.startswith("$7z$"):
                    enc_algo = "7-Zip (AES-256)"
                    hashcat_mode = 17200  # 或11600，视实际情况
                # 4. PKZIP Master Key (20500)
                elif display_hash.startswith("$pkzip$") or ("master" in display_hash.lower()):
                    enc_algo = "PKZIP Master Key (AES/ZipCrypto)"
                    hashcat_mode = 20500
                # 5. 其他未知zip哈希
                else:
                    enc_algo = "未知ZIP加密"
                    hashcat_mode = None
            elif self.file_ext.lower() == "rar":
                if display_hash.startswith("$rar5$"):
                    enc_algo = "RAR5 (AES-256)"
                elif display_hash.startswith("$rar$"):
                    enc_algo = "RAR3 (AES-128)"
                else:
                    enc_algo = "未知RAR加密"
            elif self.file_ext.lower() == "7z":
                if display_hash.startswith("$7z$"):
                    enc_algo = "7-Zip (AES-256)"
            elif self.file_ext.lower() == "pdf":
                if display_hash.startswith("$pdf$"):
                    if '256' in display_hash:
                        enc_algo = "PDF AES-256"
                    elif '128' in display_hash:
                        enc_algo = "PDF RC4-128"
                    else:
                        enc_algo = "PDF RC4-40/未知"
            elif self.file_ext.lower() in ["doc", "docx", "xls", "xlsx", "ppt", "pptx"]:
                if display_hash.startswith("$office$"):
                    if '2013' in display_hash or '2016' in display_hash:
                        enc_algo = "Office 2013/2016+ AES-128/256"
                    elif '2007' in display_hash:
                        enc_algo = "Office 2007 AES-128"
                    elif '97' in display_hash or '2000' in display_hash or '2003' in display_hash:
                        enc_algo = "Office 97-2003 RC4"
                    else:
                        enc_algo = "Office加密(未知版本)"
            self.log_message(f"哈希长度: {hash_length} 位，加密算法: {enc_algo}", "info")

            # 自动填充掩码攻击参数区（优先用hashcat_mode，否则fallback到HASHCAT_MODE_MAP）
            try:
                from zipcracker_models import HASHCAT_MODE_MAP
                mode = None
                if hashcat_mode:
                    mode = hashcat_mode
                else:
                    mode = HASHCAT_MODE_MAP.get(self.file_ext.lower())
                if mode:
                    self.hashModeEdit.setText(str(mode))
                else:
                    self.hashModeEdit.setText("")
                self.workloadCombo.setCurrentIndex(1)  # 默认"默认"
            except Exception as e:
                self.log_message(f"自动填充参数失败: {e}", "warning")

            # 新增：zip类型弹窗提示建议用John破解
            if self.file_ext.lower() == "zip":
                def show_john_tip():
                    msg = QtWidgets.QMessageBox(self)
                    msg.setWindowTitle("ZIP破解建议")
                    msg.setText("检测到ZIP文件，建议使用John the Ripper进行专业破解。\n是否跳转到John破解界面？")
                    msg.setIcon(QtWidgets.QMessageBox.Information)
                    btn_jump = msg.addButton("跳转John破解", QtWidgets.QMessageBox.AcceptRole)
                    btn_cancel = msg.addButton("取消", QtWidgets.QMessageBox.RejectRole)
                    msg.exec_()
                    if msg.clickedButton() == btn_jump:
                        self.show_john_crack_dialog(prefill_hash=hash_value, prefill_file=self.selected_file)
                QtCore.QTimer.singleShot(200, show_john_tip)
            # 只针对.doc类型弹窗
            if self.file_ext.lower() == "doc":
                def show_doc_john_tip():
                    msg = QtWidgets.QMessageBox(self)
                    msg.setWindowTitle("DOC破解建议")
                    msg.setText("检测到DOC文档，建议使用John the Ripper进行专业破解。\n是否跳转到John破解界面？")
                    msg.setIcon(QtWidgets.QMessageBox.Information)
                    btn_jump = msg.addButton("跳转John破解", QtWidgets.QMessageBox.AcceptRole)
                    btn_cancel = msg.addButton("取消", QtWidgets.QMessageBox.RejectRole)
                    msg.exec_()
                    if msg.clickedButton() == btn_jump:
                        self.show_john_crack_dialog(prefill_hash=hash_value, prefill_file=self.selected_file)
                QtCore.QTimer.singleShot(200, show_doc_john_tip)
            # 只针对.ppt、.xls类型弹窗
            if self.file_ext.lower() in ["ppt", "xls"]:
                def show_office_john_tip():
                    msg = QtWidgets.QMessageBox(self)
                    msg.setWindowTitle("破解建议")
                    msg.setText("检测到Office文档（ppt/xls），建议使用John the Ripper进行专业破解。\n是否跳转到John破解界面？")
                    msg.setIcon(QtWidgets.QMessageBox.Information)
                    btn_jump = msg.addButton("跳转John破解", QtWidgets.QMessageBox.AcceptRole)
                    btn_cancel = msg.addButton("取消", QtWidgets.QMessageBox.RejectRole)
                    msg.exec_()
                    if msg.clickedButton() == btn_jump:
                        self.show_john_crack_dialog(prefill_hash=hash_value, prefill_file=self.selected_file)
                QtCore.QTimer.singleShot(200, show_office_john_tip)
            # 新增：7z类型弹窗提示建议用John破解
            if self.file_ext.lower() == "7z":
                def show_7z_john_tip():
                    msg = QtWidgets.QMessageBox(self)
                    msg.setWindowTitle("7z破解建议")
                    msg.setText("检测到7z文件，建议使用John the Ripper进行专业破解。\n是否跳转到John破解界面？")
                    msg.setIcon(QtWidgets.QMessageBox.Information)
                    btn_jump = msg.addButton("跳转John破解", QtWidgets.QMessageBox.AcceptRole)
                    btn_cancel = msg.addButton("取消", QtWidgets.QMessageBox.RejectRole)
                    msg.exec_()
                    if msg.clickedButton() == btn_jump:
                        self.show_john_crack_dialog(prefill_hash=hash_value, prefill_file=self.selected_file)
                QtCore.QTimer.singleShot(200, show_7z_john_tip)
        except Exception as e:
            print(f"更新哈希UI出错: {str(e)}")
            log_error(e)
    
    def on_hash_text_changed(self):
        """哈希值文本变化事件"""
        # 从QTextEdit获取文本
        text = self.hashValueEdit.toPlainText()
        
        # 启用复制按钮，如果有文本
        # 删除对原复制按钮的引用
        self.copyHashBtn.setEnabled(bool(text))
        
        # 如果用户手动输入了哈希值，将其保存
        if text:
            self.hash_value = text
            self.startCrackBtn.setEnabled(True)
        else:
            self.hash_value = ""
            self.startCrackBtn.setEnabled(False)
            
    def copy_hash(self):
        """复制哈希值到剪贴板"""
        hash_text = self.hashValueEdit.toPlainText()
        if hash_text and hash_text != "未提取":
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(hash_text)
            self.set_status("哈希值已复制到剪贴板", "success")
    
    def on_start_stop_clicked(self):
        """开始/停止破解按钮点击事件"""
        if not self.is_cracking and not self.is_paused:
            self.start_crack()
        else:
            self.stop_crack()
    
    def on_pause_resume_clicked(self):
        """暂停/继续破解按钮点击事件"""
        if self.is_cracking and not self.is_paused:
            self.pause_crack()
        elif self.is_paused:
            self.resume_crack()
    
    def start_crack(self):
        """开始破解"""
        if not self.hash_value:
            self.log_message("请先提取哈希值", "warning")
            return
        
        # 检查必要的工具
        if not self.hashcat_path:
            self.log_message("请先设置Hashcat路径", "warning")
            self.show_tool_paths_dialog()
            return
            
        # 寻找hashcat可执行文件
        hashcat_exe = self.find_hashcat_executable(self.hashcat_path)
        if not hashcat_exe or not os.path.exists(hashcat_exe):
            self.log_message("未找到Hashcat可执行文件，请重新设置路径", "error")
            self.show_tool_paths_dialog()
            return
        
        # 获取选择的攻击模式
        attack_mode = self.current_attack_mode
        
        # 构建破解参数字典
        crack_params = {}
        
        # 根据攻击模式设置参数
        if attack_mode == 0:  # 字典攻击
            crack_params["attack_mode"] = 0
            dict_path = self.dictPathEdit.text()
            if not dict_path:
                self.log_message("请先选择字典文件", "warning")
                return
            if not os.path.exists(dict_path):
                self.log_message(f"字典文件不存在: {dict_path}", "error")
                return
            crack_params["dict_path"] = dict_path
        elif attack_mode == 1:  # 组合攻击
            crack_params["attack_mode"] = 1
            dict1_path = self.dict1PathEdit.text()
            dict2_path = self.dict2PathEdit.text()
            if not dict1_path or not dict2_path:
                self.log_message("请先选择两个字典文件", "warning")
                return
            if not os.path.exists(dict1_path):
                self.log_message(f"字典文件不存在: {dict1_path}", "error")
                return
            if not os.path.exists(dict2_path):
                self.log_message(f"字典文件不存在: {dict2_path}", "error")
                return
            crack_params["dict1_path"] = dict1_path
            crack_params["dict2_path"] = dict2_path
        elif attack_mode == 2:  # 掩码攻击
            crack_params["attack_mode"] = 3  # hashcat中掩码攻击的代码是3
            mask = self.maskEdit.text()
            if not mask:
                self.log_message("请先设置掩码", "warning")
                return
            # 检查掩码格式
            if not mask.startswith("?") and not any(c in "?*[]" for c in mask):
                self.log_message("警告: 掩码格式可能不正确，一般掩码应包含?d、?l、?u等字符", "warning")
            crack_params["mask"] = mask
        elif attack_mode == 3:  # 混合攻击
            mask = self.maskHybridEdit.text()
            dict_path = self.dictHybridPathEdit.text()
            if not dict_path:
                self.log_message("请先选择字典文件", "warning")
                return
            if not os.path.exists(dict_path):
                self.log_message(f"字典文件不存在: {dict_path}", "error")
                return
            if not mask:
                self.log_message("请先设置掩码", "warning")
                return
            # 判断是否为前缀掩码或后缀掩码
            is_prefix = self.maskHybridPosCombo.currentIndex() == 1  # 索引1为"前缀"
            if is_prefix:
                crack_params["attack_mode"] = 6  # 掩码+字典
            else:
                crack_params["attack_mode"] = 7  # 字典+掩码
            crack_params["dict_path"] = dict_path
            crack_params["mask"] = mask
            # 检查掩码格式
            if not mask.startswith("?") and not any(c in "?*[]" for c in mask):
                self.log_message("警告: 掩码格式可能不正确，一般掩码应包含?d、?l、?u等字符", "warning")
        elif attack_mode == 4:  # 暴力攻击
            crack_params["attack_mode"] = 3  # hashcat掩码攻击
            min_len = self.bruteMinLen.value()
            max_len = self.bruteMaxLen.value()
            charset_idx = self.bruteCharsetCombo.currentIndex()
            if charset_idx == 0:
                charset = "?a"
            elif charset_idx == 1:
                charset = "?d"
            elif charset_idx == 2:
                charset = "?l"
            elif charset_idx == 3:
                charset = "?u"
            elif charset_idx == 4:
                charset = "?d?l"
            elif charset_idx == 5:
                charset = "?d?u"
            else:
                charset = self.bruteCustomCharset.text() or "?a"
            # 自动生成掩码
            masks = []
            for l in range(min_len, max_len+1):
                if charset.startswith("?") and len(charset) <= 4:
                    masks.append(charset * l)
                else:
                    masks.append("?1" * l)
            # 这里只用第一个长度（可扩展为多轮）
            crack_params["mask"] = masks[0]
            self.log_message(f"暴力攻击掩码: {masks[0]}")
        
        # 获取性能设置
        performance_settings = config.get("performance_settings", {})
        
        # 应用性能设置
        workload = 2  # 默认工作负载
        threads = None
        device = None
        memory_limit = None
        
        if performance_settings:
            if "workload" in performance_settings:
                workload = performance_settings["workload"]
            if "threads" in performance_settings:
                threads = performance_settings["threads"]
            if "gpu_device" in performance_settings and performance_settings["use_gpu"]:
                device = performance_settings["gpu_device"] - 1  # 减1是因为combo的第一项是CPU
                if device < 0:  # 如果选择了CPU，则设为None
                    device = None
            if "memory_limit" in performance_settings:
                memory_limit = performance_settings["memory_limit"]
        
        # 获取是否使用GPU
        use_gpu = self.gpuRadio.isChecked()
        
        # 检测是否是RAR5格式，需要特殊提醒
        is_rar5 = self.file_ext.lower() == "rar" and "$rar5$" in self.hash_value
        if is_rar5 and crack_params.get("attack_mode") == 3:
            self.log_message("注意: RAR5掩码攻击性能较低，可能需要较长时间", "info")
        
        # 获取session名
        import time
        self.hashcat_session_name = f"zipcracker_{int(time.time())}"
        
        # 创建Hashcat破解线程
        # 自动修复：根据文件类型选择正确的 hashcat 模式号，未识别类型弹窗报错
        hash_mode = HASHCAT_MODE_MAP.get(self.file_ext)
        if not hash_mode:
            QtWidgets.QMessageBox.critical(self, "不支持的文件类型", f"未能识别的文件类型: {self.file_ext}\n无法自动选择 hashcat 模式号，请检查文件扩展名或手动配置。")
            self.set_status(f"不支持的文件类型: {self.file_ext}", "error")
            return
        # 新增：日志显示当前使用的哈希类型编号
        self.log_message(f"当前使用的哈希类型编号: -m {hash_mode}", "info")
        self.hashcat_thread = HashcatThread(
            hashcat_path=hashcat_exe,  # 使用找到的可执行文件路径
            hash_value=self.hash_value,
            hash_mode=hash_mode,  # 自动选择的模式号
            attack_mode=crack_params.get("attack_mode", 0),
            dict_path=crack_params.get("dict_path", ""),
            rule_path=crack_params.get("rule_path", ""),
            mask=crack_params.get("mask", ""),
            dict1_path=crack_params.get("dict1_path", ""),
            dict2_path=crack_params.get("dict2_path", ""),
            use_gpu=use_gpu,
            workload=workload,
            threads=threads,
            device=device,
            memory_limit=memory_limit,
            cwd=os.path.dirname(hashcat_exe),  # 设置工作目录为hashcat可执行文件所在目录
            session=self.hashcat_session_name  # 新增session参数
        )
        
        # 连接信号
        self.hashcat_thread.log_signal.connect(self.log_message)
        self.hashcat_thread.status_signal.connect(self.set_status)
        # 移除进度条相关的信号连接
        self.hashcat_thread.finished_signal.connect(self.on_crack_finished)
        
        # 记录开始时间
        self.start_time = time.time()
        
        # 更新UI状态
        self.is_cracking = True
        self.is_paused = False
        self.startCrackBtn.setText("停止破解")
        self.startCrackBtn.setEnabled(True)
        self.pauseResumeBtn.setText("暂停破解")
        self.pauseResumeBtn.setEnabled(True)
        self.timer.start(1000)
        self.crackTimeLabel.setText("破解时间: 00:00:00")
        
        # 添加任务
        self.task_manager.add_task(self.hashcat_thread)
        
        # 记录日志
        attack_mode_names = ["字典攻击", "字典+规则", "掩码攻击", "混合攻击"]
        attack_mode_index = 0  # 默认为字典攻击
        
        # 映射攻击模式到日志显示名称的索引
        if crack_params.get("attack_mode") == 0 and crack_params.get("rule_path"):
            attack_mode_index = 1  # 字典+规则
        elif crack_params.get("attack_mode") == 3:
            attack_mode_index = 2  # 掩码攻击
        elif crack_params.get("attack_mode") in [6, 7]:
            attack_mode_index = 3  # 混合攻击
            
        self.log_signal.emit(f"开始破解: {attack_mode_names[attack_mode_index]}", "info")
        
        if use_gpu:
            self.log_message("使用GPU引擎")
        else:
            self.log_message("使用CPU引擎")
        
        # 记录性能设置日志
        if workload != 2:
            workload_names = ["", "低负载", "标准负载", "高负载", "极高负载"]
            self.log_message(f"工作负载: {workload_names[workload]}")
        if threads:
            self.log_message(f"线程数: {threads}")
        if device is not None:
            self.log_message(f"使用设备: {device}")
        if memory_limit:
            self.log_message(f"内存限制: {memory_limit}")
        
        # 启动定时器
        self.timer.start(1000)
        
        # 设置状态
        self.set_status("正在破解中...", "normal")
        
        # 启动 John 实时进度刷新线程
        self.john_status_stop = threading.Event()
        session_name = getattr(self, 'john_session_name', None) or getattr(self, 'hashcat_session_name', None) or 'zipcracker_session'
        john_exe = self.find_john_executable(self.john_path)
        def status_worker():
            while not self.john_status_stop.is_set():
                try:
                    result = subprocess.run(
                        [john_exe, f"--status={session_name}"],
                        capture_output=True, text=True, timeout=5
                    )
                    status = result.stdout.strip()
                    if status:
                        self.log_message("[进度] " + status.splitlines()[-1])
                except Exception:
                    pass
                time.sleep(2)
        self.john_status_thread = threading.Thread(target=status_worker, daemon=True)
        self.john_status_thread.start()
    
    def pause_crack(self):
        """暂停破解（kill进程，保留session）"""
        if self.is_cracking and self.hashcat_session_name:
            self.task_manager.stop_all_tasks()
            self.is_cracking = False
            self.is_paused = True
            self.startCrackBtn.setText("停止破解")
            self.startCrackBtn.setEnabled(True)
            self.pauseResumeBtn.setText("继续破解")
            self.pauseResumeBtn.setEnabled(True)
            self.set_status("已暂停，可继续破解", "info")
            self.log_message("破解已暂停，可点击继续破解", "info")
            # 新增：检测 .restore 文件并刷新保存破解进度按钮
            import os, time
            hashcat_exe = self.find_hashcat_executable(self.hashcat_path)
            restore_file = os.path.join(os.path.dirname(hashcat_exe), f"{self.hashcat_session_name}.restore")
            for _ in range(10):  # 最多等1秒
                if os.path.exists(restore_file):
                    break
                time.sleep(0.1)
            # 刷新文件菜单，确保保存破解进度按钮可用
            if hasattr(self, 'show_file_menu'):
                self.show_file_menu()
    
    def resume_crack(self):
        """继续破解（用--restore恢复）"""
        if self.is_paused and self.hashcat_session_name:
            hashcat_exe = self.find_hashcat_executable(self.hashcat_path)
            if not hashcat_exe or not os.path.exists(hashcat_exe):
                self.log_message("未找到Hashcat可执行文件，请重新设置路径", "error")
                self.show_tool_paths_dialog()
                return
            # 继续用restore参数启动
            from zipcracker_models import HashcatThread
            self.log_message(f"[恢复] hashcat_exe: {hashcat_exe}")
            self.log_message(f"[恢复] session: {self.hashcat_session_name}")
            restore_file = os.path.join(os.path.dirname(hashcat_exe), f"{self.hashcat_session_name}.restore")
            self.log_message(f"[恢复] restore文件: {restore_file}")
            self.hashcat_thread = HashcatThread(
                hashcat_path=hashcat_exe,
                hash_value=self.hash_value,
                hash_mode=None,  # restore模式无需指定
                attack_mode=None,
                cwd=os.path.dirname(hashcat_exe),
                session=self.hashcat_session_name,
                restore=True
            )
            self.hashcat_thread.log_signal.connect(self.log_message)
            self.hashcat_thread.status_signal.connect(self.set_status)
            self.hashcat_thread.finished_signal.connect(self.on_crack_finished)
            self.start_time = time.time()
            self.is_cracking = True
            self.is_paused = False
            self.startCrackBtn.setText("停止破解")
            self.startCrackBtn.setEnabled(True)
            self.pauseResumeBtn.setText("暂停破解")
            self.pauseResumeBtn.setEnabled(True)
            self.timer.start(1000)
            self.set_status("正在继续破解...", "normal")
            self.log_message("已恢复破解进度，继续破解", "info")
            # 新增：3秒内无进程ID日志则自动提示
            def check_restore_started():
                import time
                for _ in range(30):  # 最多等3秒
                    time.sleep(0.1)
                    if hasattr(self.hashcat_thread, 'process') and self.hashcat_thread.process is not None:
                        if self.hashcat_thread.process.pid:
                            return  # 已启动
                # 检查日志内容
                if not any("进程ID" in l for l in getattr(self.hashcat_thread, 'cmd_output', [])):
                    QtWidgets.QMessageBox.critical(self, "恢复破解失败", "未能成功恢复破解进度，可能restore文件不匹配、已损坏或环境不一致。请检查restore文件和参数。")
                    self.set_status("恢复破解失败", "error")
                    self.is_cracking = False
                    self.is_paused = False
                    self.startCrackBtn.setText("开始破解")
                    self.startCrackBtn.setEnabled(True)
                    self.pauseResumeBtn.setText("暂停破解")
                    self.pauseResumeBtn.setEnabled(False)
            import threading
            threading.Thread(target=check_restore_started, daemon=True).start()
    
    def stop_crack(self):
        """停止破解"""
        if self.is_cracking or self.is_paused:
            self.task_manager.stop_all_tasks()
        self.is_cracking = False
        self.is_paused = False
        self.startCrackBtn.setText("开始破解")
        self.startCrackBtn.setEnabled(True)
        self.pauseResumeBtn.setText("暂停破解")
        self.pauseResumeBtn.setEnabled(False)
    
    def on_status_label_clicked(self):
        if self.statusLabel.text() == "检测":
            # 自动递归查找当前目录及子目录的john.exe和hashcat.exe
            import glob, os
            base_dir = os.getcwd()
            john_candidates = glob.glob(os.path.join(base_dir, '**', 'john.exe'), recursive=True)
            hashcat_candidates = glob.glob(os.path.join(base_dir, '**', 'hashcat.exe'), recursive=True)
            updated = False
            if john_candidates:
                # 取第一个找到的john.exe的上级目录（如run的上一级）
                john_dir = os.path.dirname(john_candidates[0])
                # 如果是run目录，取上一级
                if os.path.basename(john_dir).lower() == 'run':
                    john_dir = os.path.dirname(john_dir)
                self.john_path = john_dir
                config.set("john_path", john_dir)
                updated = True
                self.log_message(f"自动检测到John路径: {john_dir}", "success")
            if hashcat_candidates:
                hashcat_dir = os.path.dirname(hashcat_candidates[0])
                self.hashcat_path = hashcat_candidates[0]
                config.set("hashcat_path", self.hashcat_path)
                updated = True
                self.log_message(f"自动检测到Hashcat路径: {self.hashcat_path}", "success")
            if updated:
                self.force_detect_tools()
            else:
                self.set_status("未在当前目录及子目录找到工具", "warning")

    def download_john(self):
        show_error_dialog(self, "请访问 https://www.openwall.com/john/ 下载 John the Ripper，并在设置中配置路径。", title="下载John the Ripper")

    def download_hashcat(self):
        show_error_dialog(self, "请访问 https://hashcat.net/hashcat/ 下载 Hashcat，并在设置中配置路径。", title="下载Hashcat")

    def on_fix_engine(self):
        """修复引擎按钮点击事件，自动修复所有工具路径并检测依赖"""
        # 自动修复所有工具路径
        import glob, os, webbrowser, shutil, subprocess
        from PyQt5 import QtWidgets
        from zipcracker_config import config
        base_dir = os.getcwd()
        # 1. 查找 john.exe
        john_candidates = glob.glob(os.path.join(base_dir, '**', 'john.exe'), recursive=True)
        if john_candidates:
            john_dir = os.path.dirname(john_candidates[0])
            if os.path.basename(john_dir).lower() == 'run':
                john_dir = os.path.dirname(john_dir)
            self.john_path = john_dir
            config.set("john_path", john_dir)
            self.log_message(f"自动修复: 检测到John路径: {john_dir}", "success")
        # 2. 查找 hashcat.exe
        hashcat_candidates = glob.glob(os.path.join(base_dir, '**', 'hashcat.exe'), recursive=True)
        if hashcat_candidates:
            hashcat_path = hashcat_candidates[0]
            self.hashcat_path = hashcat_path
            config.set("hashcat_path", hashcat_path)
            self.log_message(f"自动修复: 检测到Hashcat路径: {hashcat_path}", "success")
        # 3. 查找 OpenCL
        opencl_candidates = glob.glob(os.path.join(base_dir, '**', 'OpenCL*'), recursive=True)
        if opencl_candidates:
            opencl_dir = os.path.dirname(opencl_candidates[0])
            self.opencl_path = opencl_dir
            config.set("opencl_path", opencl_dir)
            self.log_message(f"自动修复: 检测到OpenCL路径: {opencl_dir}", "success")
        # 4. 查找 perl.exe
        perl_candidates = glob.glob(os.path.join(base_dir, '**', 'perl.exe'), recursive=True)
        if perl_candidates:
            perl_path = perl_candidates[0]
            self.perl_path = perl_path
            config.set("perl_path", perl_path)
            self.log_message(f"自动修复: 检测到Perl路径: {perl_path}", "success")
        # 刷新UI
        self.force_detect_tools()
        # 继续原有OpenCL/Perl检测逻辑
        hashcat_path = config.get("hashcat_path", "")
        hashcat_dir = os.path.dirname(hashcat_path) if hashcat_path else os.getcwd()
        opencl_path = os.path.join(hashcat_dir, "OpenCL")
        # 1. 检查OpenCL
        if os.path.exists(opencl_path):
            QtWidgets.QMessageBox.information(self, "修复结果", "OpenCL 文件夹已存在，无需修复。\n如仍有问题请尝试安装OpenCL驱动。")
        else:
            reply = QtWidgets.QMessageBox.question(
                self, "修复引擎",
                "未检测到 OpenCL 文件夹。\n是否需要自动打开OpenCL驱动下载页面？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                webbrowser.open("https://www.intel.com/content/www/us/en/developer/tools/opencl/opencl-drivers.html")
            else:
                QtWidgets.QMessageBox.information(self, "手动修复", "请手动安装 OpenCL 运行库或复制 OpenCL 文件夹到 hashcat 目录。")
        # 2. 检查Perl环境
        perl_ok = False
        perl_path = getattr(self, "perl_path", None) or shutil.which("perl") or shutil.which("perl.exe")
        if perl_path:
            # 进一步检测perl是否可用
            try:
                result = subprocess.run([perl_path, "-v"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and ("perl" in result.stdout.lower() or "perl" in result.stderr.lower()):
                    perl_ok = True
            except Exception:
                pass
        if perl_ok:
            QtWidgets.QMessageBox.information(self, "Perl环境检测", f"Perl环境已就绪 (检测到: {perl_path})\n无需修复。\n如仍有问题请尝试重装Perl。")
        else:
            reply = QtWidgets.QMessageBox.question(
                self, "Perl环境缺失",
                "未检测到可用的Perl环境，部分John the Ripper辅助工具（如rar2john.pl/pdf2john.pl等）需要Perl支持。\n\n是否打开Perl官方下载页面？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                # 推荐Strawberry Perl（更适合Windows）
                webbrowser.open("https://strawberryperl.com/")
            else:
                QtWidgets.QMessageBox.information(self, "手动修复", "请手动下载安装Strawberry Perl或ActivePerl，并确保perl.exe已加入系统PATH环境变量。\n推荐：https://strawberryperl.com/")

    def get_gpu_info(self):
        import subprocess
        try:
            result = subprocess.run(
                ['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                capture_output=True, text=True, encoding='utf-8'
            )
            lines = result.stdout.strip().split('\n')
            gpus = [line.strip() for line in lines[1:] if line.strip()]
            return ' | '.join(gpus) if gpus else '未知显卡'
        except Exception:
            return '未知显卡'

    def kill_hashcat_processes(self):
        """结束所有hashcat.exe进程（跨平台）"""
        import subprocess
        import sys
        try:
            if sys.platform == "win32":
                subprocess.call('taskkill /F /IM hashcat.exe', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.call('pkill -f hashcat', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.log_message(f"结束hashcat进程失败: {e}", "warning")

    def save_crack_progress(self):
        """保存当前破解进度（session .restore文件和参数）"""
        if not self.hashcat_session_name:
            QtWidgets.QMessageBox.warning(self, "无法保存", "当前没有正在进行的破解任务或未分配session名。")
            return
        import os, shutil
        session_name = self.hashcat_session_name
        hashcat_dir = os.path.dirname(self.find_hashcat_executable(self.hashcat_path))
        restore_file = os.path.join(hashcat_dir, f"{session_name}.restore")
        if not os.path.exists(restore_file):
            QtWidgets.QMessageBox.warning(self, "无法保存", f"未找到session进度文件: {restore_file}")
            return
        # 记忆保存目录
        from zipcracker_config import config
        last_dir = config.get("last_progress_save_dir", "")
        if not last_dir or not os.path.exists(last_dir):
            last_dir = os.path.expanduser("~")
        save_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "选择保存破解进度的文件夹", last_dir)
        if not save_dir:
            return
        # 记忆本次保存目录
        config.set("last_progress_save_dir", save_dir)
        try:
            shutil.copy2(restore_file, os.path.join(save_dir, f"{session_name}.restore"))
            # 可选：保存参数信息
            param_file = os.path.join(save_dir, f"{session_name}_params.txt")
            with open(param_file, "w", encoding="utf-8") as f:
                f.write(f"hashcat_path={self.hashcat_path}\n")
                f.write(f"hash_file={self.hash_file}\n")
                f.write(f"hash_value={self.hash_value}\n")
                f.write(f"session={session_name}\n")
                f.write(f"file_ext={self.file_ext}\n")
            QtWidgets.QMessageBox.information(self, "保存成功", f"破解进度已保存到: {save_dir}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "保存失败", f"保存进度失败: {e}")
    
    def load_crack_progress(self):
        """加载破解进度（选择.restore文件并恢复session）"""
        import os
        from zipcracker_config import config
        last_dir = config.get("last_progress_save_dir", "")
        if not last_dir or not os.path.exists(last_dir):
            last_dir = os.path.expanduser("~")
        restore_file, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择破解进度文件", last_dir, "Hashcat进度文件 (*.restore);;所有文件 (*)")
        if not restore_file:
            return
        # 记忆本次打开目录
        config.set("last_progress_save_dir", os.path.dirname(restore_file))
        session_name = os.path.splitext(os.path.basename(restore_file))[0]
        hashcat_dir = os.path.dirname(self.find_hashcat_executable(self.hashcat_path))
        # 复制到hashcat目录
        try:
            import shutil
            shutil.copy2(restore_file, os.path.join(hashcat_dir, os.path.basename(restore_file)))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "加载失败", f"复制进度文件失败: {e}")
            return
        self.hashcat_session_name = session_name
        self.is_paused = True
        self.resume_crack()
        QtWidgets.QMessageBox.information(self, "加载成功", f"已加载破解进度并恢复session: {session_name}")

    def log_error_to_file(self, error: Exception):
        """将异常写入日志文件"""
        import traceback
        with open('error.log', 'a', encoding='utf-8') as f:
            f.write(traceback.format_exc())

    def auto_find_and_detect_tools(self):
        """自动查找工具路径并检测"""
        import glob, os
        base_dir = os.getcwd()
        john_candidates = glob.glob(os.path.join(base_dir, '**', 'john.exe'), recursive=True)
        hashcat_candidates = glob.glob(os.path.join(base_dir, '**', 'hashcat.exe'), recursive=True)
        updated = False
        if john_candidates:
            john_dir = os.path.dirname(john_candidates[0])
            if os.path.basename(john_dir).lower() == 'run':
                john_dir = os.path.dirname(john_dir)
            self.john_path = john_dir
            config.set("john_path", john_dir)
            updated = True
            self.log_message(f"自动检测到John路径: {john_dir}", "success")
        if hashcat_candidates:
            hashcat_path = hashcat_candidates[0]
            self.hashcat_path = hashcat_path
            config.set("hashcat_path", hashcat_path)
            updated = True
            self.log_message(f"自动检测到Hashcat路径: {hashcat_path}", "success")
        if updated:
            self.force_detect_tools()
        else:
            self.set_status("未在当前目录及子目录找到工具", "warning")

    def detect_gpus(self):
        self.device_combo.clear()
        self.device_combo.addItem("CPU (不使用GPU)")
        try:
            import subprocess, re
            from zipcracker_config import config
            hashcat_path = config.get("hashcat_path", "")
            if hashcat_path and os.path.exists(hashcat_path):
                process = subprocess.Popen(
                    [hashcat_path, "--benchmark", "--machine-readable"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                stdout, stderr = process.communicate(timeout=10)
                devices = []
                for line in stdout.split("\n"):
                    if "DEVICE_NAME" in line:
                        match = re.search(r'DEVICE_NAME:(.*?)(?:,|$)', line)
                        if match:
                            device_name = match.group(1).strip()
                            devices.append(device_name)
                for device in devices:
                    self.device_combo.addItem(device)
                if devices:
                    self.device_combo.setCurrentIndex(1)
            else:
                self.device_combo.addItem("NVIDIA GPU")
                self.device_combo.addItem("AMD GPU")
        except:
            self.device_combo.addItem("NVIDIA GPU")
            self.device_combo.addItem("AMD GPU")

    def show_mask_gen(self):
        """显示掩码生成器，并标记是从哪个按钮调用的"""
        # 获取发送者
        sender = self.sender()
        # 导入掩码生成器对话框
        from zipcracker_dialogs import MaskGeneratorDialog
        dialog = MaskGeneratorDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            mask = dialog.get_mask()
            # 根据调用的按钮决定更新哪个输入框
            if sender == self.maskGenBtn:
                self.maskEdit.setText(mask)
            elif sender == self.maskHybridGenBtn:
                self.maskHybridEdit.setText(mask)
            else:
                # 默认根据当前模式决定
                if self.current_attack_mode == 2:  # 掩码攻击
                    self.maskEdit.setText(mask)
                elif self.current_attack_mode == 3:  # 混合攻击
                    self.maskHybridEdit.setText(mask)
                else:
                    # 如果在其他模式下，优先使用掩码攻击
                    self.maskEdit.setText(mask)
            if mask:
                self.set_status(f"掩码已设置: {mask}", "success")

    def browse_rule_file(self):
        """浏览规则文件"""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择规则文件", "", "文本文件 (*.rule);;所有文件 (*)"
        )
        if filename:
            self.rulePathEdit.setText(filename)

    def browse_dict1_file(self):
        """浏览第一个字典文件"""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择第一个字典文件", "", "文本文件 (*.txt *.dict);;所有文件 (*)"
        )
        if filename:
            self.dict1PathEdit.setText(filename)

    def browse_dict2_file(self):
        """浏览第二个字典文件"""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择第二个字典文件", "", "文本文件 (*.txt *.dict);;所有文件 (*)"
        )
        if filename:
            self.dict2PathEdit.setText(filename)

    def browse_dict_hybrid_file(self):
        """浏览混合攻击字典文件"""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择混合攻击字典文件", "", "文本文件 (*.txt *.dict);;所有文件 (*)"
        )
        if filename:
            self.dictHybridPathEdit.setText(filename)

    def force_detect_tools(self):
        """强制检测工具路径并刷新UI状态"""
        self.detect_tools_async()

    def on_crack_finished(self, result_dict):
        """
        破解线程完成时的回调
        result_dict: 包含 success, password, error, speed 等信息
        """
        self.is_cracking = False
        self.is_paused = False
        self.startCrackBtn.setText("开始破解")
        self.startCrackBtn.setEnabled(True)
        self.pauseResumeBtn.setText("暂停破解")
        self.pauseResumeBtn.setEnabled(False)
        import logging
        from PyQt5 import QtWidgets
        logger = logging.getLogger("zipcracker")
        file_path = getattr(self, 'selected_file', None) or getattr(self, 'current_file', None) or ''
        if result_dict.get('success', False):
            password = result_dict.get('password', '')
            self.passwordEdit.setText(password)
            self.passwordEdit.setStyleSheet("color: #00FF00; background-color: #1E1E1E;")
            self.copyPasswordBtn.setEnabled(bool(password))
            msg = f"破解成功！\n\n文件: {file_path}\n密码: {password}"
            self.log_message(msg, "success")
            logger.info(msg)
            QtWidgets.QMessageBox.information(self, "破解成功", msg)
        else:
            error = result_dict.get('error', '未找到密码')
            suggest = "1. 检查掩码/字典是否覆盖密码范围\n2. 确认哈希格式和加密类型\n3. 可尝试更换攻击方式或工具"
            msg = f"破解失败！\n\n文件: {file_path}\n原因: {error}\n\n建议:\n{suggest}"
            self.log_message(msg, "error")
            logger.error(msg)
            QtWidgets.QMessageBox.warning(self, "破解失败", msg)
        if hasattr(self, 'john_status_stop'):
            self.john_status_stop.set()

    def show_rule_editor(self):
        from PyQt5 import QtWidgets, QtGui, QtCore
        import os
        class RuleTab(QtWidgets.QWidget):
            def __init__(self, filename=None, content="", parent=None):
                super().__init__(parent)
                layout = QtWidgets.QVBoxLayout(self)
                # 代码编辑器（带行号）
                self.editor = QtWidgets.QPlainTextEdit()
                self.editor.setFont(QtGui.QFont("Consolas", 11))
                self.editor.setPlainText(content)
                layout.addWidget(self.editor)
                self.filename = filename
                self.saved = True
                self.editor.textChanged.connect(self.on_text_changed)
            def on_text_changed(self):
                self.saved = False
        class RuleEditorPro(QtWidgets.QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("专业密码规则编辑器")
                self.resize(900, 600)
                mainLayout = QtWidgets.QVBoxLayout(self)
                # 顶部说明
                desc = QtWidgets.QLabel("专业规则编辑器，支持多标签、批量测试、规则片段库、语法高亮。每行一条规则，语法兼容hashcat。")
                desc.setStyleSheet("color: #CCCCCC; font-size: 12px;")
                mainLayout.addWidget(desc)
                # 主体分栏
                bodyLayout = QtWidgets.QHBoxLayout()
                # 左侧：文件管理
                filePanel = QtWidgets.QVBoxLayout()
                self.recentList = QtWidgets.QListWidget()
                self.recentList.setFixedWidth(160)
                self.recentList.addItem("最近文件（点击打开）")
                filePanel.addWidget(self.recentList)
                btnRow = QtWidgets.QHBoxLayout()
                self.newBtn = QtWidgets.QPushButton("新建")
                self.openBtn = QtWidgets.QPushButton("打开")
                self.saveBtn = QtWidgets.QPushButton("保存")
                self.saveAsBtn = QtWidgets.QPushButton("另存为")
                btnRow.addWidget(self.newBtn)
                btnRow.addWidget(self.openBtn)
                btnRow.addWidget(self.saveBtn)
                btnRow.addWidget(self.saveAsBtn)
                filePanel.addLayout(btnRow)
                bodyLayout.addLayout(filePanel)
                # 中部：多标签编辑区
                self.tabWidget = QtWidgets.QTabWidget()
                self.tabWidget.setTabsClosable(True)
                self.tabWidget.tabCloseRequested.connect(self.close_tab)
                bodyLayout.addWidget(self.tabWidget, 1)
                # 右侧：规则片段库
                rulePanel = QtWidgets.QVBoxLayout()
                rulePanel.addWidget(QtWidgets.QLabel("常用规则片段"))
                self.ruleList = QtWidgets.QListWidget()
                self.ruleList.addItems([
                    ": (原文)",
                    "l (小写)",
                    "u (大写)",
                    "c (首字母大写)",
                    "d (去首字母)",
                    "D (去尾字母)",
                    "$1 (末尾加1)",
                    "^A (前加A)",
                    "$! (末尾加!)",
                    "s@a (a替换为@)",
                    "r (反转)",
                    "..."
                ])
                rulePanel.addWidget(self.ruleList)
                self.insertRuleBtn = QtWidgets.QPushButton("插入到当前")
                rulePanel.addWidget(self.insertRuleBtn)
                bodyLayout.addLayout(rulePanel)
                mainLayout.addLayout(bodyLayout, 1)
                # 底部：批量测试区
                testGroup = QtWidgets.QGroupBox("规则批量测试")
                testLayout = QtWidgets.QHBoxLayout(testGroup)
                self.testInput = QtWidgets.QPlainTextEdit()
                self.testInput.setPlaceholderText("每行一个密码")
                self.testInput.setFixedHeight(60)
                self.testResult = QtWidgets.QPlainTextEdit()
                self.testResult.setReadOnly(True)
                self.testResult.setFixedHeight(60)
                testLayout.addWidget(self.testInput)
                testLayout.addWidget(self.testResult)
                self.testBtn = QtWidgets.QPushButton("测试当前规则")
                testLayout.addWidget(self.testBtn)
                mainLayout.addWidget(testGroup)
                # 状态栏
                self.statusBar = QtWidgets.QLabel("就绪")
                mainLayout.addWidget(self.statusBar)
                # 事件绑定
                self.newBtn.clicked.connect(self.new_tab)
                self.openBtn.clicked.connect(self.open_rule)
                self.saveBtn.clicked.connect(self.save_rule)
                self.saveAsBtn.clicked.connect(self.save_rule_as)
                self.insertRuleBtn.clicked.connect(self.insert_rule)
                self.testBtn.clicked.connect(self.test_rule)
                self.recentList.itemClicked.connect(self.open_recent)
                # 初始化一个空标签
                self.new_tab()
            def new_tab(self):
                tab = RuleTab()
                idx = self.tabWidget.addTab(tab, "未命名.rule")
                self.tabWidget.setCurrentIndex(idx)
            def close_tab(self, idx):
                self.tabWidget.removeTab(idx)
            def open_rule(self):
                filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "打开规则文件", "", "规则文件 (*.rule);;所有文件 (*)")
                if filename:
                    with open(filename, "r", encoding="utf-8") as f:
                        content = f.read()
                    tab = RuleTab(filename, content)
                    idx = self.tabWidget.addTab(tab, os.path.basename(filename))
                    self.tabWidget.setCurrentIndex(idx)
            def save_rule(self):
                tab = self.tabWidget.currentWidget()
                if tab.filename:
                    with open(tab.filename, "w", encoding="utf-8") as f:
                        f.write(tab.editor.toPlainText())
                    tab.saved = True
                    self.statusBar.setText(f"已保存: {tab.filename}")
                else:
                    self.save_rule_as()
            def save_rule_as(self):
                tab = self.tabWidget.currentWidget()
                filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存规则文件", "", "规则文件 (*.rule);;所有文件 (*)")
                if filename:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(tab.editor.toPlainText())
                    tab.filename = filename
                    tab.saved = True
                    self.tabWidget.setTabText(self.tabWidget.currentIndex(), os.path.basename(filename))
                    self.statusBar.setText(f"已保存: {filename}")
            def insert_rule(self):
                tab = self.tabWidget.currentWidget()
                rule = self.ruleList.currentItem().text().split()[0]
                cursor = tab.editor.textCursor()
                cursor.insertText(rule + "\n")
                tab.editor.setTextCursor(cursor)
                tab.editor.setFocus()
            def test_rule(self):
                tab = self.tabWidget.currentWidget()
                rules = tab.editor.toPlainText().splitlines()
                test_words = self.testInput.toPlainText().splitlines()
                result_lines = []
                for word in test_words:
                    for rule in rules:
                        result_lines.append(self.apply_rule(rule, word))
                self.testResult.setPlainText("\n".join(result_lines))
            def apply_rule(self, rule, word):
                try:
                    w = word
                    for op in rule:
                        if op == ':':
                            pass
                        elif op == 'l':
                            w = w.lower()
                        elif op == 'u':
                            w = w.upper()
                        elif op == 'c':
                            w = w.capitalize()
                        elif op == 'd':
                            w = w[1:]
                        elif op == 'D':
                            w = w[:-1]
                        elif op == '$':
                            idx = rule.find('$')
                            if idx != -1 and idx+1 < len(rule):
                                w = w + rule[idx+1]
                        elif op == '^':
                            idx = rule.find('^')
                            if idx != -1 and idx+1 < len(rule):
                                w = rule[idx+1] + w
                    return w
                except Exception as e:
                    return f"规则解析异常: {e}"
            def open_recent(self, item):
                # 预留：可实现最近文件管理
                pass
        dialog = RuleEditorPro(self)
        dialog.exec_()

    def show_dict_merge(self):
        from zipcracker_dialogs import DictMergeDialog
        dialog = DictMergeDialog(self)
        dialog.exec_()

    def show_dict_manager_for(self, target_field):
        from zipcracker_dialogs import DictManagerDialog
        dialog = DictManagerDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected_path = dialog.get_selected_dict_path()
            if selected_path and hasattr(self, target_field):
                getattr(self, target_field).setText(selected_path)

    def on_gpu_label_clicked(self, event):
        """点击显卡标签，弹窗显示OpenCL平台和设备信息"""
        try:
            import pyopencl as cl
            platforms = cl.get_platforms()
            if not platforms:
                QtWidgets.QMessageBox.warning(self, "OpenCL检测", "未检测到任何OpenCL平台。")
                return
            info_lines = []
            for p in platforms:
                info_lines.append(f"平台: {p.name} ({p.vendor})")
                devices = p.get_devices()
                for d in devices:
                    info_lines.append(f"  设备: {d.name} ({cl.device_type.to_string(d.type)})")
            preview = "\n".join(info_lines[:20])
            if len(info_lines) > 20:
                preview += "\n... (更多内容请在终端运行pyopencl查看)"
            QtWidgets.QMessageBox.information(self, "OpenCL信息", preview)
        except ImportError:
            QtWidgets.QMessageBox.warning(self, "OpenCL检测", "未安装pyopencl库，无法检测OpenCL信息。\n请先安装: pip install pyopencl")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "OpenCL检测", f"pyopencl检测异常: {e}")

def cleanup_all_cracker_processes():
    import subprocess, sys
    try:
        if sys.platform == "win32":
            subprocess.call('taskkill /F /IM hashcat.exe', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call('taskkill /F /IM john.exe', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.call('pkill -f hashcat', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call('pkill -f john', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
atexit.register(cleanup_all_cracker_processes)

def run_app():
    """运行应用程序"""
    app = QtWidgets.QApplication(sys.argv)
    
    # 设置应用程序信息
    app.setApplicationName("ZIP Cracker")
    app.setApplicationVersion("4.0.5")
    app.setOrganizationName("ZIPCracker Team")
    
    # 设置应用程序图标
    app_icon = QtGui.QIcon()
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
    if os.path.exists(icon_path):
        app_icon.addFile(icon_path)
        app.setWindowIcon(app_icon)
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    # 启动应用程序
    sys.exit(app.exec_())

if __name__ == "__main__":
    init_logging()  # 初始化日志系统
    try:
        print("Starting application...")
        run_app()
    except Exception as e:
        error_msg = f"发生未处理的异常: {str(e)}\n\n{traceback.format_exc()}"
        show_error_dialog(None, "程序发生致命错误，已自动记录日志。", detail=error_msg, suggestion="请检查依赖环境、日志文件，或联系开发者反馈。")
        sys.exit(1) 
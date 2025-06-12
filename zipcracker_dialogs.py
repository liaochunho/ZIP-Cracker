#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ZIP Cracker - 对话框模块
包含所有自定义对话框
"""

import os
import sys
import time
import datetime
import threading
import tempfile
import subprocess
import webbrowser
import requests
import glob
import logging
import urllib.request

from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt

from zipcracker_ui import BaseDialog
from zipcracker_models import DownloadThread, DownloadThreadWithRetry
from zipcracker_utils import log_error, run_cmd_with_output, format_duration, show_error_dialog, show_info_dialog
from zipcracker_config import config

class ToolPathsDialog(BaseDialog):
    """工具路径设置对话框"""
    
    def __init__(self, parent=None, john_path="", hashcat_path="", opencl_path="", perl_path=""):
        """初始化对话框
        
        Args:
            parent: 父窗口
            john_path (str): John the Ripper路径
            hashcat_path (str): Hashcat路径
            opencl_path (str): OpenCL路径
            perl_path (str): Perl路径
        """
        super().__init__(parent)
        
        # 设置窗口属性
        self.setWindowTitle("工具路径设置")
        self.setMinimumWidth(450)
        
        # John the Ripper路径
        self.john_path = john_path
        
        # Hashcat路径
        self.hashcat_path = hashcat_path
        
        # OpenCL路径
        from zipcracker_config import config
        self.opencl_path = opencl_path or config.get("opencl_path", "")
        # Perl路径
        self.perl_path = perl_path or config.get("perl_path", "")
        
        # 自动查找OpenCL和Perl路径（仅在未设置时）
        if not self.opencl_path:
            self.opencl_path = self._auto_find_opencl_path()
        if not self.perl_path:
            self.perl_path = self._auto_find_perl_path()
        
        # 设置界面
        self.setup_ui()
        
        # 先初始化opencl_status_label，避免后续方法调用时报错
        self.opencl_status_label = QtWidgets.QLabel()
        self.opencl_status_label.setMinimumWidth(120)
    
    def _auto_find_opencl_path(self):
        """优先检测系统常见OpenCL默认安装路径，未找到再递归查找当前目录"""
        import os, glob
        # 常见OpenCL安装路径
        candidates = [
            r"C:/Windows/System32",
            r"C:/Windows/SysWOW64",
            r"C:/Program Files/NVIDIA Corporation/OpenCL",
            r"C:/Program Files/AMD/OpenCL",
            r"C:/Program Files (x86)/NVIDIA Corporation/OpenCL",
            r"C:/Program Files (x86)/AMD/OpenCL",
        ]
        for path in candidates:
            if os.path.exists(path):
                dlls = [f for f in os.listdir(path) if f.lower().startswith("opencl") and f.lower().endswith(".dll")]
                if dlls:
                    return path
        # 递归查找当前目录
        base_dir = os.getcwd()
        dlls = glob.glob(os.path.join(base_dir, '**', 'OpenCL*.dll'), recursive=True)
        if dlls:
            return os.path.dirname(dlls[0])
        return ""
    
    def _auto_find_perl_path(self):
        """递归查找perl.exe完整路径"""
        base_dir = os.getcwd()
        perls = glob.glob(os.path.join(base_dir, '**', 'perl.exe'), recursive=True)
        if perls:
            return perls[0]
        return ""
    
    def setup_ui(self):
        """设置界面"""
        # 使用QFormLayout统一布局，保证标签、输入框、按钮对齐
        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        # John the Ripper
        john_row = QtWidgets.QHBoxLayout()
        self.john_path_edit = QtWidgets.QLineEdit()
        self.john_path_edit.setText(self.john_path)
        self.john_path_edit.setPlaceholderText("选择解压后的John目录（如john-1.9.0-jumbo-1-win64）")
        self.john_path_edit.setMinimumWidth(88)
        john_browse_btn = QtWidgets.QPushButton("浏览")
        john_browse_btn.setFixedWidth(50)
        john_browse_btn.clicked.connect(self.browse_john_path)
        john_row.addWidget(self.john_path_edit, alignment=QtCore.Qt.AlignVCenter)
        john_row.addWidget(john_browse_btn, alignment=QtCore.Qt.AlignVCenter)
        form_layout.addRow("John the Ripper:", john_row)

        # Hashcat
        hashcat_row = QtWidgets.QHBoxLayout()
        self.hashcat_path_edit = QtWidgets.QLineEdit()
        self.hashcat_path_edit.setText(self.hashcat_path)
        self.hashcat_path_edit.setPlaceholderText("选择解压后的Hashcat目录（如hashcat-6.2.6）")
        self.hashcat_path_edit.setMinimumWidth(88)
        hashcat_browse_btn = QtWidgets.QPushButton("浏览")
        hashcat_browse_btn.setFixedWidth(50)
        hashcat_browse_btn.clicked.connect(self.browse_hashcat_path)
        hashcat_row.addWidget(self.hashcat_path_edit, alignment=QtCore.Qt.AlignVCenter)
        hashcat_row.addWidget(hashcat_browse_btn, alignment=QtCore.Qt.AlignVCenter)
        form_layout.addRow("Hashcat:", hashcat_row)

        # OpenCL
        opencl_row = QtWidgets.QHBoxLayout()
        opencl_row.setContentsMargins(0, 0, 0, 0)
        opencl_row.setSpacing(6)
        self.opencl_path_edit = QtWidgets.QLineEdit()
        self.opencl_path_edit.setText(self.opencl_path)
        self.opencl_path_edit.setPlaceholderText("可选：指定OpenCL运行库目录（如有需要）")
        self.opencl_path_edit.setMinimumWidth(88)
        opencl_browse_btn = QtWidgets.QPushButton("浏览")
        opencl_browse_btn.setFixedWidth(50)
        opencl_browse_btn.clicked.connect(self.browse_opencl_path)
        opencl_row.addWidget(self.opencl_path_edit, alignment=QtCore.Qt.AlignVCenter)
        opencl_row.addWidget(opencl_browse_btn, alignment=QtCore.Qt.AlignVCenter)
        form_layout.addRow("OpenCL路径:", opencl_row)

        # Perl
        perl_row = QtWidgets.QHBoxLayout()
        self.perl_path_edit = QtWidgets.QLineEdit()
        self.perl_path_edit.setText(self.perl_path)
        self.perl_path_edit.setPlaceholderText("可选：指定perl.exe路径（如C:/Strawberry/perl/bin/perl.exe）")
        self.perl_path_edit.setMinimumWidth(88)
        perl_browse_btn = QtWidgets.QPushButton("浏览")
        perl_browse_btn.setFixedWidth(50)
        perl_browse_btn.clicked.connect(self.browse_perl_path)
        perl_row.addWidget(self.perl_path_edit, alignment=QtCore.Qt.AlignVCenter)
        perl_row.addWidget(perl_browse_btn, alignment=QtCore.Qt.AlignVCenter)
        form_layout.addRow("Perl路径:", perl_row)

        self.main_layout.addLayout(form_layout)
        
        # 间隔
        self.main_layout.addSpacing(10)
        
        # 按钮区（自定义布局，所有按钮靠右，默认宽度）
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.ok_button = QtWidgets.QPushButton("确定")
        btn_layout.addWidget(self.ok_button)
        self.refresh_btn = QtWidgets.QPushButton("刷新状态")
        btn_layout.addWidget(self.refresh_btn)
        opencl_status_btn = QtWidgets.QPushButton("OpenCL状态")
        opencl_status_btn.clicked.connect(self.check_opencl_status)
        btn_layout.addWidget(opencl_status_btn)
        self.cancel_button = QtWidgets.QPushButton("取消")
        btn_layout.addWidget(self.cancel_button)
        self.main_layout.addSpacing(10)
        self.main_layout.addLayout(btn_layout)
        # 绑定按钮事件
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
    
    def browse_opencl_path(self):
        folder_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择OpenCL目录", ""
        )
        if folder_path:
            self.opencl_path_edit.setText(folder_path)
    
    def browse_perl_path(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择perl.exe", "", "可执行文件 (*.exe);;所有文件 (*)"
        )
        if file_path:
            self.perl_path_edit.setText(file_path)
    
    def browse_john_path(self):
        """浏览John the Ripper路径"""
        folder_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择John the Ripper目录", ""
        )
        
        if folder_path:
            self.john_path_edit.setText(folder_path)
    
    def browse_hashcat_path(self):
        """浏览Hashcat路径"""
        folder_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择Hashcat目录", ""
        )
        
        if folder_path:
            self.hashcat_path_edit.setText(folder_path)
    
    def get_paths(self):
        """获取路径设置
        
        Returns:
            dict: 包含john_path和hashcat_path的字典
        """
        return {
            "john_path": self.john_path_edit.text().strip(),
            "hashcat_path": self.hashcat_path_edit.text().strip(),
            "opencl_path": self.opencl_path_edit.text().strip(),
            "perl_path": self.perl_path_edit.text().strip()
        }

    def check_opencl_status(self):
        """使用pyopencl查询OpenCL平台和设备信息"""
        try:
            import pyopencl as cl
            platforms = cl.get_platforms()
            if not platforms:
                QtWidgets.QMessageBox.warning(self, "OpenCL检测", "未检测到任何OpenCL平台。")
                self.opencl_status_label.setText("未检测到OpenCL平台")
                self.opencl_status_label.setStyleSheet("color:#F44336;")
                return
            info_lines = []
            for p in platforms:
                info_lines.append(f"平台: {p.name} ({p.vendor})")
                devices = p.get_devices()
                for d in devices:
                    info_lines.append(f"  设备: {d.name} ({cl.device_type.to_string(d.type)})")
            preview = "\n".join(info_lines[:20])
            if len(info_lines) > 20:
                preview += "\n... (更多内容请用pyopencl查看)"
            QtWidgets.QMessageBox.information(self, "OpenCL信息 (pyopencl)", preview)
            self.opencl_status_label.setText("已检测到OpenCL平台")
            self.opencl_status_label.setStyleSheet("color:#4CAF50;")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "OpenCL检测", f"pyopencl检测异常: {e}")
            self.opencl_status_label.setText("检测异常")
            self.opencl_status_label.setStyleSheet("color:#F44336;")

    def refresh_tool_paths(self):
        """自动查找并填充工具路径"""
        import glob, os
        base_dir = os.getcwd()
        # 查找 john.exe
        johns = glob.glob(os.path.join(base_dir, '**', 'john.exe'), recursive=True)
        if johns:
            john_dir = os.path.dirname(johns[0])
            if os.path.basename(john_dir).lower() == 'run':
                john_dir = os.path.dirname(john_dir)
            self.john_path_edit.setText(john_dir)
        # 查找 hashcat.exe
        hashcats = glob.glob(os.path.join(base_dir, '**', 'hashcat.exe'), recursive=True)
        if hashcats:
            self.hashcat_path_edit.setText(hashcats[0])
        # 查找 OpenCL
        opencls = glob.glob(os.path.join(base_dir, '**', 'OpenCL*'), recursive=True)
        if opencls:
            self.opencl_path_edit.setText(os.path.dirname(opencls[0]))
        # 查找 perl.exe
        perls = glob.glob(os.path.join(base_dir, '**', 'perl.exe'), recursive=True)
        if perls:
            self.perl_path_edit.setText(perls[0])

class AboutDialog(BaseDialog):
    """关于对话框"""
    
    def __init__(self, parent=None, version="4.0.2"):
        """初始化对话框
        
        Args:
            parent: 父窗口
            version (str): 版本号
        """
        super().__init__(parent)
        self.setWindowTitle("关于 ZIP Cracker")
        self.resize(400, 300)
        
        # 标题
        title_label = QtWidgets.QLabel("ZIP Cracker")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.main_layout.addWidget(title_label)
        
        # 版本
        version_label = QtWidgets.QLabel(f"版本 {version}")
        version_label.setAlignment(QtCore.Qt.AlignCenter)
        self.main_layout.addWidget(version_label)
        
        # 分隔线
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.main_layout.addWidget(line)
        
        # 描述
        desc_label = QtWidgets.QLabel(
            "ZIP Cracker是一个用于破解加密压缩文件的工具，"
            "支持多种破解方式，包括字典攻击、掩码攻击等。"
        )
        desc_label.setWordWrap(True)
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        self.main_layout.addWidget(desc_label)
        
        # 依赖工具
        tools_label = QtWidgets.QLabel(
            "本工具依赖于以下开源项目：\n"
            "- John the Ripper\n"
            "- Hashcat"
        )
        tools_label.setAlignment(QtCore.Qt.AlignCenter)
        self.main_layout.addWidget(tools_label)
        
        # 版权信息
        copyright_label = QtWidgets.QLabel("© 2023-2024 ZIPCracker Team. 保留所有权利。")
        copyright_label.setAlignment(QtCore.Qt.AlignCenter)
        self.main_layout.addWidget(copyright_label)
        
        self.main_layout.addStretch()
        
        # 按钮布局
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        ok_btn = QtWidgets.QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        self.main_layout.addLayout(btn_layout)

class HelpDialog(BaseDialog):
    """帮助对话框"""
    
    def __init__(self, parent=None):
        """初始化对话框
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("使用帮助")
        self.resize(600, 400)
        
        # 使用选项卡组织内容
        tab_widget = QtWidgets.QTabWidget()
        
        # 基本使用选项卡
        basic_tab = QtWidgets.QWidget()
        basic_layout = QtWidgets.QVBoxLayout(basic_tab)
        
        basic_help = QtWidgets.QTextEdit()
        basic_help.setReadOnly(True)
        basic_help.setHtml("""
            <h3>基本使用</h3>
            <ol>
                <li><b>选择文件</b>: 点击标题栏的"文件"按钮或将文件拖放到程序窗口中。</li>
                <li><b>提取哈希</b>: 选择文件后，点击"提取哈希"按钮，程序会自动提取文件的哈希值。</li>
                <li><b>选择攻击模式</b>: 选择合适的攻击模式，并设置相应的参数。</li>
                <li><b>开始破解</b>: 点击"开始破解"按钮，开始破解过程。</li>
                <li><b>查看结果</b>: 破解成功后，密码将显示在界面上，可以复制使用。</li>
            </ol>
        """)
        basic_layout.addWidget(basic_help)
        
        tab_widget.addTab(basic_tab, "基本使用")
        
        # 攻击模式选项卡
        attack_tab = QtWidgets.QWidget()
        attack_layout = QtWidgets.QVBoxLayout(attack_tab)
        
        attack_help = QtWidgets.QTextEdit()
        attack_help.setReadOnly(True)
        attack_help.setHtml("""
            <h3>攻击模式说明</h3>
            <ul>
                <li><b>字典攻击</b>: 使用预设的密码字典进行破解，适合常见密码。</li>
                <li><b>掩码攻击</b>: 使用特定规则生成密码进行破解，适合已知密码部分信息的情况。</li>
                <li><b>字典+规则</b>: 在字典基础上应用变形规则，提高破解成功率。</li>
                <li><b>组合攻击</b>: 将两个字典的内容组合生成密码，适合密码由多个部分组成的情况。</li>
                <li><b>混合攻击</b>: 结合字典和掩码的攻击方式，更加灵活。</li>
            </ul>
            <h4>掩码说明</h4>
            <p>掩码使用特定字符表示不同类型的字符：</p>
            <ul>
                <li><b>?l</b> - 小写字母 (a-z)</li>
                <li><b>?u</b> - 大写字母 (A-Z)</li>
                <li><b>?d</b> - 数字 (0-9)</li>
                <li><b>?s</b> - 特殊字符 (空格和标点符号)</li>
                <li><b>?a</b> - 所有字符</li>
                <li><b>?h</b> - 十六进制小写 (0-9, a-f)</li>
                <li><b>?H</b> - 十六进制大写 (0-9, A-F)</li>
            </ul>
            <p>例如，<code>?l?l?l?l?d?d</code> 表示4个小写字母后跟2个数字的密码。</p>
        """)
        attack_layout.addWidget(attack_help)
        
        tab_widget.addTab(attack_tab, "攻击模式")
        
        # 常见问题选项卡
        faq_tab = QtWidgets.QWidget()
        faq_layout = QtWidgets.QVBoxLayout(faq_tab)
        
        faq_help = QtWidgets.QTextEdit()
        faq_help.setReadOnly(True)
        faq_help.setHtml("""
            <h3>常见问题</h3>
            <p><b>Q: 无法提取哈希值怎么办？</b></p>
            <p>A: 确保已正确设置John the Ripper的路径，并且文件确实是加密的。某些文件格式可能不受支持。</p>
            
            <p><b>Q: 破解速度很慢怎么办？</b></p>
            <p>A: 尝试启用GPU加速（需要有支持CUDA或OpenCL的显卡），或使用更小的字典文件。</p>
            
            <p><b>Q: 找不到密码怎么办？</b></p>
            <p>A: 尝试使用不同的攻击模式或更大的字典文件。对于复杂密码，可能需要更长的时间。</p>
            
            <p><b>Q: 支持哪些类型的文件？</b></p>
            <p>A: 当前支持ZIP、RAR、7Z、PDF等常见加密文件格式。</p>
        """)
        faq_layout.addWidget(faq_help)
        
        tab_widget.addTab(faq_tab, "常见问题")
        
        # 新增：Hashcat使用技巧Tab
        hashcat_tab = QtWidgets.QWidget()
        hashcat_layout = QtWidgets.QVBoxLayout(hashcat_tab)
        hashcat_help = QtWidgets.QTextEdit()
        hashcat_help.setReadOnly(True)
        hashcat_help.setHtml('''
            <h3>Hashcat GPU破解与常用命令</h3>
            <p>Hashcat 是世界上破解密码速度最快的工具之一，支持 GPU/CPU/APU/FPGA 等多种核心。推荐使用官方驱动，尤其是 NVIDIA 显卡请务必安装官网下载的驱动。</p>
            <h4>一、检测GPU支持</h4>
            <pre>hashcat64.exe -b</pre>
            <p>基准测试，能看到显卡信息即支持GPU加速。</p>
            <h4>二、常用参数说明</h4>
            <ul>
                <li><b>-m NUM</b>：哈希类型编号，如 -m 1800 表示 sha512。</li>
                <li><b>-a NUM</b>：攻击模式，0=字典，1=组合，3=掩码。</li>
                <li><b>-V</b>：显示版本信息。</li>
                <li><b>-h</b>：帮助信息。</li>
                <li><b>-b</b>：基准测试。</li>
                <li><b>--force</b>：强制运行（遇到警告时）。</li>
                <li><b>--opencl-device-types</b>：指定设备类型。</li>
                <li><b>--status</b>：显示破解进度。</li>
                <li><b>-o FILE</b>：输出破解结果到文件。</li>
                <li><b>--remove</b>：破解成功后自动移除hash。</li>
                <li><b>-r FILE</b>：使用规则文件。</li>
                <li><b>--increment</b>：掩码攻击时启用长度递增。</li>
            </ul>
            <h4>三、常见攻击命令示例</h4>
            <pre>
# 字典攻击
hashcat64.exe -a 0 -m 0 hash.txt rockyou.txt

# 掩码攻击（8位数字）
hashcat64.exe -a 3 -m 0 hash.txt ?d?d?d?d?d?d?d?d

# 组合攻击
hashcat64.exe -a 1 -m 0 hash.txt dict1.txt dict2.txt

# 使用规则
hashcat64.exe -a 0 -m 0 -r rules/best64.rule hash.txt rockyou.txt

# 会话保存与恢复
hashcat64.exe -a 3 -m 0 --session mysess hash.txt ?d?d?d?d?d?d?d?d
hashcat64.exe --session mysess --restore
            </pre>
            <h4>四、性能优化参数</h4>
            <ul>
                <li><b>--workload-profile NUM</b>：负载调优，常用1/2/3/4。</li>
                <li><b>--gpu-accel NUM</b>：GPU加速等级，常用160。</li>
                <li><b>--gpu-loops NUM</b>：GPU循环，常用1024。</li>
                <li><b>--segment-size NUM</b>：字典缓存大小，单位MB。</li>
            </ul>
            <h4>五、常用哈希类型编号（-m参数）</h4>
            <table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px;">
                <tr><th>编号</th><th>类型</th><th>说明</th></tr>
                <tr><td>0</td><td>MD5</td><td>常见Web/系统密码</td></tr>
                <tr><td>100</td><td>SHA1</td><td>常见Web/系统密码</td></tr>
                <tr><td>1400</td><td>SHA256</td><td>常见Web/系统密码</td></tr>
                <tr><td>1700</td><td>SHA512</td><td>常见Web/系统密码</td></tr>
                <tr><td>500</td><td>md5crypt</td><td>Unix/Linux MD5</td></tr>
                <tr><td>1800</td><td>sha512crypt</td><td>Unix/Linux SHA512</td></tr>
                <tr><td>1000</td><td>NTLM</td><td>Windows登录</td></tr>
                <tr><td>3000</td><td>LM</td><td>Windows早期登录</td></tr>
                <tr><td>5500</td><td>NetNTLMv1</td><td>Windows网络认证</td></tr>
                <tr><td>5600</td><td>NetNTLMv2</td><td>Windows网络认证</td></tr>
                <tr><td>900</td><td>MD4</td><td>旧系统/协议</td></tr>
                <tr><td>2100</td><td>DCC2</td><td>Windows域缓存</td></tr>
                <tr><td>1100</td><td>DCC</td><td>Windows域缓存</td></tr>
                <tr><td>2500</td><td>WPA-EAPOL-PBKDF2</td><td>WiFi WPA/WPA2</td></tr>
                <tr><td>22000</td><td>WPA-PBKDF2-PMKID+EAPOL</td><td>WiFi WPA3/PMKID</td></tr>
                <tr><td>11600</td><td>7-Zip</td><td>压缩包</td></tr>
                <tr><td>12500</td><td>RAR3-hp</td><td>压缩包</td></tr>
                <tr><td>13000</td><td>RAR5</td><td>压缩包</td></tr>
                <tr><td>13600</td><td>WinZip</td><td>压缩包</td></tr>
                <tr><td>17200</td><td>PKZIP (压缩)</td><td>压缩包</td></tr>
                <tr><td>10500</td><td>PDF 1.4-1.6</td><td>PDF文档</td></tr>
                <tr><td>10400</td><td>PDF 1.1-1.3</td><td>PDF文档</td></tr>
                <tr><td>9400</td><td>MS Office 2007/2013</td><td>Office文档</td></tr>
                <tr><td>9800</td><td>MS Office 2003/2007</td><td>Office文档</td></tr>
                <tr><td>9600</td><td>MS Office 2013</td><td>Office文档</td></tr>
                <tr><td>9500</td><td>MS Office 2010</td><td>Office文档</td></tr>
                <tr><td>18400</td><td>ODF 1.2</td><td>Open Document Format</td></tr>
                <tr><td>13400</td><td>KeePass</td><td>密码管理器</td></tr>
                <tr><td>11300</td><td>Bitcoin/Litecoin wallet.dat</td><td>加密货币钱包</td></tr>
                <tr><td>14600</td><td>LUKS v1</td><td>全盘加密</td></tr>
                <tr><td>22100</td><td>BitLocker</td><td>全盘加密</td></tr>
                <tr><td>13711</td><td>VeraCrypt</td><td>全盘加密</td></tr>
                <tr><td>12200</td><td>eCryptfs</td><td>全盘加密</td></tr>
                <tr><td>9000</td><td>Password Safe v2</td><td>密码管理器</td></tr>
                <tr><td>5200</td><td>Password Safe v3</td><td>密码管理器</td></tr>
                <tr><td>6800</td><td>LastPass</td><td>密码管理器</td></tr>
            </table>
            <p style="color:#888;font-size:11px;">更多哈希类型请参考 <a href="https://hashcat.net/wiki/doku.php?id=hashcat" target="_blank">Hashcat官方Wiki</a>。</p>
            <h4>六、密码设置建议</h4>
            <ul>
                <li>使用更长的密码（8位以上）。</li>
                <li>混合字母、数字、符号。</li>
                <li>避免使用与自己相关的生日、手机号等。</li>
            </ul>
            <p>更多详细用法和参数请参考 <a href="#" target="_blank">Hashcat官方使用详解</a>。</p>
            <h4>六、特殊哈希类型（常见但不属于普通Web/系统）</h4>
            <table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px;">
                <tr><th>编号</th><th>类型</th><th>说明</th></tr>
                <tr><td>2500</td><td>WPA-EAPOL-PBKDF2</td><td>WiFi WPA/WPA2</td></tr>
                <tr><td>22000</td><td>WPA-PBKDF2-PMKID+EAPOL</td><td>WiFi WPA3/PMKID</td></tr>
                <tr><td>11300</td><td>Bitcoin/Litecoin wallet.dat</td><td>加密货币钱包</td></tr>
                <tr><td>14600</td><td>LUKS v1</td><td>全盘加密</td></tr>
                <tr><td>22100</td><td>BitLocker</td><td>全盘加密</td></tr>
                <tr><td>13711</td><td>VeraCrypt</td><td>全盘加密</td></tr>
                <tr><td>12200</td><td>eCryptfs</td><td>全盘加密</td></tr>
                <tr><td>18400</td><td>ODF 1.2</td><td>Open Document Format</td></tr>
                <tr><td>13400</td><td>KeePass</td><td>密码管理器</td></tr>
                <tr><td>9000</td><td>Password Safe v2</td><td>密码管理器</td></tr>
                <tr><td>5200</td><td>Password Safe v3</td><td>密码管理器</td></tr>
                <tr><td>6800</td><td>LastPass</td><td>密码管理器</td></tr>
            </table>
            <h4>七、常用破解规则与掩码示例</h4>
            <ul>
                <li><b>数字掩码</b>：?d?d?d?d?d?d?d?d（8位数字）</li>
                <li><b>小写字母掩码</b>：?l?l?l?l?l?l（6位小写字母）</li>
                <li><b>大写字母掩码</b>：?u?u?u?u?u?u?u（7位大写字母）</li>
                <li><b>混合掩码</b>：-2 ?d?l ?2?2?2?2?2?2（数字+小写字母混合6位）</li>
                <li><b>长度递增</b>：--increment --increment-min 6 --increment-max 8 ?l?l?l?l?l?l?l?l（6-8位递增）</li>
                <li><b>规则文件</b>：-r rules/best64.rule（常用变形规则）</li>
                <li><b>组合用法</b>：hashcat -a 0 -m 0 -r rules/best64.rule hash.txt rockyou.txt</li>
                <li><b>会话保存与恢复</b>：--session myjob --restore</li>
                <li><b>掩码文件</b>：masks/rockyou-7-2592000.hcmask（批量掩码）</li>
            </ul>
            <pre>
# 典型命令示例
# 8位数字暴力破解
hashcat64.exe -a 3 -m 0 hash.txt ?d?d?d?d?d?d?d?d
# 6-8位小写字母递增
hashcat64.exe -a 3 -m 0 --increment --increment-min 6 --increment-max 8 hash.txt ?l?l?l?l?l?l?l?l
# 字典+规则
hashcat64.exe -a 0 -m 0 -r rules/best64.rule hash.txt rockyou.txt
# 使用掩码文件
hashcat -m 2611 -a 3 --session mydz dz.hash masks/rockyou-7-2592000.hcmask
# 恢复会话
hashcat --session mydz --restore
            </pre>
            <p style="color:#888;font-size:11px;">更多规则和掩码技巧详见 <a href="#" target="_blank">Hashcat官方使用详解</a>。</p>
        ''')
        hashcat_layout.addWidget(hashcat_help)
        tab_widget.addTab(hashcat_tab, "Hashcat使用技巧")
        
        self.main_layout.addWidget(tab_widget)
        
        # 按钮布局
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        ok_btn = QtWidgets.QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        self.main_layout.addLayout(btn_layout)

class MaskGeneratorDialog(BaseDialog):
    """掩码生成器对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("掩码生成器")
        self.resize(600, 500)
        desc_label = QtWidgets.QLabel("生成密码掩码以加速破解")
        desc_label.setStyleSheet("font-weight: bold;")
        self.main_layout.addWidget(desc_label)

        self.tab_widget = QtWidgets.QTabWidget()

        # 1. 基本掩码Tab
        basic_tab = QtWidgets.QWidget()
        basic_layout = QtWidgets.QVBoxLayout(basic_tab)
        example_group = QtWidgets.QGroupBox("密码示例")
        example_layout = QtWidgets.QFormLayout(example_group)
        self.example_input = QtWidgets.QLineEdit()
        self.example_input.setPlaceholderText("输入一个与目标密码相似的例子")
        self.example_input.textChanged.connect(self.update_basic_mask)
        example_layout.addRow("密码例子:", self.example_input)
        self.mask_output = QtWidgets.QLineEdit()
        self.mask_output.setReadOnly(True)
        example_layout.addRow("识别掩码:", self.mask_output)
        basic_layout.addWidget(example_group)
        # 一键应用按钮
        apply_basic_btn = QtWidgets.QPushButton("应用此掩码")
        apply_basic_btn.clicked.connect(lambda: self.apply_mask_to_main(self.mask_output.text()))
        basic_layout.addWidget(apply_basic_btn)
        self.tab_widget.addTab(basic_tab, "基本掩码")

        # 2. 常用掩码Tab
        common_tab = QtWidgets.QWidget()
        common_layout = QtWidgets.QVBoxLayout(common_tab)
        common_mask_hint = QtWidgets.QLabel("双击选择常用掩码:")
        common_mask_hint.setStyleSheet("color: #0078D7; font-style: italic;")
        common_layout.addWidget(common_mask_hint)
        self.common_mask_list = QtWidgets.QListWidget()
        self.init_common_masks()
        self.common_mask_list.itemDoubleClicked.connect(self.apply_common_mask)
        common_layout.addWidget(self.common_mask_list)
        # 一键应用按钮
        apply_common_btn = QtWidgets.QPushButton("应用选中掩码")
        apply_common_btn.clicked.connect(self.apply_selected_common_mask)
        common_layout.addWidget(apply_common_btn)
        self.tab_widget.addTab(common_tab, "常用掩码")

        # 3. 自定义掩码Tab（密码特征+每位手动选择）
        custom_tab = QtWidgets.QWidget()
        custom_layout = QtWidgets.QVBoxLayout(custom_tab)
        feature_group = QtWidgets.QGroupBox("密码特征生成掩码")
        feature_layout = QtWidgets.QVBoxLayout(feature_group)
        length_layout = QtWidgets.QHBoxLayout()
        length_layout.addWidget(QtWidgets.QLabel("密码长度:"))
        self.password_length = QtWidgets.QLineEdit()
        self.password_length.setText("8")
        self.password_length.setMaximumWidth(60)
        self.password_length.setValidator(QtGui.QIntValidator(1, 99))
        length_layout.addWidget(self.password_length)
        length_hint = QtWidgets.QLabel("位")
        length_layout.addWidget(length_hint)
        length_layout.addStretch()
        feature_layout.addLayout(length_layout)
        charset_layout = QtWidgets.QVBoxLayout()
        charset_layout.addWidget(QtWidgets.QLabel("选择字符集:"))
        self.lowercase_check = QtWidgets.QCheckBox("小写字母 (a-z)")
        self.lowercase_check.setChecked(True)
        charset_layout.addWidget(self.lowercase_check)
        self.uppercase_check = QtWidgets.QCheckBox("大写字母 (A-Z)")
        self.uppercase_check.setChecked(True)
        charset_layout.addWidget(self.uppercase_check)
        self.digits_check = QtWidgets.QCheckBox("数字 (0-9)")
        self.digits_check.setChecked(True)
        charset_layout.addWidget(self.digits_check)
        self.special_check = QtWidgets.QCheckBox("特殊字符 (!@#$%^&*...)")
        charset_layout.addWidget(self.special_check)
        self.lowercase_check.toggled.connect(self.update_custom_mask)
        self.uppercase_check.toggled.connect(self.update_custom_mask)
        self.digits_check.toggled.connect(self.update_custom_mask)
        self.special_check.toggled.connect(self.update_custom_mask)
        self.password_length.textChanged.connect(self.on_custom_length_changed)
        feature_layout.addLayout(charset_layout)
        custom_layout.addWidget(feature_group)
        # 每位手动选择区域
        manual_group = QtWidgets.QGroupBox("每位手动选择类型（更专业）")
        manual_layout = QtWidgets.QHBoxLayout(manual_group)
        self.manual_combo_boxes = []
        custom_layout.addWidget(manual_group)
        # 掩码显示
        self.custom_mask_input = QtWidgets.QLineEdit()
        self.custom_mask_input.setPlaceholderText("自动生成的掩码")
        self.custom_mask_input.setReadOnly(True)
        custom_layout.addWidget(self.custom_mask_input)
        # 一键应用按钮
        apply_custom_btn = QtWidgets.QPushButton("应用此掩码")
        apply_custom_btn.clicked.connect(lambda: self.apply_mask_to_main(self.custom_mask_input.text()))
        custom_layout.addWidget(apply_custom_btn)
        self.tab_widget.addTab(custom_tab, "自定义掩码")
        self.main_layout.addWidget(self.tab_widget)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)
        self.main_layout.addLayout(btn_layout)
        self.on_custom_length_changed()

    def on_custom_length_changed(self):
        """密码长度变化时，动态生成每位下拉框"""
        try:
            length = int(self.password_length.text())
        except Exception:
            length = 0
        # 清除旧的
        for cb in getattr(self, 'manual_combo_boxes', []):
            cb.setParent(None)
        self.manual_combo_boxes = []
        # 生成新下拉框
        options = [
            ("小写", "?l"),
            ("大写", "?u"),
            ("数字", "?d"),
            ("符号", "?s"),
            ("任意", "?a")
        ]
        manual_group = None
        for w in self.tab_widget.widget(2).findChildren(QtWidgets.QGroupBox):
            if w.title().startswith("每位手动选择类型"):
                manual_group = w
                break
        if manual_group is None:
            return
        layout = manual_group.layout()
        # 移除旧控件
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        # 添加新下拉框
        for i in range(length):
            cb = QtWidgets.QComboBox()
            for label, val in options:
                cb.addItem(label, val)
            cb.setCurrentIndex(i % 3)  # 默认前几位小写/大写/数字
            cb.currentIndexChanged.connect(self.update_manual_mask)
            layout.addWidget(cb)
            self.manual_combo_boxes.append(cb)
        self.update_manual_mask()

    def update_manual_mask(self):
        """根据每位下拉框生成掩码"""
        if not self.manual_combo_boxes:
            self.update_custom_mask()
            return
        mask = "".join(cb.currentData() for cb in self.manual_combo_boxes)
        self.custom_mask_input.setText(mask)

    def update_basic_mask(self):
        """根据示例更新基本掩码，支持更多类型"""
        example = self.example_input.text()
        if not example:
            self.mask_output.setText("")
            return
        mask = ""
        for char in example:
            if char.islower():
                mask += "?l"
            elif char.isupper():
                mask += "?u"
            elif char.isdigit():
                mask += "?d"
            elif char in "!@#$%^&*()_+-=~`[]{};:'\",.<>/?|":
                mask += "?s"
            else:
                mask += "?a"  # 其他字符归为所有字符
        self.mask_output.setText(mask)

    def update_custom_mask(self):
        """根据密码特征生成掩码（批量方式）"""
        # 如果有手动下拉框，优先用手动
        if getattr(self, 'manual_combo_boxes', []):
            self.update_manual_mask()
            return
        length = self.password_length.text()
        charsets = []
        if self.lowercase_check.isChecked():
            charsets.append("?l")
        if self.uppercase_check.isChecked():
            charsets.append("?u")
        if self.digits_check.isChecked():
            charsets.append("?d")
        if self.special_check.isChecked():
            charsets.append("?s")
        if not charsets:
            charsets = ["?l"]
            self.lowercase_check.setChecked(True)
        mask = ""
        if not length:
            self.custom_mask_input.setText("")
            return
        for i in range(int(length)):
            mask += charsets[i % len(charsets)]
        self.custom_mask_input.setText(mask)

    def init_common_masks(self):
        common_masks = [
            {"name": "6位数字 (如123456)", "mask": "?d?d?d?d?d?d"},
            {"name": "8位数字 (如12345678)", "mask": "?d?d?d?d?d?d?d?d"},
            {"name": "6位小写字母 (如abcdef)", "mask": "?l?l?l?l?l?l"},
            {"name": "8位小写字母 (如password)", "mask": "?l?l?l?l?l?l?l?l"},
            {"name": "首字母大写+5位小写 (如Admin)", "mask": "?u?l?l?l?l?l"},
            {"name": "首字母大写+7位小写 (如Password)", "mask": "?u?l?l?l?l?l?l?l"},
            {"name": "4位字母+2位数字 (如pass12)", "mask": "?l?l?l?l?d?d"},
            {"name": "6位字母+2位数字 (如passwd12)", "mask": "?l?l?l?l?l?l?d?d"},
            {"name": "3位字母+5位数字 (如abc12345)", "mask": "?l?l?l?d?d?d?d?d"},
            {"name": "日期格式DDMMYYYY (如01012023)", "mask": "?d?d?d?d?d?d?d?d"}
        ]
        self.common_mask_list.clear()
        for mask_data in common_masks:
            item = QtWidgets.QListWidgetItem(mask_data["name"])
            item.setData(QtCore.Qt.UserRole, mask_data["mask"])
            self.common_mask_list.addItem(item)

    def apply_common_mask(self, item):
        mask = item.data(QtCore.Qt.UserRole)
        self.apply_mask_to_main(mask)

    def apply_selected_common_mask(self):
        item = self.common_mask_list.currentItem()
        if item:
            self.apply_common_mask(item)

    def apply_mask_to_main(self, mask):
        if mask:
            self._selected_mask = mask
            self.accept()

    def get_mask(self):
        return getattr(self, '_selected_mask', None) or ''

class HistoryDialog(BaseDialog):
    """历史记录对话框"""
    
    def __init__(self, parent=None, history_manager=None):
        """初始化对话框
        
        Args:
            parent: 父窗口
            history_manager: 历史记录管理器
        """
        super().__init__(parent)
        self.setWindowTitle("破解历史记录")
        self.resize(800, 500)
        
        self.history_manager = history_manager
        
        # 创建内容布局
        content_layout = QtWidgets.QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        
        # 搜索过滤区域
        filter_group = QtWidgets.QGroupBox("搜索过滤")
        filter_layout = QtWidgets.QHBoxLayout(filter_group)
        
        # 搜索框
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("搜索文件名、哈希值或密码...")
        self.search_edit.textChanged.connect(self.filter_records)
        filter_layout.addWidget(self.search_edit)
        
        # 过滤按钮
        filter_btn = QtWidgets.QPushButton("过滤")
        filter_btn.clicked.connect(self.filter_records)
        filter_layout.addWidget(filter_btn)
        
        # 清除过滤按钮
        clear_filter_btn = QtWidgets.QPushButton("清除过滤")
        clear_filter_btn.clicked.connect(lambda: self.search_edit.clear())
        filter_layout.addWidget(clear_filter_btn)
        
        content_layout.addWidget(filter_group)
        
        # 历史记录表格
        self.history_table = QtWidgets.QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["破解时间", "文件名", "哈希值", "密码", "耗时"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.history_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.history_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self.show_context_menu)
        content_layout.addWidget(self.history_table)
        
        # 操作按钮
        btn_layout = QtWidgets.QHBoxLayout()
        
        export_btn = QtWidgets.QPushButton("导出历史")
        export_btn.clicked.connect(self.export_history)
        btn_layout.addWidget(export_btn)
        
        clear_btn = QtWidgets.QPushButton("清空历史")
        clear_btn.clicked.connect(self.clear_history)
        btn_layout.addWidget(clear_btn)
        
        btn_layout.addStretch()
        
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        content_layout.addLayout(btn_layout)
        
        # 添加内容到主布局
        self.main_layout.addLayout(content_layout)
        
        # 加载历史记录
        self.load_records()
    
    def load_records(self):
        """加载历史记录"""
        if not self.history_manager:
            return
        
        # 清空表格
        self.history_table.setRowCount(0)
        
        # 获取所有记录
        records = self.history_manager.get_all_records()
        
        # 添加到表格
        for record in records:
            self.add_record_to_table(record)
    
    def add_record_to_table(self, record):
        """添加记录到表格
        
        Args:
            record (dict): 记录字典
        """
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        
        # 破解时间
        crack_time = ""
        if record.get("crack_time") is not None:
            crack_time = format_duration(record["crack_time"])
        self.history_table.setItem(row, 0, QtWidgets.QTableWidgetItem(crack_time))
        
        # 文件名
        file_name = os.path.basename(record.get("file_path", "未知文件"))
        self.history_table.setItem(row, 1, QtWidgets.QTableWidgetItem(file_name))
        
        # 哈希值
        hash_value = record.get("hash_value", "")
        display_hash = hash_value[:37] + "..." if len(hash_value) > 40 else hash_value
        hash_item = QtWidgets.QTableWidgetItem(display_hash)
        hash_item.setToolTip(hash_value)  # 存储完整哈希
        self.history_table.setItem(row, 2, hash_item)
        
        # 密码
        self.history_table.setItem(row, 3, QtWidgets.QTableWidgetItem(record.get("password", "")))
        
        # 耗时
        if "crack_time" in record and record["crack_time"] is not None:
            self.history_table.setItem(row, 4, QtWidgets.QTableWidgetItem(format_duration(record["crack_time"])))
        else:
            self.history_table.setItem(row, 4, QtWidgets.QTableWidgetItem("未知"))
    
    def filter_records(self):
        """过滤记录"""
        search_text = self.search_edit.text().lower()
        
        for row in range(self.history_table.rowCount()):
            match = False
            
            for col in range(self.history_table.columnCount()):
                item = self.history_table.item(row, col)
                if item and search_text in item.text().lower():
                    match = True
                    break
            
            self.history_table.setRowHidden(row, not match)
    
    def export_history(self):
        """导出历史记录"""
        if not self.history_manager or len(self.history_manager.get_all_records()) == 0:
            show_info_dialog(self, "没有历史记录可导出", title="提示")
            return
        
        # 选择导出格式
        format_dialog = QtWidgets.QDialog(self)
        format_dialog.setWindowTitle("选择导出格式")
        format_dialog.resize(300, 150)
        
        format_layout = QtWidgets.QVBoxLayout(format_dialog)
        
        format_label = QtWidgets.QLabel("选择导出格式:")
        format_layout.addWidget(format_label)
        
        format_group = QtWidgets.QButtonGroup(format_dialog)
        
        csv_radio = QtWidgets.QRadioButton("CSV文件")
        csv_radio.setChecked(True)
        format_group.addButton(csv_radio, 0)
        format_layout.addWidget(csv_radio)
        
        json_radio = QtWidgets.QRadioButton("JSON文件")
        format_group.addButton(json_radio, 1)
        format_layout.addWidget(json_radio)
        
        text_radio = QtWidgets.QRadioButton("文本文件")
        format_group.addButton(text_radio, 2)
        format_layout.addWidget(text_radio)
        
        format_layout.addStretch()
        
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        ok_btn = QtWidgets.QPushButton("确定")
        ok_btn.clicked.connect(format_dialog.accept)
        btn_layout.addWidget(ok_btn)
        
        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.clicked.connect(format_dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        format_layout.addLayout(btn_layout)
        
        if format_dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        
        # 获取导出格式
        export_format = format_group.checkedId()
        
        # 选择保存路径
        file_filter = ""
        if export_format == 0:
            file_filter = "CSV文件 (*.csv)"
            default_ext = ".csv"
        elif export_format == 1:
            file_filter = "JSON文件 (*.json)"
            default_ext = ".json"
        else:
            file_filter = "文本文件 (*.txt)"
            default_ext = ".txt"
        
        import datetime
        current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"zipcracker_history_{current_time}{default_ext}"
        
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出历史记录", default_filename, file_filter
        )
        
        if not filename:
            return
        
        try:
            # 导出历史记录
            if export_format == 0:
                self.history_manager.export_to_csv(filename)
            elif export_format == 1:
                self.history_manager.export_to_json(filename)
            else:
                self.history_manager.export_to_text(filename)
            
            show_info_dialog(self, f"历史记录已导出到 {filename}", title="成功")
        except Exception as e:
            show_error_dialog(self, "导出失败", detail=str(e))
    
    def clear_history(self):
        """清空历史记录"""
        if not self.history_manager or len(self.history_manager.get_all_records()) == 0:
            show_info_dialog(self, "没有历史记录可清空", title="提示")
            return
        
        reply = QtWidgets.QMessageBox.question(
            self, "确认", 
            "确定要清空所有历史记录吗？此操作不可撤销。", 
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, 
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.history_manager.clear_history()
            self.history_table.setRowCount(0)
            show_info_dialog(self, "历史记录已清空", title="成功")
    
    def show_context_menu(self, position):
        """显示上下文菜单
        
        Args:
            position: 菜单位置
        """
        # 获取选中的行
        indexes = self.history_table.selectedIndexes()
        if not indexes:
            return
        
        # 创建菜单
        menu = QtWidgets.QMenu(self)
        
        # 复制选中项
        copy_action = menu.addAction("复制选中项")
        copy_action.triggered.connect(self.copy_selected)
        
        # 复制密码
        copy_password_action = menu.addAction("复制密码")
        copy_password_action.triggered.connect(self.copy_password)
        
        # 复制哈希值
        copy_hash_action = menu.addAction("复制哈希值")
        copy_hash_action.triggered.connect(self.copy_hash)
        
        # 删除记录
        menu.addSeparator()
        delete_action = menu.addAction("删除记录")
        delete_action.triggered.connect(self.delete_selected)
        
        # 显示菜单
        menu.exec_(self.history_table.viewport().mapToGlobal(position))
    
    def copy_selected(self):
        """复制选中项"""
        indexes = self.history_table.selectedIndexes()
        if not indexes:
            return
        
        # 获取选中的文本
        text = ""
        for index in indexes:
            text += self.history_table.item(index.row(), index.column()).text() + "\t"
            if index.column() == self.history_table.columnCount() - 1:
                text += "\n"
        
        # 复制到剪贴板
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(text)
    
    def copy_password(self):
        """复制密码"""
        indexes = self.history_table.selectedIndexes()
        if not indexes:
            return
        
        # 获取密码列
        row = indexes[0].row()
        password_item = self.history_table.item(row, 3)
        
        if password_item:
            # 复制到剪贴板
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(password_item.text())
    
    def copy_hash(self):
        """复制哈希值"""
        indexes = self.history_table.selectedIndexes()
        if not indexes:
            return
        
        # 获取哈希值列
        row = indexes[0].row()
        hash_item = self.history_table.item(row, 2)
        
        if hash_item:
            # 获取完整哈希值（从工具提示）
            hash_value = hash_item.toolTip()
            
            # 复制到剪贴板
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(hash_value)
    
    def delete_selected(self):
        """删除选中的记录"""
        indexes = self.history_table.selectedIndexes()
        if not indexes:
            return
        
        reply = QtWidgets.QMessageBox.question(
            self, "确认", 
            "确定要删除选中的记录吗？", 
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, 
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # 获取选中的行
            rows = set()
            for index in indexes:
                rows.add(index.row())
            
            # 从后往前删除行，避免索引变化
            rows = sorted(list(rows), reverse=True)
            
            for row in rows:
                # 获取哈希值
                hash_value = self.history_table.item(row, 2).toolTip()
                
                # 从历史记录中删除
                if self.history_manager:
                    self.history_manager.delete_record(hash_value)
                
                # 从表格中删除
                self.history_table.removeRow(row)

class DictManagerDialog(BaseDialog):
    """字典管理对话框"""
    
    def __init__(self, parent=None):
        """初始化对话框
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("字典管理")
        self.resize(800, 500)
        
        # 创建内容布局
        content_layout = QtWidgets.QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        
        # 选项卡小部件
        self.tab_widget = QtWidgets.QTabWidget()
        
        # 本地字典选项卡
        local_tab = QtWidgets.QWidget()
        local_layout = QtWidgets.QVBoxLayout(local_tab)
        
        # 创建表格
        self.dict_table = QtWidgets.QTableWidget()
        self.dict_table.setColumnCount(4)
        self.dict_table.setHorizontalHeaderLabels(["字典名称", "大小", "路径", "操作"])
        self.dict_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.dict_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.dict_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.dict_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.dict_table.verticalHeader().setVisible(False)
        self.dict_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.dict_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        # 添加双击事件
        self.dict_table.cellDoubleClicked.connect(self.apply_local_dict_on_double_click)
        # 添加右键菜单
        self.dict_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.dict_table.customContextMenuRequested.connect(self.show_local_context_menu)
        local_layout.addWidget(self.dict_table)
        
        # 本地字典操作按钮
        local_btn_layout = QtWidgets.QHBoxLayout()
        
        add_dict_btn = QtWidgets.QPushButton("添加字典")
        add_dict_btn.clicked.connect(self.add_local_dict)
        local_btn_layout.addWidget(add_dict_btn)
        
        remove_btn = QtWidgets.QPushButton("移除字典")
        remove_btn.clicked.connect(self.remove_local_dict)
        local_btn_layout.addWidget(remove_btn)
        
        view_dict_btn = QtWidgets.QPushButton("查看内容")
        view_dict_btn.clicked.connect(self.view_dict_content)
        local_btn_layout.addWidget(view_dict_btn)
        
        local_btn_layout.addStretch()
        
        local_layout.addLayout(local_btn_layout)
        
        # 字典生成器选项卡
        generator_tab = QtWidgets.QWidget()
        generator_layout = QtWidgets.QVBoxLayout(generator_tab)
        gen_form = QtWidgets.QFormLayout()
        self.gen_prefix = QtWidgets.QLineEdit()
        self.gen_prefix.setPlaceholderText("可选，前缀")
        gen_form.addRow("前缀:", self.gen_prefix)
        self.gen_charset = QtWidgets.QLineEdit()
        self.gen_charset.setPlaceholderText("如: abcdefghijklmnopqrstuvwxyz0123456789")
        gen_form.addRow("字符集:", self.gen_charset)
        # 新增：长度区间
        len_layout = QtWidgets.QHBoxLayout()
        self.gen_min_length = QtWidgets.QSpinBox()
        self.gen_min_length.setRange(1, 16)
        self.gen_min_length.setValue(6)
        self.gen_max_length = QtWidgets.QSpinBox()
        self.gen_max_length.setRange(1, 16)
        self.gen_max_length.setValue(8)
        len_layout.addWidget(QtWidgets.QLabel("最小"))
        len_layout.addWidget(self.gen_min_length)
        len_layout.addWidget(QtWidgets.QLabel("最大"))
        len_layout.addWidget(self.gen_max_length)
        gen_form.addRow("长度区间:", len_layout)
        self.gen_suffix = QtWidgets.QLineEdit()
        self.gen_suffix.setPlaceholderText("可选，后缀")
        gen_form.addRow("后缀:", self.gen_suffix)
        # 新增：词根导入
        root_layout = QtWidgets.QHBoxLayout()
        self.gen_root_path = QtWidgets.QLineEdit()
        self.gen_root_path.setPlaceholderText("可选，导入词根txt")
        root_btn = QtWidgets.QPushButton("导入")
        def import_roots():
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择词根文件", "", "文本文件 (*.txt)")
            if path:
                self.gen_root_path.setText(path)
        root_btn.clicked.connect(import_roots)
        root_layout.addWidget(self.gen_root_path)
        root_layout.addWidget(root_btn)
        gen_form.addRow("词根:", root_layout)
        # 新增：常用模板
        self.gen_template = QtWidgets.QComboBox()
        self.gen_template.addItems(["无", "手机号", "生日(8位)", "姓名+数字", "邮箱前缀+数字"])
        gen_form.addRow("模板:", self.gen_template)
        # 新增：大小写变换
        self.case_combo = QtWidgets.QComboBox()
        self.case_combo.addItems(["无", "全小写", "全大写", "首字母大写", "大小写混合"])
        gen_form.addRow("大小写:", self.case_combo)
        # 新增：预览条数
        self.preview_count = QtWidgets.QSpinBox()
        self.preview_count.setRange(10, 1000)
        self.preview_count.setValue(100)
        gen_form.addRow("预览条数:", self.preview_count)
        generator_layout.addLayout(gen_form)
        self.gen_preview = QtWidgets.QTextEdit()
        self.gen_preview.setReadOnly(True)
        self.gen_preview.setPlaceholderText("生成的字典预览（最多显示N条）")
        generator_layout.addWidget(self.gen_preview)
        btn_layout = QtWidgets.QHBoxLayout()
        self.gen_btn = QtWidgets.QPushButton("生成预览")
        self.save_btn = QtWidgets.QPushButton("保存字典")
        btn_layout.addWidget(self.gen_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addStretch()
        generator_layout.addLayout(btn_layout)
        self.gen_btn.clicked.connect(self._on_generate_dict)
        self.save_btn.clicked.connect(self._on_save_dict)
        self.tab_widget.addTab(local_tab, "本地字典")
        self.tab_widget.addTab(generator_tab, "字典生成器")
        
        # 在线字典选项卡
        online_tab = QtWidgets.QWidget()
        online_layout = QtWidgets.QVBoxLayout(online_tab)
        
        # 添加提示标签
        hint_label = QtWidgets.QLabel("提示: 双击字典行可以直接下载字典")
        hint_label.setStyleSheet("color: #0078D7; font-style: italic;")
        online_layout.addWidget(hint_label)
        
        # 在线字典表格
        self.online_table = QtWidgets.QTableWidget()
        self.online_table.setColumnCount(7)  # 增加一列显示是否已下载
        self.online_table.setHorizontalHeaderLabels(["字典名称", "大小", "描述", "下载", "操作", "说明", "复制地址"])
        self.online_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.online_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.online_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.online_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.online_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        self.online_table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        self.online_table.horizontalHeader().setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
        self.online_table.verticalHeader().setVisible(False)
        self.online_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.online_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        # 添加双击事件处理器
        self.online_table.cellDoubleClicked.connect(self.apply_dict_on_double_click)
        # 添加右键菜单
        self.online_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.online_table.customContextMenuRequested.connect(self.show_online_context_menu)
        # 设置工具提示
        self.online_table.setToolTip("双击行可直接应用字典到路径，右键点击可下载字典")
        online_layout.addWidget(self.online_table)
        
        # 修改提示标签
        hint_label.setText("提示: 双击字典行可应用到字典路径，右键点击可下载字典")
        
        # 在线字典操作按钮
        online_btn_layout = QtWidgets.QHBoxLayout()
        
        refresh_btn = QtWidgets.QPushButton("刷新列表")
        refresh_btn.clicked.connect(self.refresh_online_dicts)
        online_btn_layout.addWidget(refresh_btn)
        
        online_btn_layout.addStretch()
        
        online_layout.addLayout(online_btn_layout)
        
        # 添加选项卡
        self.tab_widget.addTab(local_tab, "本地字典")
        self.tab_widget.addTab(online_tab, "在线字典")
        
        content_layout.addWidget(self.tab_widget)
        
        # 添加内容到主布局
        self.main_layout.addLayout(content_layout)
        
        # 加载字典
        self.load_local_dicts()
        self.load_online_dicts()
    
    def load_local_dicts(self):
        """加载本地字典"""
        # 清空表格
        self.dict_table.setRowCount(0)
        
        # 默认字典目录
        dict_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionaries")
        if not os.path.exists(dict_dir):
            os.makedirs(dict_dir)
        
        # 搜索字典文件
        dict_files = []
        for root, dirs, files in os.walk(dict_dir):
            for file in files:
                if file.endswith(".txt") or file.endswith(".dict"):
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path)
                    dict_files.append((file, file_size, file_path))
        
        # 添加到表格
        for dict_file in dict_files:
            row = self.dict_table.rowCount()
            self.dict_table.insertRow(row)
            
            # 字典名称 (第0列)
            self.dict_table.setItem(row, 0, QtWidgets.QTableWidgetItem(dict_file[0]))
            
            # 文件大小 (第1列)
            size_str = self.format_size(dict_file[1])
            self.dict_table.setItem(row, 1, QtWidgets.QTableWidgetItem(size_str))
            
            # 路径 (第2列)
            self.dict_table.setItem(row, 2, QtWidgets.QTableWidgetItem(dict_file[2]))
            
            # 操作按钮 (第3列)
            # 不在这里添加，留空
    
    def format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def load_online_dicts(self):
        """加载在线字典列表"""
        # 清空表格
        self.online_table.setRowCount(0)

        # 集成可用的在线字典和需要手动网页下载的大型字典
        online_dicts = [
            # 可直接下载
            ("rockyou.txt", "著名的密码泄露字典，包含1400万个常见密码", "60.5 MB", "direct", "https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt"),
            ("500-worst-passwords.txt", "500个最弱密码", "20 KB", "direct", "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/500-worst-passwords.txt"),
            ("default-passwords.txt", "设备/服务默认密码", "7 KB", "direct", "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Default-Credentials/default-passwords.txt"),
            # 需要网页下载
            ("CrackStation.txt", "1.5亿密码，超大字典，需手动网页下载", "15 GB", "web", "https://crackstation.net/buy-crackstation-wordlist-password-cracking-dictionary.htm"),
            ("Weakpass 字典集", "多种超大字典，需手动网页下载", "多种", "web", "https://weakpass.com/wordlist"),
        ]

        # 默认字典目录
        dict_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionaries")

        # 设置表头标签
        self.online_table.setColumnCount(7)
        self.online_table.setHorizontalHeaderLabels(["字典名称", "大小", "描述", "下载", "操作", "说明", "复制地址"])

        for dict_info in online_dicts:
            name, size, desc, dtype, url = dict_info
            row = self.online_table.rowCount()
            self.online_table.insertRow(row)
            self.online_table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
            self.online_table.setItem(row, 1, QtWidgets.QTableWidgetItem(size))
            self.online_table.setItem(row, 2, QtWidgets.QTableWidgetItem(desc))
            # 下载状态
            file_name = os.path.basename(name)
            is_downloaded = os.path.exists(os.path.join(dict_dir, file_name)) if dtype == "direct" else False
            status_text = "已下载" if is_downloaded else ("未下载" if dtype == "direct" else "需网页下载")
            downloaded_item = QtWidgets.QTableWidgetItem(status_text)
            downloaded_item.setTextAlignment(QtCore.Qt.AlignCenter)
            if is_downloaded:
                downloaded_item.setForeground(QtGui.QColor("#00CC00"))
            elif dtype == "web":
                downloaded_item.setForeground(QtGui.QColor("#0078D7"))
            else:
                downloaded_item.setForeground(QtGui.QColor("#888888"))
            self.online_table.setItem(row, 3, downloaded_item)
            # 操作按钮
            op_btn = QtWidgets.QPushButton("下载" if dtype == "direct" else "网页下载")
            def make_download_func(url=url, dtype=dtype, name=name):
                if dtype == "direct":
                    return lambda: self.start_direct_download(url, name)
                else:
                    import webbrowser
                    return lambda: webbrowser.open(url)
            op_btn.clicked.connect(make_download_func())
            self.online_table.setCellWidget(row, 4, op_btn)
            # 说明列
            explain_item = QtWidgets.QTableWidgetItem("需要魔法" if dtype == "direct" else "-")
            explain_item.setTextAlignment(QtCore.Qt.AlignCenter)
            explain_item.setForeground(QtGui.QColor("#FF9800" if dtype == "direct" else "#888888"))
            self.online_table.setItem(row, 5, explain_item)
            # 复制地址按钮
            copy_btn = QtWidgets.QPushButton("复制地址")
            def make_copy_func(url=url):
                return lambda: self.copy_to_clipboard(url)
            copy_btn.clicked.connect(make_copy_func())
            self.online_table.setCellWidget(row, 6, copy_btn)

    def copy_to_clipboard(self, text):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(text)
        QtWidgets.QMessageBox.information(self, "复制成功", "下载地址已复制到剪贴板！")
    
    def start_direct_download(self, url, name):
        """直接下载字典文件"""
        import urllib.request
        dict_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionaries")
        if not os.path.exists(dict_dir):
            os.makedirs(dict_dir)
        save_path = os.path.join(dict_dir, os.path.basename(name))
        progress_dialog = QtWidgets.QProgressDialog(f"正在下载字典 {name}...", "取消", 0, 100, self)
        progress_dialog.setWindowTitle("下载中")
        progress_dialog.setAutoClose(True)
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setFixedWidth(380)
        def do_download():
            try:
                urllib.request.urlretrieve(url, save_path)
                QtCore.QMetaObject.invokeMethod(progress_dialog, "setValue", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(int, 100))
                QtWidgets.QMessageBox.information(self, "下载成功", f"字典 {name} 已下载完成")
                self.load_local_dicts()
                self.load_online_dicts()
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "下载失败", f"下载失败: {e}")
            finally:
                progress_dialog.close()
        import threading
        threading.Thread(target=do_download, daemon=True).start()
        progress_dialog.show()
    
    def add_local_dict(self):
        """添加本地字典"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择字典文件", "", "文本文件 (*.txt);;字典文件 (*.dict);;所有文件 (*)"
        )
        
        if file_path:
            # 默认字典目录
            dict_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionaries")
            if not os.path.exists(dict_dir):
                os.makedirs(dict_dir)
            
            # 复制文件到字典目录
            import shutil
            try:
                file_name = os.path.basename(file_path)
                dest_path = os.path.join(dict_dir, file_name)
                shutil.copy2(file_path, dest_path)
                
                show_info_dialog(self, "字典文件已添加: {}".format(file_name), title="成功")
                
                # 刷新列表
                self.load_local_dicts()
            except Exception as e:
                show_error_dialog(self, "添加字典失败", detail=str(e))
    
    def remove_local_dict(self):
        """删除本地字典"""
        selected_rows = self.dict_table.selectedIndexes()
        if not selected_rows:
            show_error_dialog(self, "请先选择要删除的字典", title="警告")
            return
        
        # 获取选中的行
        row = selected_rows[0].row()
        dict_name = self.dict_table.item(row, 0).text()
        dict_path = self.dict_table.item(row, 2).text()
        
        # 确认删除
        reply = QtWidgets.QMessageBox.question(
            self, "确认删除", f"确定要删除字典 {dict_name} 吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                os.remove(dict_path)
                
                show_info_dialog(self, f"字典已删除: {dict_name}", title="成功")
                
                # 刷新列表
                self.load_local_dicts()
            except Exception as e:
                show_error_dialog(self, "删除字典失败", detail=str(e))
    
    def view_dict_content(self):
        """查看字典内容"""
        selected_rows = self.dict_table.selectedIndexes()
        if not selected_rows:
            show_error_dialog(self, "请先选择要查看的字典", title="警告")
            return
        
        # 获取选中的行
        row = selected_rows[0].row()
        dict_name = self.dict_table.item(row, 0).text()
        dict_path = self.dict_table.item(row, 2).text()
        
        # 创建查看对话框
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"查看字典 - {dict_name}")
        dialog.resize(600, 400)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # 字典内容文本框
        content_text = QtWidgets.QTextEdit()
        content_text.setReadOnly(True)
        layout.addWidget(content_text)
        
        # 加载字典内容
        try:
            with open(dict_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 只读取前10000行，避免过大的文件
                lines = []
                for i, line in enumerate(f):
                    if i >= 10000:
                        lines.append("...(更多内容省略)...")
                        break
                    lines.append(line.strip())
                
                content_text.setText("\n".join(lines))
        except Exception as e:
            content_text.setText(f"读取字典内容失败: {str(e)}")
        
        # 关闭按钮
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        # 显示对话框
        dialog.exec_()
    
    def download_dict(self):
        """下载在线字典"""
        selected_rows = self.online_table.selectedIndexes()
        if not selected_rows:
            show_error_dialog(self, "请先选择要下载的字典", title="警告")
            return
        
        # 获取选中的行
        row = selected_rows[0].row()
        dict_name = self.online_table.item(row, 0).text()
        
        # 确认下载
        reply = QtWidgets.QMessageBox.question(
            self, "下载确认", 
            f"确定要下载字典 {dict_name} 吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # 开始下载
            self.start_dict_download(dict_name)
    
    def download_dict_on_double_click(self, row, column):
        """处理在线字典表格的双击事件，下载选中的字典
        
        Args:
            row: 点击的行
            column: 点击的列
        """
        if row >= 0 and row < self.online_table.rowCount():
            # 获取点击的字典名称
            dict_name = self.online_table.item(row, 0).text()
            
            # 确认下载
            reply = QtWidgets.QMessageBox.question(
                self, "下载确认", 
                f"确定要下载字典 {dict_name} 吗？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                # 开始下载
                self.start_dict_download(dict_name)



    def start_dict_download(self, dict_name):
        """开始下载字典
        
        Args:
            dict_name: 要下载的字典名称
        """
        # 下载目录
        dict_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionaries")
        if not os.path.exists(dict_dir):
            os.makedirs(dict_dir)
        
        # 获取文件名（去掉可能的路径前缀）
        filename = os.path.basename(dict_name)
        save_path = os.path.join(dict_dir, filename)
        
        # 显示下载进度对话框
        progress_dialog = QtWidgets.QProgressDialog(f"正在下载字典 {filename}...", "取消", 0, 100, self)
        progress_dialog.setWindowTitle("下载中")
        progress_dialog.setAutoClose(True)
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setFixedWidth(380)  # 设置固定宽度为380px
        
        # 定义多个可能的下载源，优先使用国内镜像
        download_sources = [
            # 国内加速镜像
            f"https://ghproxy.com/https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/{dict_name}",
            f"https://gh.api.99988866.xyz/https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/{dict_name}",
            f"https://raw.staticdn.net/danielmiessler/SecLists/master/Passwords/{dict_name}",
            # jsdelivr镜像
            f"https://cdn.jsdelivr.net/gh/danielmiessler/SecLists/Passwords/{dict_name}",
            f"https://fastly.jsdelivr.net/gh/danielmiessler/SecLists/Passwords/{dict_name}",
            # GitHub原始链接
            f"https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/{dict_name}",
        ]
        
        # 创建自定义下载线程
        download_thread = DownloadThreadWithRetry(download_sources, save_path, max_retries=3)
        
        # 连接信号
        download_thread.progress_signal.connect(progress_dialog.setValue)
        download_thread.status_signal.connect(lambda msg: progress_dialog.setLabelText(msg))
        download_thread.finished_signal.connect(lambda success, msg: self.on_dict_download_finished(success, msg, filename, progress_dialog))
        
        # 处理取消按钮
        progress_dialog.canceled.connect(download_thread.cancel)
        
        # 显示对话框并启动线程
        progress_dialog.show()
        download_thread.start()
        
        # 保存线程引用，避免垃圾回收
        self.download_thread = download_thread
    
    def on_dict_download_finished(self, success, message, dict_name, progress_dialog):
        """字典下载完成回调"""
        # 关闭进度对话框
        progress_dialog.close()
        
        if success:
            QtWidgets.QMessageBox.information(self, "下载成功", f"字典 {dict_name} 已下载完成")
            
            # 刷新列表
            self.load_local_dicts()
            # 刷新在线字典列表，更新已下载状态
            self.load_online_dicts()
        else:
            # 显示下载失败对话框，提供重试选项
            retry_box = QtWidgets.QMessageBox(self)
            retry_box.setWindowTitle("下载失败")
            retry_box.setIcon(QtWidgets.QMessageBox.Warning)
            retry_box.setText(f"下载失败: {message}")
            retry_box.setInformativeText("是否要重试下载?")
            
            retry_button = retry_box.addButton("重试", QtWidgets.QMessageBox.AcceptRole)
            cancel_button = retry_box.addButton("取消", QtWidgets.QMessageBox.RejectRole)
            
            retry_box.exec_()
            
            if retry_box.clickedButton() == retry_button:
                # 重新开始下载
                self.start_dict_download(dict_name)
    
    def refresh_online_dicts(self):
        """刷新在线字典列表"""
        self.load_online_dicts()
        show_info_dialog(self, "在线字典列表已刷新", title="刷新完成")
    
    def show_online_context_menu(self, position):
        """显示在线字典表格的右键菜单
        
        Args:
            position: 鼠标位置
        """
        menu = QtWidgets.QMenu()
        
        # 获取选中的行
        indexes = self.online_table.selectedIndexes()
        if not indexes:
            return
        
        row = indexes[0].row()
        dict_name = self.online_table.item(row, 0).text()
        is_downloaded = self.online_table.item(row, 3).text() == "已下载"
        
        # 下载字典选项
        download_action = menu.addAction("下载字典")
        download_action.triggered.connect(lambda: self.download_dict_from_context(row))
        if is_downloaded:
            download_action.setEnabled(False)  # 如果已下载，禁用此选项
        
        # 应用字典选项
        apply_action = menu.addAction("应用到字典路径")
        apply_action.triggered.connect(lambda: self.apply_dict_to_path(row))
        if not is_downloaded:
            apply_action.setEnabled(False)  # 如果未下载，禁用此选项
        
        # 显示菜单
        menu.exec_(self.online_table.viewport().mapToGlobal(position))
    
    def download_dict_from_context(self, row):
        """从右键菜单下载字典
        
        Args:
            row: 表格行
        """
        if row >= 0 and row < self.online_table.rowCount():
            # 获取字典名称
            dict_name = self.online_table.item(row, 0).text()
            
            # 开始下载
            self.start_dict_download(dict_name)
    
    def apply_dict_to_path(self, row):
        """将字典应用到路径
        
        Args:
            row: 表格行
        """
        if row >= 0 and row < self.online_table.rowCount():
            # 获取字典名称
            dict_name = self.online_table.item(row, 0).text()
            
            # 默认字典目录
            dict_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionaries")
            file_name = os.path.basename(dict_name)
            dict_path = os.path.join(dict_dir, file_name)
            
            # 检查字典是否已下载
            if os.path.exists(dict_path):
                # 设置选中的路径并关闭对话框
                self.selected_dict_path = dict_path
                self.accept()
            else:
                # 提示用户下载字典
                reply = QtWidgets.QMessageBox.question(
                    self, "字典未下载", 
                    f"字典 {file_name} 尚未下载，是否现在下载?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.Yes
                )
                
                if reply == QtWidgets.QMessageBox.Yes:
                    # 开始下载
                    self.start_dict_download(dict_name)
    
    def apply_dict_on_double_click(self, row, column):
        """处理在线字典表格的双击事件，应用选中的字典到路径
        
        Args:
            row: 点击的行
            column: 点击的列
        """
        # 调用应用字典到路径方法
        self.apply_dict_to_path(row)

    def get_selected_dict_path(self):
        """获取选中的字典路径，供外部调用"""
        return getattr(self, 'selected_dict_path', None)
    
    def apply_local_dict_on_double_click(self, row, column):
        """处理本地字典表格的双击事件，应用选中的字典到路径
        
        Args:
            row: 点击的行
            column: 点击的列
        """
        # 确保行索引有效
        if row >= 0 and row < self.dict_table.rowCount():
            # 获取字典路径
            dict_path = self.dict_table.item(row, 2).text()
            
            # 检查文件是否存在
            if os.path.exists(dict_path):
                # 设置选中的路径并关闭对话框
                self.selected_dict_path = dict_path
                self.accept()
            else:
                # 如果文件不存在，显示警告
                show_error_dialog(self, f"字典文件 {os.path.basename(dict_path)} 不存在或已被移动/删除", title="文件不存在")
                # 刷新字典列表
                self.load_local_dicts()
    
    def apply_local_dict(self, row):
        """应用本地字典到路径
        
        Args:
            row: 表格行
        """
        if row >= 0 and row < self.dict_table.rowCount():
            # 获取字典路径
            dict_path = self.dict_table.item(row, 2).text()
            
            # 检查文件是否存在
            if os.path.exists(dict_path):
                # 设置选中的路径并关闭对话框
                self.selected_dict_path = dict_path
                self.accept()
            else:
                # 如果文件不存在，显示警告
                show_error_dialog(self, f"字典文件 {os.path.basename(dict_path)} 不存在或已被移动/删除", title="文件不存在")
                # 刷新字典列表
                self.load_local_dicts()
    
    def show_local_context_menu(self, position):
        """显示本地字典表格的右键菜单
        
        Args:
            position: 鼠标位置
        """
        menu = QtWidgets.QMenu()
        
        # 获取选中的行
        indexes = self.dict_table.selectedIndexes()
        if not indexes:
            return
        
        row = indexes[0].row()
        dict_name = self.dict_table.item(row, 0).text()
        dict_path = self.dict_table.item(row, 2).text()
        
        # 应用字典选项
        apply_action = menu.addAction("应用到字典路径")
        apply_action.triggered.connect(lambda: self.apply_local_dict(row))
        
        # 查看内容选项
        view_action = menu.addAction("查看内容")
        view_action.triggered.connect(lambda: self.view_dict_content_by_row(row))
        
        # 移除字典选项
        remove_action = menu.addAction("移除字典")
        remove_action.triggered.connect(lambda: self.remove_local_dict_by_row(row))
        
        # 显示菜单
        menu.exec_(self.dict_table.viewport().mapToGlobal(position))
    
    def view_dict_content_by_row(self, row):
        """根据行号查看字典内容
        
        Args:
            row: 表格行
        """
        if row >= 0 and row < self.dict_table.rowCount():
            # 调用原有的查看字典内容方法
            self.dict_table.selectRow(row)
            self.view_dict_content()
    
    def remove_local_dict_by_row(self, row):
        """根据行号删除本地字典
        
        Args:
            row: 表格行
        """
        if row >= 0 and row < self.dict_table.rowCount():
            # 调用原有的删除字典方法
            self.dict_table.selectRow(row)
            self.remove_local_dict()

    def _on_generate_dict(self):
        """生成字典预览（专业版）"""
        from itertools import product
        prefix = self.gen_prefix.text()
        charset = self.gen_charset.text()
        if not charset:
            show_error_dialog(self, "字符集不能为空！", title="警告")
            return
        min_len = self.gen_min_length.value()
        max_len = self.gen_max_length.value()
        suffix = self.gen_suffix.text()
        template = self.gen_template.currentText()
        case_mode = self.case_combo.currentText()
        preview_limit = self.preview_count.value()
        roots = []
        if self.gen_root_path.text():
            try:
                with open(self.gen_root_path.text(), "r", encoding="utf-8") as f:
                    roots = [line.strip() for line in f if line.strip()]
            except Exception:
                roots = []
        results = []
        def apply_case(word):
            if case_mode == "全小写":
                return word.lower()
            elif case_mode == "全大写":
                return word.upper()
            elif case_mode == "首字母大写":
                return word.capitalize()
            elif case_mode == "大小写混合":
                return [word.lower(), word.upper(), word.capitalize()]
            return word
        def add_result(word):
            if isinstance(word, list):
                for w in word:
                    results.append(w)
                    if len(results) >= preview_limit:
                        return True
            else:
                results.append(word)
                if len(results) >= preview_limit:
                    return True
            return False
        # 专业模板处理
        if template == "手机号":
            count = 0
            for p in ["13", "15", "17", "18", "19"]:
                for i in range(100000000, 1000000000):
                    word = p + str(i)
                    if add_result(apply_case(word)):
                        break
                    count += 1
                    if count >= preview_limit:
                        break
                if count >= preview_limit:
                    break
        elif template == "生日(8位)":
            count = 0
            for y in range(1970, 2024):
                for m in range(1, 13):
                    for d in range(1, 32):
                        word = f"{y:04d}{m:02d}{d:02d}"
                        if add_result(apply_case(word)):
                            break
                        count += 1
                        if count >= preview_limit:
                            break
                    if count >= preview_limit:
                        break
                if count >= preview_limit:
                    break
        elif template == "姓名+数字":
            if not roots:
                roots = ["zhangsan", "lisi", "wangwu"]
            for name in roots:
                for n in range(100):
                    word = f"{name}{n:02d}"
                    if add_result(apply_case(word)):
                        break
                if len(results) >= preview_limit:
                    break
        elif template == "邮箱前缀+数字":
            if not roots:
                roots = ["user", "admin", "test"]
            for name in roots:
                for n in range(1000):
                    word = f"{name}{n:03d}"
                    if add_result(apply_case(word)):
                        break
                if len(results) >= preview_limit:
                    break
        else:
            # 普通排列组合
            if roots:
                for root in roots:
                    for l in range(min_len, max_len+1):
                        for tup in product(charset, repeat=l):
                            word = prefix + root + ''.join(tup) + suffix
                            if add_result(apply_case(word)):
                                break
                        if len(results) >= preview_limit:
                            break
                    if len(results) >= preview_limit:
                        break
            else:
                for l in range(min_len, max_len+1):
                    for tup in product(charset, repeat=l):
                        word = prefix + ''.join(tup) + suffix
                        if add_result(apply_case(word)):
                            break
                    if len(results) >= preview_limit:
                        break
        self.gen_preview.setPlainText('\n'.join(results) + (f"\n...（仅预览前{preview_limit}条）" if len(results) == preview_limit else ""))

    def _on_save_dict(self):
        """保存生成的字典到txt文件（专业版）"""
        logger = logging.getLogger("zipcracker")
        try:
            from itertools import product
            prefix = self.gen_prefix.text()
            charset = self.gen_charset.text()
            if not charset:
                QtWidgets.QMessageBox.warning(self, "警告", "字符集不能为空！")
                return
            min_len = self.gen_min_length.value()
            max_len = self.gen_max_length.value()
            suffix = self.gen_suffix.text()
            template = self.gen_template.currentText()
            case_mode = self.case_combo.currentText()
            roots = []
            if self.gen_root_path.text():
                try:
                    with open(self.gen_root_path.text(), "r", encoding="utf-8") as f:
                        roots = [line.strip() for line in f if line.strip()]
                except Exception:
                    roots = []
            save_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存字典", "custom_dict.txt", "文本文件 (*.txt);;所有文件 (*)")
            if not save_path:
                return
            def apply_case(word):
                if case_mode == "全小写":
                    return word.lower()
                elif case_mode == "全大写":
                    return word.upper()
                elif case_mode == "首字母大写":
                    return word.capitalize()
                elif case_mode == "大小写混合":
                    return [word.lower(), word.upper(), word.capitalize()]
                return word
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    # 专业模板处理
                    if template == "手机号":
                        count = 0
                        for p in ["13", "15", "17", "18", "19"]:
                            for i in range(100000000, 1000000000):
                                word = p + str(i)
                                w = apply_case(word)
                                if isinstance(w, list):
                                    for ww in w:
                                        f.write(ww + "\n")
                                        count += 1
                                        if count >= 100000:  # 限制最大写入条数
                                            break
                                else:
                                    f.write(w + "\n")
                                    count += 1
                                    if count >= 100000:
                                        break
                                if count >= 100000:
                                    break
                            if count >= 100000:
                                break
                    elif template == "生日(8位)":
                        for y in range(1970, 2024):
                            for m in range(1, 13):
                                for d in range(1, 32):
                                    word = f"{y:04d}{m:02d}{d:02d}"
                                    w = apply_case(word)
                                    if isinstance(w, list):
                                        for ww in w:
                                            f.write(ww + "\n")
                                    else:
                                        f.write(w + "\n")
                    elif template == "姓名+数字":
                        if not roots:
                            roots = ["zhangsan", "lisi", "wangwu"]
                        for name in roots:
                            for n in range(100):
                                word = f"{name}{n:02d}"
                                w = apply_case(word)
                                if isinstance(w, list):
                                    for ww in w:
                                        f.write(ww + "\n")
                                else:
                                    f.write(w + "\n")
                    elif template == "邮箱前缀+数字":
                        if not roots:
                            roots = ["user", "admin", "test"]
                        for name in roots:
                            for n in range(1000):
                                word = f"{name}{n:03d}"
                                w = apply_case(word)
                                if isinstance(w, list):
                                    for ww in w:
                                        f.write(ww + "\n")
                                else:
                                    f.write(w + "\n")
                    else:
                        # 普通排列组合
                        if roots:
                            for root in roots:
                                for l in range(min_len, max_len+1):
                                    for tup in product(charset, repeat=l):
                                        word = prefix + root + ''.join(tup) + suffix
                                        w = apply_case(word)
                                        if isinstance(w, list):
                                            for ww in w:
                                                f.write(ww + "\n")
                                        else:
                                            f.write(w + "\n")
                        else:
                            for l in range(min_len, max_len+1):
                                for tup in product(charset, repeat=l):
                                    word = prefix + ''.join(tup) + suffix
                                    w = apply_case(word)
                                    if isinstance(w, list):
                                        for ww in w:
                                            f.write(ww + "\n")
                                    else:
                                        f.write(w + "\n")
                QtWidgets.QMessageBox.information(self, "保存成功", f"字典已保存到: {save_path}")
            except Exception as e:
                logger.error(f"保存字典失败: {e}")
                show_error_dialog(self, "保存字典失败", detail=str(e))
        except Exception as e:
            logger.error(f"保存字典失败: {e}")
            show_error_dialog(self, "保存字典失败", detail=str(e))

class PerformanceSettingsDialog(BaseDialog):
    """性能设置对话框"""
    
    def __init__(self, parent=None):
        """初始化对话框
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("性能设置")
        self.resize(500, 400)
        
        # 设置布局
        content_layout = QtWidgets.QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        
        # 添加说明标签
        desc_label = QtWidgets.QLabel("调整性能参数以优化破解速度和资源使用:")
        desc_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(desc_label)
        
        # GPU设置
        gpu_group = QtWidgets.QGroupBox("GPU设置")
        gpu_layout = QtWidgets.QVBoxLayout(gpu_group)
        
        # 使用GPU复选框
        self.use_gpu_check = QtWidgets.QCheckBox("启用GPU加速")
        self.use_gpu_check.setChecked(True)
        gpu_layout.addWidget(self.use_gpu_check)
        
        # GPU设备选择
        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.addItem("检测中...")
        self.device_combo.setEnabled(True)
        
        # 添加可用GPU设备
        self.detect_gpus()
        
        device_layout = QtWidgets.QHBoxLayout()
        device_layout.addWidget(QtWidgets.QLabel("GPU设备:"))
        device_layout.addWidget(self.device_combo)
        gpu_layout.addLayout(device_layout)
        
        # GPU工作负载
        self.workload_combo = QtWidgets.QComboBox()
        self.workload_combo.addItems(["低 (运行其他任务时使用)", "默认", "高 (仅用于破解)", "极高 (可能会冻结系统)"])
        self.workload_combo.setCurrentIndex(1)  # 默认设置
        
        workload_layout = QtWidgets.QHBoxLayout()
        workload_layout.addWidget(QtWidgets.QLabel("工作负载:"))
        workload_layout.addWidget(self.workload_combo)
        gpu_layout.addLayout(workload_layout)
        
        # 将GPU组添加到主布局
        content_layout.addWidget(gpu_group)
        
        # CPU设置
        cpu_group = QtWidgets.QGroupBox("CPU设置")
        cpu_layout = QtWidgets.QVBoxLayout(cpu_group)
        
        # 线程数设置
        thread_layout = QtWidgets.QHBoxLayout()
        thread_label = QtWidgets.QLabel("线程数:")
        thread_layout.addWidget(thread_label)
        
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        
        self.thread_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.thread_slider.setMinimum(1)
        self.thread_slider.setMaximum(cpu_count)
        self.thread_slider.setValue(cpu_count // 2)
        self.thread_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.thread_slider.setTickInterval(1)
        self.thread_slider.valueChanged.connect(self.update_thread_label)
        thread_layout.addWidget(self.thread_slider)
        
        self.thread_value_label = QtWidgets.QLabel(f"{cpu_count // 2}")
        thread_layout.addWidget(self.thread_value_label)
        
        cpu_layout.addLayout(thread_layout)
        
        # 将CPU组添加到主布局
        content_layout.addWidget(cpu_group)
        
        # 内存设置
        memory_group = QtWidgets.QGroupBox("内存设置")
        memory_layout = QtWidgets.QVBoxLayout(memory_group)
        
        # 内存限制
        memory_limit_layout = QtWidgets.QHBoxLayout()
        memory_limit_label = QtWidgets.QLabel("内存限制:")
        memory_limit_layout.addWidget(memory_limit_label)
        
        self.memory_limit_combo = QtWidgets.QComboBox()
        self.memory_limit_combo.addItems(["256 MB", "512 MB", "1 GB", "2 GB", "4 GB", "8 GB", "不限制"])
        self.memory_limit_combo.setCurrentIndex(2)  # 1 GB
        memory_limit_layout.addWidget(self.memory_limit_combo)
        
        memory_layout.addLayout(memory_limit_layout)
        
        # 将内存组添加到主布局
        content_layout.addWidget(memory_group)
        
        # 其他设置
        other_group = QtWidgets.QGroupBox("其他设置")
        other_layout = QtWidgets.QVBoxLayout(other_group)
        
        # 优化级别
        self.optimization_combo = QtWidgets.QComboBox()
        self.optimization_combo.addItems(["低 (省电模式)", "中等", "高 (最大性能)"])
        self.optimization_combo.setCurrentIndex(1)  # 中等
        
        optimization_layout = QtWidgets.QHBoxLayout()
        optimization_layout.addWidget(QtWidgets.QLabel("优化级别:"))
        optimization_layout.addWidget(self.optimization_combo)
        other_layout.addLayout(optimization_layout)
        
        # 将其他设置组添加到主布局
        content_layout.addWidget(other_group)
        
        # 连接GPU复选框
        self.use_gpu_check.toggled.connect(self.toggle_gpu_settings)
        
        content_layout.addStretch()
        
        # 底部按钮
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        self.default_btn = QtWidgets.QPushButton("恢复默认")
        self.default_btn.clicked.connect(self.restore_defaults)
        btn_layout.addWidget(self.default_btn)
        
        self.save_btn = QtWidgets.QPushButton("保存设置")
        self.save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QtWidgets.QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        content_layout.addLayout(btn_layout)
        
        # 添加内容到主布局
        self.main_layout.addLayout(content_layout)
    
    def detect_gpus(self):
        """检测可用的GPU设备，兼容hashcat路径为文件夹或exe文件，支持多种输出格式，优先显示显卡型号，并输出调试日志"""
        self.device_combo.clear()
        self.device_combo.addItem("CPU (不使用GPU)")
        try:
            import subprocess, re, os
            from zipcracker_config import config
            hashcat_path = config.get("hashcat_path", "")
            # 兼容：如果是文件夹，自动查找hashcat.exe
            if hashcat_path and os.path.isdir(hashcat_path):
                exe_path = os.path.join(hashcat_path, "hashcat.exe")
                if os.path.exists(exe_path):
                    hashcat_path = exe_path
            if hashcat_path and os.path.isfile(hashcat_path):
                try:
                    process = subprocess.run([hashcat_path, "-I"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
                    output = process.stdout
                    # 调试输出
                    try:
                        with open("gpu_detect_debug.txt", "w", encoding="utf-8") as f:
                            f.write(output)
                    except Exception:
                        pass
                    devices = []
                    # 更宽松的正则，兼容所有NVIDIA/AMD显卡行
                    for line in output.splitlines():
                        m = re.search(r'Name.*?:\s*(NVIDIA.*|AMD.*)', line)
                        if m:
                            device_name = m.group(1).strip()
                            if device_name and device_name not in devices:
                                devices.append(device_name)
                    # 如果还没找到，兜底用包含NVIDIA/AMD的行
                    if not devices:
                        for line in output.splitlines():
                            if "NVIDIA" in line or "AMD" in line:
                                devices.append(line.strip())
                    for device in devices:
                        self.device_combo.addItem(device)
                    if devices:
                        self.device_combo.setCurrentIndex(1)
                        return
                except Exception:
                    pass
                # 降级用--benchmark --machine-readable
                try:
                    process = subprocess.run([hashcat_path, "--benchmark", "--machine-readable"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
                    output = process.stdout
                    devices = []
                    for line in output.split("\n"):
                        if "DEVICE_NAME" in line:
                            match = re.search(r'DEVICE_NAME:(.*?)(?:,|$)', line)
                            if match:
                                device_name = match.group(1).strip()
                                devices.append(device_name)
                    for device in devices:
                        self.device_combo.addItem(device)
                    if devices:
                        self.device_combo.setCurrentIndex(1)
                        return
                except Exception:
                    pass
        except Exception as e:
            pass
        # 兜底
        self.device_combo.addItem("NVIDIA GPU")
        self.device_combo.addItem("AMD GPU")
    
    def toggle_gpu_settings(self, enabled):
        """切换GPU设置的启用状态"""
        self.device_combo.setEnabled(enabled)
        self.workload_combo.setEnabled(enabled)
    
    def update_thread_label(self, value):
        """更新线程数标签"""
        self.thread_value_label.setText(str(value))
    
    def restore_defaults(self):
        """恢复默认设置"""
        self.use_gpu_check.setChecked(True)
        self.device_combo.setCurrentIndex(1 if self.device_combo.count() > 1 else 0)
        self.workload_combo.setCurrentIndex(1)
        
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        self.thread_slider.setValue(cpu_count // 2)
        
        self.memory_limit_combo.setCurrentIndex(2)  # 1 GB
        self.optimization_combo.setCurrentIndex(1)  # 中等
    
    def get_settings(self):
        """获取设置
        
        Returns:
            dict: 设置字典
        """
        return {
            "use_gpu": self.use_gpu_check.isChecked(),
            "gpu_device": self.device_combo.currentIndex(),
            "gpu_device_name": self.device_combo.currentText(),
            "workload": self.workload_combo.currentIndex(),
            "threads": self.thread_slider.value(),
            "memory_limit": self.memory_limit_combo.currentText(),
            "optimization": self.optimization_combo.currentIndex()
        }

class DictMergeDialog(BaseDialog):
    """字典合并对话框，用于合并多个字典文件并去除重复项"""
    
    def __init__(self, parent=None):
        """初始化对话框
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("字典合并工具")
        self.resize(650, 500)
        
        # 源字典列表
        self.dict_files = []
        
        # 设置布局
        content_layout = QtWidgets.QVBoxLayout()
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)
        
        # 添加说明标签
        desc_label = QtWidgets.QLabel("选择要合并的字典文件，合并后将自动去除重复项")
        desc_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(desc_label)
        
        # 字典列表区域
        list_group = QtWidgets.QGroupBox("源字典文件")
        list_layout = QtWidgets.QVBoxLayout(list_group)
        
        # 字典列表
        self.dict_list = QtWidgets.QListWidget()
        self.dict_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        list_layout.addWidget(self.dict_list)
        
        # 字典操作按钮
        dict_btn_layout = QtWidgets.QHBoxLayout()
        
        add_btn = QtWidgets.QPushButton("添加字典")
        add_btn.clicked.connect(self.add_dict)
        dict_btn_layout.addWidget(add_btn)
        
        remove_btn = QtWidgets.QPushButton("移除字典")
        remove_btn.clicked.connect(self.remove_dict)
        dict_btn_layout.addWidget(remove_btn)
        
        clear_btn = QtWidgets.QPushButton("清空列表")
        clear_btn.clicked.connect(self.clear_dicts)
        dict_btn_layout.addWidget(clear_btn)
        
        list_layout.addLayout(dict_btn_layout)
        content_layout.addWidget(list_group)
        
        # 输出设置
        output_group = QtWidgets.QGroupBox("输出设置")
        output_layout = QtWidgets.QFormLayout(output_group)
        
        self.output_path_edit = QtWidgets.QLineEdit()
        self.output_path_edit.setPlaceholderText("选择合并后字典的保存路径...")
        
        output_path_layout = QtWidgets.QHBoxLayout()
        output_path_layout.setContentsMargins(0, 0, 0, 0)
        output_path_layout.addWidget(self.output_path_edit)
        
        browse_output_btn = QtWidgets.QPushButton("浏览")
        browse_output_btn.clicked.connect(self.browse_output)
        output_path_layout.addWidget(browse_output_btn)
        
        output_layout.addRow("输出文件:", output_path_layout)
        
        # 字符编码选择
        self.encoding_combo = QtWidgets.QComboBox()
        self.encoding_combo.addItems(["UTF-8", "GBK", "Latin-1", "ASCII"])
        output_layout.addRow("字符编码:", self.encoding_combo)
        
        # 排序选项
        self.sort_check = QtWidgets.QCheckBox("按字母顺序排序")
        self.sort_check.setChecked(True)
        output_layout.addRow("", self.sort_check)
        
        # 大小写选项
        self.case_check = QtWidgets.QCheckBox("忽略大小写(转小写)")
        self.case_check.setChecked(True)
        output_layout.addRow("", self.case_check)
        
        content_layout.addWidget(output_group)
        
        # 进度条和状态
        self.status_label = QtWidgets.QLabel("就绪")
        content_layout.addWidget(self.status_label)
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        content_layout.addWidget(self.progress_bar)
        
        # 操作按钮
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        self.merge_btn = QtWidgets.QPushButton("开始合并")
        self.merge_btn.setProperty("class", "primaryButton")
        self.merge_btn.setMinimumWidth(100)
        self.merge_btn.clicked.connect(self.merge_dicts)
        btn_layout.addWidget(self.merge_btn)
        
        cancel_btn = QtWidgets.QPushButton("关闭")
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        content_layout.addLayout(btn_layout)
        
        # 添加内容到主布局
        self.main_layout.addLayout(content_layout)
    
    def add_dict(self):
        """添加字典文件"""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "选择字典文件", "", "文本文件 (*.txt);;字典文件 (*.dict);;所有文件 (*)"
        )
        
        if files:
            for file_path in files:
                # 检查是否已添加
                if file_path in self.dict_files:
                    continue
                
                # 添加到列表
                self.dict_files.append(file_path)
                item = QtWidgets.QListWidgetItem(os.path.basename(file_path))
                item.setToolTip(file_path)
                self.dict_list.addItem(item)
            
            # 更新状态
            self.status_label.setText(f"已添加 {len(self.dict_files)} 个字典文件")
    
    def remove_dict(self):
        """移除选中的字典文件"""
        selected_items = self.dict_list.selectedItems()
        if not selected_items:
            return
        
        for item in selected_items:
            row = self.dict_list.row(item)
            file_path = self.dict_files[row]
            # 从列表中移除
            self.dict_list.takeItem(row)
            self.dict_files.remove(file_path)
        
        # 更新状态
        self.status_label.setText(f"已添加 {len(self.dict_files)} 个字典文件")
    
    def clear_dicts(self):
        """清空字典列表"""
        self.dict_list.clear()
        self.dict_files.clear()
        self.status_label.setText("已清空字典列表")
    
    def browse_output(self):
        """选择输出文件路径"""
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "选择输出文件", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        
        if file_path:
            self.output_path_edit.setText(file_path)
    
    def merge_dicts(self):
        """合并字典文件"""
        # 检查是否有源字典
        if not self.dict_files:
            QtWidgets.QMessageBox.warning(self, "警告", "请至少添加一个源字典文件")
            return
        
        # 检查是否设置输出路径
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QtWidgets.QMessageBox.warning(self, "警告", "请设置输出文件路径")
            return
        
        # 获取设置
        encoding = self.encoding_combo.currentText()
        sort_words = self.sort_check.isChecked()
        ignore_case = self.case_check.isChecked()
        
        # 禁用界面
        self.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在合并字典...")
        
        # 在线程中执行合并操作
        threading.Thread(
            target=self._merge_thread,
            args=(output_path, encoding, sort_words, ignore_case),
            daemon=True
        ).start()
    
    def _merge_thread(self, output_path, encoding, sort_words, ignore_case):
        """字典合并线程
        
        Args:
            output_path: 输出文件路径
            encoding: 字符编码
            sort_words: 是否排序
            ignore_case: 是否忽略大小写
        """
        try:
            # 读取所有字典并合并去重
            unique_words = set()
            total_files = len(self.dict_files)
            
            for i, file_path in enumerate(self.dict_files):
                try:
                    # 更新进度
                    progress = int((i / total_files) * 50)
                    QtCore.QMetaObject.invokeMethod(
                        self.progress_bar, "setValue", 
                        QtCore.Qt.QueuedConnection, 
                        QtCore.Q_ARG(int, progress)
                    )
                    
                    # 更新状态
                    file_name = os.path.basename(file_path)
                    QtCore.QMetaObject.invokeMethod(
                        self.status_label, "setText", 
                        QtCore.Qt.QueuedConnection, 
                        QtCore.Q_ARG(str, f"正在处理: {file_name}")
                    )
                    
                    # 读取文件
                    with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                        for line in f:
                            word = line.strip()
                            if word:
                                if ignore_case:
                                    word = word.lower()
                                unique_words.add(word)
                except Exception as e:
                    # 更新状态
                    error_msg = f"处理文件 {file_path} 时出错: {str(e)}"
                    QtCore.QMetaObject.invokeMethod(
                        self.status_label, "setText", 
                        QtCore.Qt.QueuedConnection, 
                        QtCore.Q_ARG(str, error_msg)
                    )
                    time.sleep(2)  # 暂停一下让用户看到错误
            
            # 更新进度
            QtCore.QMetaObject.invokeMethod(
                self.progress_bar, "setValue", 
                QtCore.Qt.QueuedConnection, 
                QtCore.Q_ARG(int, 50)
            )
            
            # 更新状态
            QtCore.QMetaObject.invokeMethod(
                self.status_label, "setText", 
                QtCore.Qt.QueuedConnection, 
                QtCore.Q_ARG(str, "正在排序和写入...")
            )
            
            # 转换为列表并排序
            word_list = list(unique_words)
            if sort_words:
                word_list.sort()
            
            # 写入输出文件
            with open(output_path, 'w', encoding=encoding) as f:
                for word in word_list:
                    f.write(word + '\n')
            
            # 更新进度
            QtCore.QMetaObject.invokeMethod(
                self.progress_bar, "setValue", 
                QtCore.Qt.QueuedConnection, 
                QtCore.Q_ARG(int, 100)
            )
            
            # 更新状态
            final_msg = f"合并完成! 共 {len(word_list)} 个唯一密码"
            QtCore.QMetaObject.invokeMethod(
                self.status_label, "setText", 
                QtCore.Qt.QueuedConnection, 
                QtCore.Q_ARG(str, final_msg)
            )
            
            # 显示成功消息
            QtCore.QMetaObject.invokeMethod(
                show_info_dialog,
                "__call__",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(object, self),
                QtCore.Q_ARG(str, f"字典合并完成!\n\n共处理 {total_files} 个文件\n输出 {len(word_list)} 个唯一密码\n已保存到: {output_path}"),
                QtCore.Q_ARG(str, None),
                QtCore.Q_ARG(str, None),
                QtCore.Q_ARG(str, "成功")
            )
            
        except Exception as e:
            # 显示错误
            error_msg = f"字典合并失败: {str(e)}"
            QtCore.QMetaObject.invokeMethod(
                self.status_label, "setText", 
                QtCore.Qt.QueuedConnection, 
                QtCore.Q_ARG(str, error_msg)
            )
            
            QtCore.QMetaObject.invokeMethod(
                show_error_dialog,
                "__call__",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(object, self),
                QtCore.Q_ARG(str, "字典合并失败"),
                QtCore.Q_ARG(str, error_msg),
                QtCore.Q_ARG(str, None),
                QtCore.Q_ARG(str, "错误")
            )
        
        finally:
            # 恢复界面
            QtCore.QMetaObject.invokeMethod(
                self, "setEnabled", 
                QtCore.Qt.QueuedConnection, 
                QtCore.Q_ARG(bool, True)
            )

class RuleEditorDialog(BaseDialog):
    """密码规则编辑器对话框，用于创建和编辑自定义的密码变换规则"""
    
    def __init__(self, parent=None):
        """初始化对话框
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("密码规则编辑器")
        self.resize(700, 550)
        
        # 当前规则文件路径
        self.current_file = ""
        self.has_changes = False
        
        # 设置布局
        content_layout = QtWidgets.QVBoxLayout()
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)
        
        # 添加说明标签
        desc_label = QtWidgets.QLabel(
            "使用规则编辑器创建和编辑密码变换规则，用于字典+规则攻击模式。\n"
            "每行一条规则，规则格式遵循hashcat规则语法。"
        )
        desc_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(desc_label)
        
        # 创建标签页控件
        self.tab_widget = QtWidgets.QTabWidget()
        
        # 规则编辑器标签页
        editor_tab = QtWidgets.QWidget()
        editor_layout = QtWidgets.QVBoxLayout(editor_tab)
        editor_layout.setContentsMargins(5, 5, 5, 5)
        
        # 添加规则编辑器
        editor_group = QtWidgets.QGroupBox("规则编辑器")
        editor_group_layout = QtWidgets.QVBoxLayout(editor_group)
        
        # 工具栏
        toolbar_layout = QtWidgets.QHBoxLayout()
        
        # 文件操作按钮
        new_btn = QtWidgets.QPushButton("新建")
        new_btn.clicked.connect(self.new_file)
        toolbar_layout.addWidget(new_btn)
        
        open_btn = QtWidgets.QPushButton("打开")
        open_btn.clicked.connect(self.open_file)
        toolbar_layout.addWidget(open_btn)
        
        save_btn = QtWidgets.QPushButton("保存")
        save_btn.clicked.connect(self.save_file)
        toolbar_layout.addWidget(save_btn)
        
        save_as_btn = QtWidgets.QPushButton("另存为")
        save_as_btn.clicked.connect(self.save_file_as)
        toolbar_layout.addWidget(save_as_btn)
        
        toolbar_layout.addStretch()
        
        # 当前文件标签
        self.file_label = QtWidgets.QLabel("未保存的规则文件")
        toolbar_layout.addWidget(self.file_label)
        
        editor_group_layout.addLayout(toolbar_layout)
        
        # 文本编辑器
        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setFont(QtGui.QFont("Consolas", 10))
        self.editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.editor.textChanged.connect(self.on_text_changed)
        # 设置深色背景颜色
        self.editor.setStyleSheet("background-color: #2D2D30; color: #E0E0E0;")
        editor_group_layout.addWidget(self.editor)
        
        editor_layout.addWidget(editor_group)
        
        # 规则测试区域
        test_group = QtWidgets.QGroupBox("规则测试")
        test_layout = QtWidgets.QVBoxLayout(test_group)
        
        # 输入和输出布局
        test_io_layout = QtWidgets.QHBoxLayout()
        
        # 输入区域
        input_layout = QtWidgets.QVBoxLayout()
        input_layout.addWidget(QtWidgets.QLabel("输入密码:"))
        self.test_input = QtWidgets.QPlainTextEdit()
        self.test_input.setPlaceholderText("每行一个密码")
        self.test_input.setMaximumHeight(80)
        # 设置深色背景颜色
        self.test_input.setStyleSheet("background-color: #2D2D30; color: #E0E0E0;")
        input_layout.addWidget(self.test_input)
        test_io_layout.addLayout(input_layout)
        
        # 结果区域
        result_layout = QtWidgets.QVBoxLayout()
        result_layout.addWidget(QtWidgets.QLabel("变换结果:"))
        self.test_result = QtWidgets.QPlainTextEdit()
        self.test_result.setReadOnly(True)
        self.test_result.setMaximumHeight(80)
        # 设置深色背景颜色
        self.test_result.setStyleSheet("background-color: #2D2D30; color: #E0E0E0;")
        result_layout.addWidget(self.test_result)
        test_io_layout.addLayout(result_layout)
        
        test_layout.addLayout(test_io_layout)
        
        # 测试按钮
        test_btn_layout = QtWidgets.QHBoxLayout()
        test_btn_layout.addStretch()
        
        self.test_btn = QtWidgets.QPushButton("测试选中规则")
        self.test_btn.clicked.connect(self.test_rule)
        test_btn_layout.addWidget(self.test_btn)
        
        test_all_btn = QtWidgets.QPushButton("测试所有规则")
        test_all_btn.clicked.connect(lambda: self.test_rule(test_all=True))
        test_btn_layout.addWidget(test_all_btn)
        
        test_layout.addLayout(test_btn_layout)
        
        editor_layout.addWidget(test_group)
        
        # 常用规则标签页
        common_rules_tab = QtWidgets.QWidget()
        common_rules_layout = QtWidgets.QVBoxLayout(common_rules_tab)
        common_rules_layout.setContentsMargins(5, 5, 5, 5)
        
        # 常用规则说明
        common_rules_desc = QtWidgets.QLabel("双击选择常用规则，应用到规则路径")
        common_rules_desc.setStyleSheet("font-weight: bold; color: #0078D7;")
        common_rules_layout.addWidget(common_rules_desc)
        
        # 常用规则列表
        self.common_rules_list = QtWidgets.QListWidget()
        self.common_rules_list.setAlternatingRowColors(True)
        # 设置深色背景颜色
        self.common_rules_list.setStyleSheet("background-color: #2D2D30; color: #E0E0E0; alternate-background-color: #252526;")
        # 连接双击事件
        self.common_rules_list.itemDoubleClicked.connect(self.apply_common_rule)
        common_rules_layout.addWidget(self.common_rules_list)
        
        # 规则预览
        preview_group = QtWidgets.QGroupBox("规则预览")
        preview_layout = QtWidgets.QVBoxLayout(preview_group)
        
        self.rule_preview = QtWidgets.QTextEdit()
        self.rule_preview.setReadOnly(True)
        self.rule_preview.setMinimumHeight(120)
        # 设置深色背景颜色
        self.rule_preview.setStyleSheet("background-color: #2D2D30; color: #E0E0E0;")
        preview_layout.addWidget(self.rule_preview)
        
        common_rules_layout.addWidget(preview_group)
        
        # 应用按钮
        apply_btn_layout = QtWidgets.QHBoxLayout()
        apply_btn_layout.addStretch()
        
        self.apply_rule_btn = QtWidgets.QPushButton("应用选中规则")
        self.apply_rule_btn.clicked.connect(self.apply_selected_rule)
        self.apply_rule_btn.setEnabled(False)
        apply_btn_layout.addWidget(self.apply_rule_btn)
        
        common_rules_layout.addLayout(apply_btn_layout)
        
        # 连接选择更改事件
        self.common_rules_list.currentItemChanged.connect(self.on_rule_selection_changed)
        
        # 添加标签页
        self.tab_widget.addTab(editor_tab, "规则编辑器")
        self.tab_widget.addTab(common_rules_tab, "常用规则")
        
        # 添加标签页到主布局
        content_layout.addWidget(self.tab_widget)
        
        # 底部按钮
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.close_editor)
        btn_layout.addWidget(close_btn)
        
        content_layout.addLayout(btn_layout)
        
        # 添加内容到主布局
        self.main_layout.addLayout(content_layout)
        
        # 初始化常用规则
        self.init_common_rules()
    
    def init_common_rules(self):
        """初始化常用规则列表"""
        # 定义常用规则
        common_rules = [
            {
                "name": "基本规则集 (常用变换)",
                "description": "包含最常用的密码变换规则，如首字母大写、添加数字等",
                "path": "basic.rule",
                "content": """
# 基本规则集 - 常用密码变换
# -----------------------

# 大小写变换
:           # 原始密码
c           # 首字母大写
C           # 首字母小写
u           # 全部大写
l           # 全部小写
t           # 大小写反转

# 添加数字
$1          # 末尾添加数字1
$2          # 末尾添加数字2
$3          # 末尾添加数字3
$123        # 末尾添加123
$!          # 末尾添加!
$@          # 末尾添加@

# 常见替换
so0         # 替换s为0
se3         # 替换e为3
sa@         # 替换a为@
si!         # 替换i为!
"""
            },
            {
                "name": "数字追加规则集 (0-999)",
                "description": "在密码末尾添加各种数字组合",
                "path": "append_digits.rule",
                "content": """
# 数字追加规则集
# ------------

# 单个数字 (0-9)
$0
$1
$2
$3
$4
$5
$6
$7
$8
$9

# 两位数字 (00-99)
$00
$01
$12
$23
$99

# 常见年份
$19
$20
$2020
$2021
$2022
$2023
"""
            },
            {
                "name": "特殊字符规则集",
                "description": "添加各种特殊字符的规则",
                "path": "special_chars.rule",
                "content": """
# 特殊字符规则集
# ------------

# 末尾添加特殊字符
$!
$@
$#
$$
$%
$^
$&
$*
$?

# 特殊字符组合
$!@
$@#
$#$
$!@#

# 特殊字符替换
sa@
se3
si1
si!
so0
"""
            },
            {
                "name": "leetspeak规则集",
                "description": "Leetspeak字符替换规则",
                "path": "leetspeak.rule",
                "content": """
# Leetspeak替换规则集
# ----------------

# 基本替换
sa@
se3
si1
so0
sl1
sA4
sB8
sE3
sG6
sI1
sO0
sS5
sT7
sZ2

# 组合替换
sa@so0
se3si1
so0se3
si1sl1
sa@si1
sa@se3
"""
            },
            {
                "name": "Case变换规则集",
                "description": "各种大小写变换规则",
                "path": "case_toggle.rule",
                "content": """
# 大小写变换规则集
# -------------

# 基本大小写
c           # 首字母大写
C           # 首字母小写
u           # 全部大写
l           # 全部小写
t           # 大小写反转

# 特定位置大小写
T0          # 第1个字符大小写反转
T1          # 第2个字符大小写反转
T2          # 第3个字符大小写反转

# 组合大小写
c $1        # 首字母大写 + 添加数字1
u $!        # 全部大写 + 添加!
"""
            }
        ]
        
        # 添加到列表中
        for rule in common_rules:
            item = QtWidgets.QListWidgetItem(rule["name"])
            item.setData(QtCore.Qt.UserRole, rule)
            self.common_rules_list.addItem(item)
    
    def on_rule_selection_changed(self, current, previous):
        """规则选择变更事件
        
        Args:
            current: 当前选中项
            previous: 前一个选中项
        """
        if current:
            # 获取选中规则数据
            rule_data = current.data(QtCore.Qt.UserRole)
            
            # 显示规则预览
            self.rule_preview.setText(rule_data["content"])
            
            # 启用应用按钮
            self.apply_rule_btn.setEnabled(True)
        else:
            self.rule_preview.clear()
            self.apply_rule_btn.setEnabled(False)
    
    def apply_common_rule(self, item):
        """应用选中的常用规则
        
        Args:
            item: 列表项
        """
        # 获取规则数据
        rule_data = item.data(QtCore.Qt.UserRole)
        
        # 获取父窗口
        parent = self.parent()
        
        # 检查父窗口是否是主窗口类，并且有rulePathEdit属性
        if parent and hasattr(parent, "rulePathEdit"):
            # 创建临时规则文件路径
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")
            
            # 确保目录存在
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            # 规则文件路径
            rule_file_path = os.path.join(temp_dir, rule_data["path"])
            
            # 保存规则到文件
            with open(rule_file_path, "w", encoding="utf-8") as f:
                f.write(rule_data["content"])
            
            # 设置规则路径到输入框
            parent.rulePathEdit.setText(rule_file_path)
            
            # 显示成功消息
            QtWidgets.QMessageBox.information(
                self, 
                "规则已应用", 
                f"规则 '{rule_data['name']}' 已应用到规则路径。"
            )
            
            # 关闭对话框
            self.accept()
    
    def apply_selected_rule(self):
        """应用当前选中的规则"""
        current_item = self.common_rules_list.currentItem()
        if current_item:
            self.apply_common_rule(current_item)
    
    def on_text_changed(self):
        """文本内容改变事件"""
        self.has_changes = True
        
        # 更新状态
        file_name = os.path.basename(self.current_file) if self.current_file else "未保存"
        self.file_label.setText(f"编辑中: {file_name} *")
    
    def new_file(self):
        """创建新规则文件"""
        # 检查是否有未保存的更改
        if self.has_changes:
            reply = QtWidgets.QMessageBox.question(
                self, "未保存的更改", 
                "当前文件有未保存的更改，是否保存?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Yes
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                if not self.save_file():
                    return  # 保存失败，取消新建
            elif reply == QtWidgets.QMessageBox.Cancel:
                return  # 取消新建
        
        # 清空编辑器
        self.editor.clear()
        
        # 添加默认注释
        self.editor.setPlainText(
            "# Hashcat 规则文件\n"
            "# 创建于 " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n"
            "# 每行一条规则\n\n"
            "# 示例规则:\n"
            "# $1 - 在末尾添加数字1\n"
            "# $2 - 在末尾添加数字2\n"
            "# c - 首字母大写\n"
        )
        
        # 重置文件状态
        self.current_file = ""
        self.has_changes = False
        self.file_label.setText("新建规则文件")
    
    def open_file(self):
        """打开规则文件"""
        # 检查是否有未保存的更改
        if self.has_changes:
            reply = QtWidgets.QMessageBox.question(
                self, "未保存的更改", 
                "当前文件有未保存的更改，是否保存?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Yes
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                if not self.save_file():
                    return  # 保存失败，取消打开
            elif reply == QtWidgets.QMessageBox.Cancel:
                return  # 取消打开
        
        # 显示文件选择对话框
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "打开规则文件", "", "规则文件 (*.rule);;文本文件 (*.txt);;所有文件 (*)"
        )
        
        if file_path:
            try:
                # 读取文件内容
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # 设置到编辑器
                self.editor.setPlainText(content)
                
                # 更新文件状态
                self.current_file = file_path
                self.has_changes = False
                
                # 更新状态
                file_name = os.path.basename(file_path)
                self.file_label.setText(f"已打开: {file_name}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "错误", f"打开文件失败: {str(e)}")
    
    def save_file(self):
        """保存规则文件"""
        # 如果是新文件，则另存为
        if not self.current_file:
            return self.save_file_as()
        
        try:
            # 获取编辑器内容
            content = self.editor.toPlainText()
            
            # 保存到文件
            with open(self.current_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 更新文件状态
            self.has_changes = False
            
            # 更新状态
            file_name = os.path.basename(self.current_file)
            self.file_label.setText(f"已保存: {file_name}")
            
            return True
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "错误", f"保存文件失败: {str(e)}")
            return False
    
    def save_file_as(self):
        """另存为新文件"""
        # 显示文件保存对话框
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存规则文件", "", "规则文件 (*.rule);;文本文件 (*.txt);;所有文件 (*)"
        )
        
        if file_path:
            # 更新当前文件路径
            self.current_file = file_path
            
            # 保存文件
            return self.save_file()
        
        return False
    
    def test_rule(self, test_all=False):
        """测试所选规则"""
        # 获取选中的文本
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()
        
        if not selected_text:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择要测试的规则")
            return
        
        # 创建测试对话框
        test_dialog = QtWidgets.QDialog(self)
        test_dialog.setWindowTitle("测试规则")
        test_dialog.resize(400, 300)
        test_dialog.setStyleSheet("background-color: #1E1E1E; color: #CCCCCC;")
        
        test_layout = QtWidgets.QVBoxLayout(test_dialog)
        
        # 选中的规则
        rule_label = QtWidgets.QLabel(f"当前规则: <b>{selected_text}</b>")
        test_layout.addWidget(rule_label)
        
        # 输入区域
        input_group = QtWidgets.QGroupBox("输入词汇")
        input_layout = QtWidgets.QVBoxLayout(input_group)
        
        input_edit = QtWidgets.QPlainTextEdit()
        input_edit.setPlaceholderText("在此输入要测试的词汇，每行一个")
        # 设置深色背景
        input_edit.setStyleSheet("background-color: #2D2D30; color: #E0E0E0;")
        input_layout.addWidget(input_edit)
        test_io_layout.addLayout(input_layout)
        
        # 结果区域
        result_group = QtWidgets.QGroupBox("转换结果")
        result_layout = QtWidgets.QVBoxLayout(result_group)
        
        result_edit = QtWidgets.QPlainTextEdit()
        result_edit.setReadOnly(True)
        # 设置深色背景
        result_edit.setStyleSheet("background-color: #2D2D30; color: #E0E0E0;")
        result_layout.addWidget(result_edit)
        test_io_layout.addLayout(result_layout)
        
        test_layout.addLayout(test_io_layout)
        
        # 测试按钮
        test_btn_layout = QtWidgets.QHBoxLayout()
        test_btn_layout.addStretch()
        
        self.test_btn = QtWidgets.QPushButton("测试选中规则")
        self.test_btn.clicked.connect(lambda: self.run_rule_test(selected_text, input_edit, result_edit))
        btn_layout.addWidget(self.test_btn)
        
        test_all_btn = QtWidgets.QPushButton("测试所有规则")
        test_all_btn.clicked.connect(lambda: self.test_rule(test_all=True))
        test_btn_layout.addWidget(test_all_btn)
        
        test_layout.addLayout(test_btn_layout)
        
        editor_layout.addWidget(test_group)
        
        # 常用规则标签页
        common_rules_tab = QtWidgets.QWidget()
        common_rules_layout = QtWidgets.QVBoxLayout(common_rules_tab)
        common_rules_layout.setContentsMargins(5, 5, 5, 5)
        
        # 常用规则说明
        common_rules_desc = QtWidgets.QLabel("双击选择常用规则，应用到规则路径")
        common_rules_desc.setStyleSheet("font-weight: bold; color: #0078D7;")
        common_rules_layout.addWidget(common_rules_desc)
        
        # 常用规则列表
        self.common_rules_list = QtWidgets.QListWidget()
        self.common_rules_list.setAlternatingRowColors(True)
        # 设置深色背景颜色
        
        test_layout.addWidget(result_group)
        
        # 按钮区域
        btn_layout = QtWidgets.QHBoxLayout()
        
        test_btn = QtWidgets.QPushButton("运行测试")
        test_btn.clicked.connect(lambda: self.run_rule_test(selected_text, input_edit, result_edit))
        btn_layout.addWidget(test_btn)
        
        close_test_btn = QtWidgets.QPushButton("关闭")
        close_test_btn.clicked.connect(test_dialog.accept)
        btn_layout.addWidget(close_test_btn)
        
        test_layout.addLayout(btn_layout)
        
        # 添加默认测试词
        default_words = "password\ntest123\nadmin\nsecret\nP@ssw0rd"
        input_edit.setPlainText(default_words)
        
        # 显示对话框
        test_dialog.exec_()
    
    def run_rule_test(self, rule, input_edit, result_edit):
        """运行规则测试
        
        Args:
            rule: 要测试的规则
            input_edit: 输入文本框
            result_edit: 结果文本框
        """
        # 获取输入词汇
        input_text = input_edit.toPlainText()
        words = [word.strip() for word in input_text.splitlines() if word.strip()]
        
        if not words:
            result_edit.setPlainText("请输入要测试的词汇")
            return
        
        # 创建临时规则文件
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.rule', delete=False) as temp_rule:
                temp_rule.write(rule)
                temp_rule_path = temp_rule.name
            
            # 创建临时词典文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dict', delete=False) as temp_dict:
                for word in words:
                    temp_dict.write(word + '\n')
                temp_dict_path = temp_dict.name
            
            # 创建临时输出文件
            temp_output_fd, temp_output_path = tempfile.mkstemp(suffix='.txt')
            os.close(temp_output_fd)
            
            # 获取hashcat路径
            hashcat_path = self.parent().hashcat_path if hasattr(self.parent(), 'hashcat_path') else "hashcat"
            
            # 构建命令
            cmd = [
                hashcat_path, 
                "--stdout", 
                "-r", temp_rule_path, 
                temp_dict_path
            ]
            
            # 执行命令
            try:
                # 使用subprocess执行命令
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                output, error = process.communicate(timeout=5)
                
                if process.returncode != 0:
                    # 命令执行失败
                    result_edit.setPlainText(f"测试失败: {error}")
                else:
                    # 显示结果
                    results = []
                    for i, (word, result) in enumerate(zip(words, output.splitlines())):
                        results.append(f"{word} -> {result}")
                    
                    result_edit.setPlainText("\n".join(results))
            
            except subprocess.TimeoutExpired:
                process.kill()
                result_edit.setPlainText("测试超时")
            except Exception as e:
                # 如果hashcat执行失败，使用简单的内置规则测试
                result_edit.setPlainText(f"使用内置测试（仅支持简单规则）：\n{self.simple_rule_test(rule, words)}")
        
        except Exception as e:
            result_edit.setPlainText(f"测试失败: {str(e)}")
        
        finally:
            # 清理临时文件
            for path in [temp_rule_path, temp_dict_path, temp_output_path]:
                try:
                    if os.path.exists(path):
                        os.unlink(path)
                except:
                    pass
    
    def simple_rule_test(self, rule, words):
        """简单的内置规则测试，支持基本规则
        
        Args:
            rule: 要测试的规则
            words: 输入词汇列表
        
        Returns:
            str: 测试结果
        """
        results = []
        
        for word in words:
            result = word
            
            # 实现一些基本规则
            if rule == ":l":  # 全部小写
                result = word.lower()
            elif rule == ":u":  # 全部大写
                result = word.upper()
            elif rule == ":c":  # 首字母大写
                result = word.capitalize()
            elif rule == "r":  # 反转
                result = word[::-1]
            elif rule == "d":  # 重复
                result = word + word
            elif rule == "t":  # 大小写转换
                result = ''.join([c.lower() if c.isupper() else c.upper() for c in word])
            elif rule == "{":  # 左旋转
                result = word[1:] + word[0] if word else word
            elif rule == "}":  # 右旋转
                result = word[-1] + word[:-1] if word else word
            elif rule == "[":  # 删除首字符
                result = word[1:] if word else word
            elif rule == "]":  # 删除末字符
                result = word[:-1] if word else word
            elif rule.startswith("$"):  # 在末尾添加字符
                result = word + rule[1:]
            elif rule.startswith("^"):  # 在开头添加字符
                result = rule[1:] + word
            
            results.append(f"{word} -> {result}")
        
        return "\n".join(results)
    
    def close_editor(self):
        """关闭编辑器"""
        # 检查是否有未保存的更改
        if self.has_changes:
            reply = QtWidgets.QMessageBox.question(
                self, "未保存的更改", 
                "当前文件有未保存的更改，是否保存?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Yes
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                if not self.save_file():
                    return  # 保存失败，取消关闭
            elif reply == QtWidgets.QMessageBox.Cancel:
                return  # 取消关闭
        
        # 关闭对话框
        self.accept()

    def show_local_context_menu(self, position):
        """显示本地字典表格的右键菜单
        
        Args:
            position: 鼠标位置
        """
        menu = QtWidgets.QMenu()
        
        # 获取选中的行
        indexes = self.dict_table.selectedIndexes()
        if not indexes:
            return
        
        row = indexes[0].row()
        dict_name = self.dict_table.item(row, 0).text()
        dict_path = self.dict_table.item(row, 2).text()
        
        # 应用字典选项
        apply_action = menu.addAction("应用到字典路径")
        apply_action.triggered.connect(lambda: self.apply_local_dict(row))
        
        # 查看内容选项
        view_action = menu.addAction("查看内容")
        view_action.triggered.connect(lambda: self.view_dict_content_by_row(row))
        
        # 移除字典选项
        remove_action = menu.addAction("移除字典")
        remove_action.triggered.connect(lambda: self.remove_local_dict_by_row(row))
        
        # 显示菜单
        menu.exec_(self.dict_table.viewport().mapToGlobal(position))
    


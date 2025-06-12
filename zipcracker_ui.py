#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ZIP Cracker - UI基础类
包含基础UI组件和样式定义
"""

from PyQt5 import QtWidgets, QtGui, QtCore
import os

# 基础对话框类
class BaseDialog(QtWidgets.QDialog):
    """基础对话框类，所有自定义对话框的基类"""
    
    def __init__(self, parent=None):
        """初始化对话框
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        
        # 设置无边框窗口，取消默认系统外观
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint)
        
        # 设置样式
        qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zipcracker.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        
        # 主布局
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(5)
        
        # 添加自定义标题栏
        self.title_bar = QtWidgets.QWidget()
        self.title_bar.setFixedHeight(24)
        
        title_layout = QtWidgets.QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(8, 0, 8, 0)
        
        # 标题标签
        self.title_label = QtWidgets.QLabel("对话框")
        self.title_label.setProperty("class", "title")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        
        # 关闭按钮
        self.close_btn = QtWidgets.QPushButton("×")
        self.close_btn.setFixedWidth(30)
        self.close_btn.clicked.connect(self.reject)
        title_layout.addWidget(self.close_btn)
        
        self.main_layout.addWidget(self.title_bar)
        
        # 拖动相关变量
        self.moving = False
        self.last_pos = None
        
        # 拖动窗口设置
        self.title_bar.mousePressEvent = self.titleBarMousePressEvent
        self.title_bar.mouseMoveEvent = self.titleBarMouseMoveEvent
        self.title_bar.mouseReleaseEvent = self.titleBarMouseReleaseEvent
    
    def setWindowTitle(self, title):
        """设置窗口标题
        
        Args:
            title (str): 窗口标题
        """
        super().setWindowTitle(title)
        self.title_label.setText(title)
    
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

    def create_button_box(self, has_ok=True, has_cancel=True, has_close=False, ok_text="确定", cancel_text="取消", close_text="关闭"):
        """创建标准按钮盒"""
        button_box = QtWidgets.QDialogButtonBox()
        
        if has_ok:
            self.ok_button = QtWidgets.QPushButton(ok_text)
            button_box.addButton(self.ok_button, QtWidgets.QDialogButtonBox.AcceptRole)
            
        if has_cancel:
            self.cancel_button = QtWidgets.QPushButton(cancel_text)
            button_box.addButton(self.cancel_button, QtWidgets.QDialogButtonBox.RejectRole)
            
        if has_close:
            self.close_button = QtWidgets.QPushButton(close_text)
            button_box.addButton(self.close_button, QtWidgets.QDialogButtonBox.RejectRole)
            
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        return button_box
        
    def create_form_layout(self):
        """创建标准表单布局"""
        form_layout = QtWidgets.QFormLayout()
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form_layout.setSpacing(8)
        return form_layout
        
    def create_section_title(self, title):
        """创建分区标题"""
        label = QtWidgets.QLabel(title)
        label.setProperty("class", "sectionTitle")
        return label
        
    def create_info_message(self, message, icon_type="info"):
        """创建信息消息框"""
        info_widget = QtWidgets.QWidget()
        info_layout = QtWidgets.QHBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        # 图标
        icon_label = QtWidgets.QLabel()
        if icon_type == "info":
            icon_label.setPixmap(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxInformation).pixmap(16, 16))
        elif icon_type == "warning":
            icon_label.setPixmap(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning).pixmap(16, 16))
        elif icon_type == "error":
            icon_label.setPixmap(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxCritical).pixmap(16, 16))
        info_layout.addWidget(icon_label)
        
        # 消息文本
        msg_label = QtWidgets.QLabel(message)
        msg_label.setWordWrap(True)
        info_layout.addWidget(msg_label, 1)
        
        return info_widget 
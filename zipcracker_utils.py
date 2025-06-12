#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ZIP Cracker - 工具函数
包含各种工具函数的实现
"""

import os
import sys
import time
import datetime
import traceback
import tempfile
import subprocess
from PyQt5 import QtCore, QtWidgets
import shutil
import logging
from logging.handlers import RotatingFileHandler
from zipcracker_config import config
import re

def log_error(error):
    """记录错误到日志文件（使用标准logging）
    Args:
        error: 错误对象或字符串
    """
    logger = logging.getLogger("zipcracker")
    try:
        error_message = str(error)
        error_traceback = traceback.format_exc()
        logger.error(f"{error_message}\n{error_traceback}")
    except Exception:
        pass

# 全局的UI更新事件处理器类
class UiUpdateHandler(QtCore.QObject):
    update_signal = QtCore.pyqtSignal(object)
    
    def __init__(self):
        super().__init__()
        self.update_signal.connect(self.handle_update)
    
    @QtCore.pyqtSlot(object)
    def handle_update(self, ui_func):
        try:
            ui_func()
        except Exception as e:
            log_error(e)

# 创建全局单例
_ui_update_handler = None

def get_ui_update_handler():
    """获取全局UI更新处理器"""
    global _ui_update_handler
    if _ui_update_handler is None:
        _ui_update_handler = UiUpdateHandler()
    return _ui_update_handler

def safe_ui_update(func):
    """在UI线程中安全地执行函数
    
    Args:
        func: 要执行的函数
    """
    try:
        # 检查是否在主线程
        if QtCore.QThread.currentThread() == QtWidgets.QApplication.instance().thread():
            # 在主线程中，直接调用
            func()
        else:
            # 在子线程中，使用QMetaObject.invokeMethod
            # 为函数创建一个包装器槽函数
            class FunctionWrapper(QtCore.QObject):
                @QtCore.pyqtSlot()
                def run(self):
                    try:
                        func()
                    except Exception as e:
                        print(f"UI更新错误: {str(e)}")
                        log_error(e)
            
            # 创建包装器对象
            wrapper = FunctionWrapper()
            # 使用invokeMethod调用槽函数
            QtCore.QMetaObject.invokeMethod(
                wrapper,
                "run",
                QtCore.Qt.QueuedConnection
            )
    except Exception as e:
        print(f"UI更新出错: {str(e)}")
        log_error(e)

def extract_rar_hash_py(file_path):
    """使用Python提取RAR文件的哈希
    
    这是一个简化版的rar2john实现，用于在rar2john工具不可用时提供备用方案
    
    Args:
        file_path (str): RAR文件路径
    
    Returns:
        str: 提取的哈希值，失败则返回None
    """
    try:
        # 尝试导入必要的模块
        try:
            import binascii
            import struct
        except ImportError as e:
            log_error(f"导入模块失败: {str(e)}")
            return None
            
        print(f"尝试用Python提取RAR哈希: {file_path}")
        
        # RAR文件头标志
        RAR_ID = b"Rar!\x1a\x07\x00"
        RAR5_ID = b"Rar!\x1a\x07\x01\x00"
        
        # 打开文件并读取头部
        with open(file_path, 'rb') as f:
            # 读取前8个字节来识别RAR版本
            signature = f.read(8)
            
            # 检查是否是RAR文件
            if signature.startswith(RAR_ID):
                # RAR 4.x
                print("检测到RAR 4.x格式")
                # 重置文件指针
                f.seek(0)
                
                # 寻找加密的文件头
                while True:
                    pos = f.tell()
                    header = f.read(7)
                    if len(header) < 7:
                        break  # 文件结束
                    
                    # 解析头部
                    try:
                        crc, header_type, flags, size = struct.unpack("<HBHH", header)
                        
                        # 检查是否为文件头
                        if header_type == 0x74:  # 文件头
                            if flags & 0x04:  # 检查是否加密
                                print(f"找到加密文件头 位置: {pos}")
                                # 读取盐值
                                f.seek(pos + 24)
                                salt = f.read(8)
                                if len(salt) == 8:
                                    salt_hex = binascii.hexlify(salt).decode('ascii')
                                    hash_line = f"$RAR3$*0*{salt_hex}*0*{os.path.basename(file_path)}"
                                    print(f"提取的RAR哈希: {hash_line}")
                                    return hash_line
                        
                        # 跳到下一个头部
                        f.seek(pos + size)
                    except:
                        # 结构解析错误，尝试继续
                        f.seek(pos + 1)
                
                print("未找到加密的RAR文件头")
                return None
                
            elif signature.startswith(RAR5_ID):
                # RAR 5.x
                print("检测到RAR 5.x格式")
                # 简单检测RAR5是否加密（具体算法比较复杂）
                f.seek(0)
                
                # RAR5需要更复杂的算法支持，这里只是检测可能的加密标志
                try:
                    # 跳过签名
                    f.seek(8)
                    
                    # 读取头部CRC
                    header_crc = f.read(4)
                    
                    # 读取头部类型
                    vint = read_vint(f)
                    header_type = vint & 0x7f
                    
                    # 如果是主头部（类型为1）
                    if header_type == 1:
                        # 读取头部标志
                        vint = read_vint(f)
                        flags = vint
                        
                        # 检查是否设置了加密标志（第2位）
                        if flags & 0x02:
                            print("检测到RAR5文件可能加密")
                            # 返回一个简单的RAR5哈希格式
                            hash_line = f"$RAR5$*{os.path.basename(file_path)}*这个文件是RAR5格式，需要专业工具提取哈希"
                            return hash_line
                except:
                    print("RAR5格式解析失败")
                
                print("RAR5格式，需要使用rar2john工具提取哈希")
                return None
            else:
                print("文件不是RAR格式")
                return None
    except Exception as e:
        log_error(f"Python提取RAR哈希失败: {str(e)}")
        print(f"Python提取RAR哈希失败: {str(e)}")
        return None

def read_vint(f):
    """读取RAR5中的可变长整数
    
    Args:
        f: 文件对象
    
    Returns:
        int: 可变长整数值
    """
    b = ord(f.read(1))
    if (b & 0x80) == 0:
        return b
    
    value = b & 0x7f
    
    b = ord(f.read(1))
    value |= (b & 0x7f) << 7
    if (b & 0x80) == 0:
        return value
    
    b = ord(f.read(1))
    value |= (b & 0x7f) << 14
    if (b & 0x80) == 0:
        return value
    
    b = ord(f.read(1))
    value |= (b & 0x7f) << 21
    if (b & 0x80) == 0:
        return value
    
    b = ord(f.read(1))
    value |= (b & 0x7f) << 28
    return value

def fix_hash_format(hash_value, file_ext, hash_file):
    """修复哈希格式以兼容hashcat
    
    Args:
        hash_value (str): 原始哈希值
        file_ext (str): 文件扩展名
        hash_file (str): 哈希文件路径
    
    Returns:
        tuple: (修复后的哈希值, 哈希文件路径)
    """
    if not hash_value:
        return hash_value, hash_file
    
    fixed_hash = hash_value
    
    # 简单清理哈希值，移除前后空白
    fixed_hash = fixed_hash.strip()
    
    # 如果有多行，只取第一行
    if "\n" in fixed_hash:
        fixed_hash = fixed_hash.split("\n")[0].strip()
    
    # 针对RAR5格式进行特殊处理
    if file_ext == "rar" and "$rar5$" in fixed_hash:
        # 提取标准格式的RAR5哈希
        if fixed_hash.startswith("$rar5$") and "$" in fixed_hash:
            fixed_hash = fixed_hash.split("$", 2)[2]
            print(f"已提取并修复RAR5哈希: {fixed_hash}")
        else:
            # 如果不符合标准格式，尝试构造一个兼容格式
            parts = fixed_hash.split('$')
            if len(parts) >= 6:
                # 确保格式为 $rar5$16$salt$iterations$iv$ct_len$ct
                try:
                    # 提取关键部分
                    prefix = parts[0] + "$" + parts[1]  # 通常是空字符串+"rar5"
                    salt_len = parts[2]  # 通常是"16"
                    salt = parts[3]
                    iterations = parts[4]
                    iv = parts[5]
                    
                    # 检查是否有ct_len和ct部分
                    if len(parts) >= 8:
                        ct_len = parts[6]
                        ct = parts[7]
                        # 重新构造标准格式
                        fixed_hash = f"$rar5${salt_len}${salt}${iterations}${iv}${ct_len}${ct}"
                        print(f"已重构RAR5哈希格式: {fixed_hash}")
                except:
                    print("RAR5哈希格式无法修复，将保持原始格式")
    
    # 更新哈希文件
    if fixed_hash != hash_value and hash_file:
        try:
            with open(hash_file, "w", encoding="utf-8") as f:
                f.write(fixed_hash)
            print(f"哈希格式已修复: {fixed_hash[:50]}...")
        except Exception as e:
            print(f"更新哈希文件失败: {str(e)}")
    
    return fixed_hash, hash_file

def check_perl():
    """检测系统是否安装了 Perl 解释器"""
    perl_path = shutil.which("perl")
    if perl_path:
        return True
    return False

def extract_hash_safe(john_path, file_path, file_ext):
    """安全提取哈希值
    
    Args:
        john_path (str): John the Ripper路径
        file_path (str): 文件路径
        file_ext (str): 文件扩展名
    
    Returns:
        tuple: (哈希值, 哈希文件路径)
    """
    logger = logging.getLogger("zipcracker")
    try:
        # 检查John路径
        if not john_path:
            log_error("John the Ripper路径未设置")
            return None, None
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="zipcracker_")
        
        # 哈希文件路径
        hash_file = os.path.join(temp_dir, f"hash.txt")
        
        # 检查John路径是否为目录还是直接指向可执行文件
        john_exe = john_path
        john_dir = None
        if os.path.isdir(john_path):
            john_dir = john_path
            # 检查各种可能的John路径
            possible_john_paths = [
                os.path.join(john_path, "john.exe"),  # 直接在指定目录下
                os.path.join(john_path, "john"),      # Linux/Mac
                os.path.join(john_path, "run", "john.exe"),  # Windows下的run子目录
                os.path.join(john_path, "run", "john")       # Linux/Mac下的run子目录
            ]
            # 选择第一个存在的路径
            for path in possible_john_paths:
                if os.path.exists(path):
                    john_exe = path
                    break
        
        # 检查John是否存在
        if not os.path.exists(john_exe):
            log_error(f"John the Ripper可执行文件不存在: {john_exe}")
            return None, None
        
        logger.info(f"使用John路径: {john_exe}")
        logger.info(f"处理文件: {file_path}, 类型: {file_ext}")
        
        # 根据文件类型选择格式和工具
        format_arg = ""
        need_perl = False
        perl_script = None
        if file_ext == "zip":
            format_arg = "--format=ZIP"
            # 优先用 zip2john.exe 提取哈希
            zip2john_path = None
            if john_dir:
                for p in [
                    os.path.join(john_dir, "zip2john.exe"),
                    os.path.join(john_dir, "run", "zip2john.exe"),
                    os.path.join(os.path.dirname(john_exe), "zip2john.exe")
                ]:
                    if os.path.exists(p):
                        zip2john_path = p
                        break
            if zip2john_path:
                cmd = [zip2john_path, file_path]
                logger.info(f"执行命令: {' '.join(cmd)}")
                result = run_cmd_with_output(cmd)
                if result:
                    # 修复：兼容 zip2john 输出格式，提取 $zip2$ 或 $pkzip2$ 哈希
                    hash_line = None
                    for line in result.strip().split("\n"):
                        if "$zip2$" in line:
                            m = re.search(r'(\$zip2\$[^: \r\n]*)', line)
                            if m:
                                hash_line = m.group(1)
                                break
                        elif "$pkzip2$" in line:
                            m = re.search(r'(\$pkzip2\$.*?\*\$/pkzip2\$)', line)
                            if m:
                                hash_line = m.group(1)
                                break
                    if hash_line and len(hash_line) > 20 and (hash_line.startswith("$zip2$") or hash_line.startswith("$pkzip2$")):
                        with open(hash_file, "w", encoding="utf-8") as f:
                            f.write(hash_line)
                        logger.info(f"成功用 zip2john.exe 提取哈希: {hash_line[:80]}...")
                        return hash_line, hash_file
                    else:
                        first_line = result.strip().split('\n')[0]
                        logger.info(f"zip2john.exe 输出内容不是有效哈希: {first_line}")
                else:
                    logger.info(f"zip2john.exe 未输出哈希")
            # 如果 zip2john.exe 不存在或失败，继续尝试 perl 脚本
            script_path = None
            for p in [
                os.path.join(john_dir, "zip2john.pl") if john_dir else None,
                os.path.join(john_dir, "run", "zip2john.pl") if john_dir else None,
                os.path.join(os.path.dirname(john_exe), "zip2john.pl") if john_exe else None
            ]:
                if p and os.path.exists(p):
                    script_path = p
                    break
            if script_path:
                cmd = ["perl", script_path, file_path]
                logger.info(f"执行命令: {' '.join(cmd)}")
                result = run_cmd_with_output(cmd)
                if result:
                    hash_line = result.strip().split("\n")[0]
                    if hash_line.startswith("$pkzip2$") and "*$/pkzip2$" in hash_line:
                        hash_line = hash_line.split("*$/pkzip2$", 1)[0] + "*$/pkzip2$"
                    if len(hash_line) > 20 and hash_line.startswith("$pkzip2$"):
                        with open(hash_file, "w", encoding="utf-8") as f:
                            f.write(hash_line)
                        logger.info(f"成功用 zip2john.pl 提取哈希: {hash_line[:80]}...")
                        return hash_line, hash_file
                    else:
                        logger.info(f"zip2john.pl 输出内容不是有效哈希: {hash_line}")
                else:
                    logger.info(f"zip2john.pl 未输出哈希")
            # 如果所有方法都失败，返回 None
            log_error(f"无法提取哈希值: {file_path}")
            logger.error(f"哈希提取失败: {file_path}")
            return None, None
        elif file_ext == "rar":
            # 优先用 rar2john.exe 提取哈希
            rar2john_path = None
            if john_dir:
                for p in [
                    os.path.join(john_dir, "rar2john.exe"),
                    os.path.join(john_dir, "run", "rar2john.exe"),
                    os.path.join(os.path.dirname(john_exe), "rar2john.exe")
                ]:
                    if os.path.exists(p):
                        rar2john_path = p
                        break
            hash_found = False
            if rar2john_path:
                cmd = [rar2john_path, file_path]
                logger.info(f"执行命令: {' '.join(cmd)}")
                result = run_cmd_with_output(cmd)
                if result:
                    hash_line = result.strip().split("\n")[0]
                    # 提取 $rar5$ 或 $rar$ 哈希
                    if hash_line.startswith("$rar5$") and "$" in hash_line:
                        hash_line = hash_line.split("$", 2)[2]
                        if len(hash_line) > 20 and ("$" in hash_line or ":" in hash_line):
                            with open(hash_file, "w", encoding="utf-8") as f:
                                f.write(hash_line)
                            print(f"成功用 rar2john.exe 提取哈希: {hash_line[:80]}...")
                            return hash_line, hash_file
                        else:
                            print(f"rar2john.exe 输出内容不是有效哈希: {hash_line}")
                    elif ':' in hash_line:
                        hash_line = hash_line.split(':', 1)[-1].strip()
                    if len(hash_line) > 20 and ("$" in hash_line or ":" in hash_line):
                        with open(hash_file, "w", encoding="utf-8") as f:
                            f.write(hash_line)
                        print(f"成功用 rar2john.exe 提取哈希: {hash_line[:80]}...")
                        return hash_line, hash_file
                    else:
                        print(f"rar2john.exe 输出内容不是有效哈希: {hash_line}")
                else:
                    print(f"rar2john.exe 未输出哈希")
            # 如果 rar2john.exe 不存在或失败，继续尝试 perl 脚本
            # 查找 perl 脚本路径
            script_path = None
            for p in [
                os.path.join(john_dir, "rar2john.pl") if john_dir else None,
                os.path.join(john_dir, "run", "rar2john.pl") if john_dir else None,
                os.path.join(os.path.dirname(john_exe), "rar2john.pl") if john_exe else None
            ]:
                if p and os.path.exists(p):
                    script_path = p
                    break
            if script_path:
                cmd = ["perl", script_path, file_path]
                print(f"执行命令: {' '.join(cmd)}")
                result = run_cmd_with_output(cmd)
                if result:
                    hash_line = result.strip().split("\n")[0]
                    if hash_line.startswith("$rar5$") and "$" in hash_line:
                        hash_line = hash_line.split("$", 2)[2]
                        if len(hash_line) > 20 and ("$" in hash_line or ":" in hash_line):
                            with open(hash_file, "w", encoding="utf-8") as f:
                                f.write(hash_line)
                            print(f"成功用 rar2john.pl 提取哈希: {hash_line[:80]}...")
                            return hash_line, hash_file
                        else:
                            print(f"rar2john.pl 输出内容不是有效哈希: {hash_line}")
                    elif ':' in hash_line:
                        hash_line = hash_line.split(':', 1)[-1].strip()
                    if len(hash_line) > 20 and ("$" in hash_line or ":" in hash_line):
                        with open(hash_file, "w", encoding="utf-8") as f:
                            f.write(hash_line)
                        print(f"成功用 rar2john.pl 提取哈希: {hash_line[:80]}...")
                        return hash_line, hash_file
                    else:
                        print(f"rar2john.pl 输出内容不是有效哈希: {hash_line}")
                else:
                    print(f"rar2john.pl 未输出哈希")
            # 如果所有方法都失败，返回 None
            log_error(f"无法提取哈希值: {file_path}")
            print(f"哈希提取失败: {file_path}")
            return None, None
        elif file_ext == "7z":
            format_arg = "--format=7z"
            need_perl = True
            perl_script = "7z2john.pl"
            # 查找7z2john.pl
            script_path = None
            for p in [
                os.path.join(john_dir, "7z2john.pl") if john_dir else None,
                os.path.join(john_dir, "run", "7z2john.pl") if john_dir else None,
                os.path.join(os.path.dirname(john_exe), "7z2john.pl") if john_exe else None
            ]:
                if p and os.path.exists(p):
                    script_path = p
                    break
            hash_line = None
            if script_path:
                cmd = ["perl", script_path, file_path]
                logger.info(f"执行命令: {' '.join(cmd)}")
                result = run_cmd_with_output(cmd)
                if result:
                    for line in result.splitlines():
                        if "$7z$" in line:
                            hash_line = line.split(":", 1)[-1].strip() if ":$7z$" in line else line.strip()
                            break
            # 如果7z2john.pl未能提取hash，尝试7z2hashcat.pl
            if (not hash_line or not hash_line.startswith("$7z$")):
                script_path = None
                for p in [
                    os.path.join(john_dir, "7z2hashcat.pl") if john_dir else None,
                    os.path.join(john_dir, "run", "7z2hashcat.pl") if john_dir else None,
                    os.path.join(os.path.dirname(john_exe), "7z2hashcat.pl") if john_exe else None
                ]:
                    if p and os.path.exists(p):
                        script_path = p
                        break
                if script_path:
                    cmd = ["perl", script_path, file_path]
                    logger.info(f"执行命令: {' '.join(cmd)}")
                    result = run_cmd_with_output(cmd)
                    if result:
                        for line in result.splitlines():
                            if "$7z$" in line:
                                hash_line = line.split(":", 1)[-1].strip() if ":$7z$" in line else line.strip()
                                break
            if hash_line and hash_line.startswith("$7z$"):
                with open(hash_file, "w", encoding="utf-8") as f:
                    f.write(hash_line)
                logger.info(f"成功用 7z2john.pl/7z2hashcat.pl 提取哈希: {hash_line[:80]}...")
                return hash_line, hash_file
            else:
                logger.info(f"7z2john.pl/7z2hashcat.pl 输出内容不是有效哈希: {result if 'result' in locals() else ''}")
            log_error(f"无法提取哈希值: {file_path}")
            logger.error(f"哈希提取失败: {file_path}")
            return None, None
        elif file_ext == "pdf":
            format_arg = "--format=PDF"
            need_perl = True
            perl_script = "pdf2john.pl"
        elif file_ext in ["doc", "docx", "xls", "xlsx", "ppt", "pptx"]:
            format_arg = "--format=office"
            # 优先用 office2john.py 提取哈希
            script_py = None
            script_pl = None
            if john_dir:
                for p in [
                    os.path.join(john_dir, "office2john.py"),
                    os.path.join(john_dir, "run", "office2john.py"),
                    os.path.join(os.path.dirname(john_exe), "office2john.py")
                ]:
                    if os.path.exists(p):
                        script_py = p
                        break
                for p in [
                    os.path.join(john_dir, "office2john.pl"),
                    os.path.join(john_dir, "run", "office2john.pl"),
                    os.path.dirname(john_exe) and os.path.join(os.path.dirname(john_exe), "office2john.pl")
                ]:
                    if p and os.path.exists(p):
                        script_pl = p
                        break
            # 先用python脚本
            if script_py:
                import sys
                cmd = [sys.executable, script_py, file_path]
                logger.info(f"执行命令: {' '.join(cmd)}")
                result = run_cmd_with_output(cmd)
                if result:
                    # 修复：兼容文件名:$oldoffice$...:...格式，自动提取哈希
                    hash_line = None
                    for line in result.strip().split("\n"):
                        m = re.search(r'(\$oldoffice\$[\w\*]+|\$office\$[\w\*]+)', line)
                        if m:
                            hash_line = m.group(1)
                            break
                    if hash_line and len(hash_line) > 20 and (hash_line.startswith("$oldoffice$") or hash_line.startswith("$office$")):
                        with open(hash_file, "w", encoding="utf-8") as f:
                            f.write(hash_line)
                        logger.info(f"成功用 office2john.py 提取哈希: {hash_line[:80]}...")
                        return hash_line, hash_file
                    else:
                        first_line = result.strip().split('\n')[0]
                        logger.info(f"office2john.py 输出内容不是有效哈希: {first_line}")
                        logger.info(f"office2john.py 原始输出: {result}")
                else:
                    logger.info(f"office2john.py 未输出哈希")
            # 再尝试perl脚本
            if script_pl:
                if not check_perl():
                    QtWidgets.QMessageBox.critical(None, "缺少 Perl 环境", "检测到您需要提取哈希的文件类型（如 Office）需要 Perl 解释器支持。\n\n请先安装 Perl（推荐 Strawberry Perl），并确保其已加入系统 PATH 环境变量。\n\n否则无法正常提取哈希！")
                    return None, None
                cmd = ["perl", script_pl, file_path]
                logger.info(f"执行命令: {' '.join(cmd)}")
                result = run_cmd_with_output(cmd)
                if result:
                    hash_line = None
                    for line in result.strip().split("\n"):
                        m = re.search(r'(\$oldoffice\$[\w\*]+|\$office\$[\w\*]+)', line)
                        if m:
                            hash_line = m.group(1)
                            break
                    if hash_line and len(hash_line) > 20 and (hash_line.startswith("$oldoffice$") or hash_line.startswith("$office$")):
                        with open(hash_file, "w", encoding="utf-8") as f:
                            f.write(hash_line)
                        logger.info(f"成功用 office2john.pl 提取哈希: {hash_line[:80]}...")
                        return hash_line, hash_file
                    else:
                        first_line = result.strip().split('\n')[0]
                        logger.info(f"office2john.pl 输出内容不是有效哈希: {first_line}")
                        logger.info(f"office2john.pl 原始输出: {result}")
                else:
                    logger.info(f"office2john.pl 未输出哈希")
            if not script_py and not script_pl:
                show_error_dialog(None, "未找到 office2john.py 或 office2john.pl，请确认 John the Ripper 目录下存在该脚本。\n\n否则无法正常提取哈希！", title="缺少 Office2John 脚本")
                log_error(f"无法提取哈希值: {file_path}")
                logger.error(f"哈希提取失败: {file_path}")
                return None, None
            log_error(f"无法提取哈希值: {file_path}")
            logger.error(f"哈希提取失败: {file_path}")
            print(f"哈希提取失败: {file_path}")
            return None, None
        # 构建命令
        cmd = [john_exe, "--list=formats"]
        output = run_cmd_with_output(cmd)
        logger.info(f"支持的格式: {output}")
        if format_arg:
            format_name = format_arg[9:]
            if format_name not in output:
                log_error(f"John the Ripper不支持格式: {format_name}")
                logger.error(f"不支持的格式: {format_name}")
                return None, None
        cmd = [john_exe]
        if format_arg:
            cmd.append(format_arg)
        cmd.extend(["--show", file_path])
        logger.info(f"执行命令: {' '.join(cmd)}")
        result = run_cmd_with_output(cmd)
        logger.info(f"命令结果: {result[:100]}...")
        def is_valid_hash(hash_str):
            if not hash_str:
                return False
            error_indicators = [
                "Invalid", "Error", "Usage", "Valid options", 
                "show switch", "failed", "WARNING", "ERROR"
            ]
            for indicator in error_indicators:
                if indicator in hash_str:
                    return False
            hash_indicators = ["$", ":", "*"]
            has_indicator = False
            for indicator in hash_indicators:
                if indicator in hash_str:
                    has_indicator = True
                    break
            return has_indicator
        if result:
            if not is_valid_hash(result):
                print(f"提取出的内容不是有效哈希: {result[:100]}")
                log_error(f"提取出的内容不是有效哈希: {result[:100]}")
                return None, None
            result, hash_file = fix_hash_format(result, file_ext, hash_file)
            with open(hash_file, "w", encoding="utf-8") as f:
                f.write(result)
            return result.strip(), hash_file
        log_error(f"无法提取哈希值: {file_path}")
        print(f"哈希提取失败: {file_path}")
        return None, None
    except Exception as e:
        log_error(e)
        print(f"哈希提取异常: {str(e)}")
        return None, None

def run_cmd_with_output(cmd, timeout=30):
    """运行命令并获取输出
    
    Args:
        cmd (list): 命令列表
        timeout (int, optional): 超时时间，默认30秒
    
    Returns:
        str: 命令输出
    """
    try:
        # 在Windows上，使用startupinfo隐藏命令窗口
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        print(f"执行命令: {' '.join(cmd)}")
        
        # 运行命令
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo
        )
        
        # 等待命令完成
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            
            # 检查返回码
            if process.returncode == 0:
                if stdout:
                    result = stdout.decode("utf-8", errors="ignore")
                    if len(result) > 100:
                        print(f"命令成功，输出: {result[:100]}...")
                    else:
                        print(f"命令成功，输出: {result}")
                    return result
                else:
                    print("命令成功但无输出")
                    return ""
            else:
                error = stderr.decode("utf-8", errors="ignore")
                print(f"命令失败，错误码: {process.returncode}, 错误信息: {error}")
                log_error(f"命令执行失败: {' '.join(cmd)}, 错误码: {process.returncode}, 错误: {error}")
                return error
        except subprocess.TimeoutExpired:
            # 命令超时
            process.kill()
            print(f"命令超时 ({timeout}秒): {' '.join(cmd)}")
            log_error(f"命令超时: {' '.join(cmd)}")
            return f"命令超时 ({timeout}秒)"
    except Exception as e:
        print(f"执行命令异常: {str(e)}")
        log_error(e)
        return f"命令执行错误: {str(e)}"

def get_formatted_time():
    """获取格式化的当前时间
    
    Returns:
        str: 格式化的时间字符串
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def format_duration(seconds):
    """格式化持续时间
    
    Args:
        seconds (float): 秒数
    
    Returns:
        str: 格式化的持续时间
    """
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def is_supported_file(file_path):
    """检查文件是否支持
    
    Args:
        file_path (str): 文件路径
    
    Returns:
        bool: 是否支持
    """
    from zipcracker_models import SUPPORTED_EXTS
    
    # 获取文件扩展名（包含前导点）
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # 检查扩展名是否支持
    return file_ext in SUPPORTED_EXTS

# 获取文件大小的可读字符串
def get_readable_file_size(size_bytes):
    """将字节大小转换为可读的字符串格式"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.2f} KB"
    else:
        return f"{size_bytes/(1024*1024):.2f} MB"

def has_chinese(s):
    """判断字符串是否包含中文字符"""
    if not isinstance(s, str):
        try:
            s = str(s)
        except Exception:
            return False
    for ch in s:
        if '\u4e00' <= ch <= '\u9fff':
            return True
    return False

def init_logging():
    """初始化全局日志系统，支持分级和轮转"""
    log_dir = config.get("log_dir", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, config.get("log_file", "zipcracker.log"))
    max_bytes = config.get("log_max_bytes", 5 * 1024 * 1024)  # 5MB
    backup_count = config.get("log_backup_count", 10)
    log_level = config.get("log_level", "INFO").upper()
    handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    # 避免重复添加handler
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    # 控制台输出（可选）
    if config.get("log_console", True):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root_logger.addHandler(console)

def get_logger(name=None):
    """获取logger实例"""
    return logging.getLogger(name)

def show_error_dialog(parent, message, detail=None, suggestion=None, title="错误"): 
    """弹出错误对话框并写入日志，可选详细信息和建议"""
    import logging
    from PyQt5 import QtWidgets
    logger = logging.getLogger("zipcracker")
    full_msg = message
    if detail:
        full_msg += f"\n\n详细信息: {detail}"
    if suggestion:
        full_msg += f"\n\n建议: {suggestion}"
    logger.error(full_msg)
    QtWidgets.QMessageBox.critical(parent, title, full_msg)

def show_info_dialog(parent, message, detail=None, suggestion=None, title="提示"): 
    """弹出信息对话框并写入日志，可选详细信息和建议"""
    import logging
    from PyQt5 import QtWidgets
    logger = logging.getLogger("zipcracker")
    full_msg = message
    if detail:
        full_msg += f"\n\n详细信息: {detail}"
    if suggestion:
        full_msg += f"\n\n建议: {suggestion}"
    logger.info(full_msg)
    QtWidgets.QMessageBox.information(parent, title, full_msg) 
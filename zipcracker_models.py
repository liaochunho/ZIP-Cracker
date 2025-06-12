import os
import threading
import queue
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal
import requests
import csv
import sqlite3
import re
import codecs
import tempfile

# 全局常量
SUPPORTED_EXTS = ['.zip', '.rar', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.pdf', '.7z']
JOHN_DOWNLOAD_URL = 'https://www.openwall.com/john/'
HASHCAT_DOWNLOAD_URL = 'https://hashcat.net/hashcat/'
POTFILE_PATH = 'hashcat.potfile'
MAX_WORKERS = 4  # 线程池最大线程数

# 文件扩展名与 hashcat -m 参数映射
HASHCAT_MODE_MAP = {
    'zip': '13600',  # WinZip
    'rar': '13000',  # RAR5
    'pdf': '10500',  # PDF 1.4 - 1.6
    'doc': '9800',   # Office 2007
    'docx': '9400',  # Office 2013
    'xls': '9800',   # Excel 2007
    'xlsx': '9400',  # Excel 2013
    'ppt': '9800',   # PowerPoint 2007
    'pptx': '9400',  # PowerPoint 2013
    '7z': '11600',   # 7-Zip
}

# 文件扩展名与 john --format 映射
JOHN_FORMAT_MAP = {
    'zip': 'zip',
    'rar': 'rar',
    'pdf': 'pdf',
    'doc': 'office',
    'docx': 'office',
    'xls': 'office',
    'xlsx': 'office',
    'ppt': 'office',
    'pptx': 'office',
    '7z': '7z',      # 7-Zip
}

# 任务类型
class TaskType:
    EXTRACT_HASH = 1
    CRACK_HASH = 2
    AUTO_DETECT = 3
    GENERIC_TASK = 4

# 任务状态
class TaskStatus:
    PENDING = 0
    RUNNING = 1
    COMPLETED = 2
    FAILED = 3
    CANCELED = 4

# 异步任务类
class AsyncTask:
    def __init__(self, task_id, task_type, func, args=(), kwargs=None, callback=None, error_callback=None):
        self.task_id = task_id
        self.task_type = task_type
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.callback = callback
        self.error_callback = error_callback
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None
        
    def run(self):
        self.status = TaskStatus.RUNNING
        self.start_time = time.time()
        try:
            self.result = self.func(*self.args, **self.kwargs)
            self.status = TaskStatus.COMPLETED
            if self.callback:
                self.callback(self.result)
        except Exception as e:
            self.error = e
            self.status = TaskStatus.FAILED
            if self.error_callback:
                self.error_callback(e)
        finally:
            self.end_time = time.time()
            return self.result
            
    def cancel(self):
        if self.status == TaskStatus.PENDING or self.status == TaskStatus.RUNNING:
            self.status = TaskStatus.CANCELED
            return True
        return False
        
    def get_execution_time(self):
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0

# 任务管理器类
class TaskManager:
    def __init__(self, max_workers=MAX_WORKERS):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks = {}
        self.task_queue = queue.Queue()
        self.task_id_counter = 0
        self.lock = threading.Lock()
        
    def generate_task_id(self):
        with self.lock:
            self.task_id_counter += 1
            return self.task_id_counter
            
    def submit_task(self, task_type, func, args=(), kwargs=None, callback=None, error_callback=None):
        task_id = self.generate_task_id()
        task = AsyncTask(task_id, task_type, func, args, kwargs, callback, error_callback)
        self.tasks[task_id] = task
        future = self.executor.submit(task.run)
        future.add_done_callback(lambda f: self._task_done(task_id, f))
        return task_id
        
    def _task_done(self, task_id, future):
        task = self.tasks.get(task_id)
        if task:
            try:
                # 防止再次触发异常
                future.result()
            except Exception:
                # 异常已在任务运行中处理
                pass
                
    def cancel_task(self, task_id):
        task = self.tasks.get(task_id)
        if task:
            return task.cancel()
        return False
        
    def get_task(self, task_id):
        return self.tasks.get(task_id)
        
    def get_task_status(self, task_id):
        task = self.get_task(task_id)
        if task:
            return task.status
        return None
        
    def shutdown(self):
        self.executor.shutdown(wait=False)
        
    def get_active_tasks(self):
        return {task_id: task for task_id, task in self.tasks.items() 
                if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]}
                
    def add_task(self, thread_obj):
        """添加自定义线程任务
        
        Args:
            thread_obj: 线程对象，如HashcatThread
        """
        # 启动线程
        if thread_obj and isinstance(thread_obj, QtCore.QThread):
            thread_obj.start()
            return True
        return False
        
    def stop_all_tasks(self):
        """停止所有任务"""
        # 取消所有任务
        for task_id, task in list(self.tasks.items()):
            self.cancel_task(task_id)
        
        # 关闭线程池
        self.executor.shutdown(wait=False)
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Hashcat进程线程
class HashcatThread(QtCore.QThread):
    progress_signal = pyqtSignal(int)  # 进度信号
    log_signal = pyqtSignal(str)  # 日志信号
    finished_signal = pyqtSignal(dict)  # 完成信号
    status_signal = pyqtSignal(str, str)  # 状态信号
    
    def __init__(self, cmd=None, cwd=None, hashcat_path=None, hash_value=None, hash_mode=None,
                 attack_mode=None, dict_path=None, rule_path=None, mask=None, dict1_path=None,
                 dict2_path=None, use_gpu=True, workload=2, threads=None, device=None, memory_limit=None,
                 session=None, restore=False):
        """增强版初始化方法，支持直接构建命令或提供各种参数自动构建
        
        Args:
            cmd: 直接指定的命令行参数列表
            cwd: 工作目录
            hashcat_path: hashcat可执行文件路径
            hash_value: 哈希值
            hash_mode: 哈希模式
            attack_mode: 攻击模式 (0=字典, 1=组合, 3=掩码, 6=混合前缀, 7=混合后缀)
            dict_path: 字典路径
            rule_path: 规则文件路径
            mask: 掩码
            dict1_path: 组合攻击第一个字典路径
            dict2_path: 组合攻击第二个字典路径
            use_gpu: 是否使用GPU
            workload: 工作负载 (1=低, 2=默认, 3=高, 4=极高)
            threads: CPU线程数
            device: 指定GPU设备ID
            memory_limit: 内存限制，格式如"1024M"或"1G"
            session (str): hashcat session名
            restore (bool): 是否为恢复模式
        """
        super().__init__()
        
        self.session = session
        self.restore = restore
        self.cmd = []
        self.cwd = cwd
        self.hashcat_path = hashcat_path
        self.hash_value = hash_value
        self.hash_mode = hash_mode
        self.attack_mode = attack_mode
        self.dict_path = dict_path
        self.rule_path = rule_path
        self.mask = mask
        self.dict1_path = dict1_path
        self.dict2_path = dict2_path
        self.use_gpu = use_gpu
        self.workload = workload
        self.threads = threads
        self.device = device
        self.memory_limit = memory_limit
        self.temp_file = None
        self.process = None
        self._stop_event = threading.Event()
        self.cmd_output = []
        self.last_progress_time = time.time()  # 上次进度更新时间
        
        if hashcat_path:
            self.cmd.append(hashcat_path)
        if self.restore:
            self.cmd.append('--restore')
        if self.session:
            self.cmd.extend(['--session', str(self.session)])
        if hash_mode and not self.restore:
            self.cmd.extend(['-m', str(hash_mode)])
        
        # 7z哈希格式二次校验
        if str(hash_mode) == '11600' and not hash_value.strip().startswith('$7z$'):
            from PyQt5 import QtWidgets
            QtWidgets.QMessageBox.critical(None, "哈希格式错误", "7z破解仅支持以$7z$开头的哈希！请检查哈希提取流程。")
            self.cmd = []
            self.temp_file = None
            self.cwd = cwd
            return
        
        # 检查hashcat版本
        import subprocess
        try:
            version_out = subprocess.check_output([hashcat_path, '--version'], universal_newlines=True)
            # 提取 v6.2.6 或 6.2.6 的主次版本号
            match = re.search(r'v?(\d+)\.(\d+)', version_out)
            if not match:
                raise ValueError(f"无法解析Hashcat版本号: {version_out}")
            major, minor = int(match.group(1)), int(match.group(2))
            if major < 6 or (major == 6 and minor < 1):
                from PyQt5 import QtWidgets
                QtWidgets.QMessageBox.critical(None, "Hashcat版本过低", f"检测到Hashcat版本: {version_out.strip()}\n7z破解需要6.1.0及以上版本！")
                self.cmd = []
                self.temp_file = None
                self.cwd = cwd
                return
        except Exception as e:
            from PyQt5 import QtWidgets
            QtWidgets.QMessageBox.critical(None, "Hashcat检测失败", f"无法检测Hashcat版本: {e}")
            self.cmd = []
            self.temp_file = None
            self.cwd = cwd
            return
        
        # 检查同目录下是否有hashcat.exe进程
        import psutil
        exe_dir = os.path.dirname(os.path.abspath(hashcat_path))
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['name'] and 'hashcat' in proc.info['name'].lower():
                    if proc.info['exe'] and os.path.dirname(proc.info['exe']) == exe_dir:
                        from PyQt5 import QtWidgets
                        QtWidgets.QMessageBox.critical(None, "Hashcat进程冲突", f"检测到同目录下已有hashcat进程(PID: {proc.info['pid']})在运行，建议先关闭后再尝试！")
                        self.cmd = []
                        self.temp_file = None
                        self.cwd = cwd
                        return
            except Exception:
                continue
        
        # 写入哈希值，去除BOM、空格、换行，只保留一行
        hash_file = None
        try:
            clean_hash = hash_value.strip().split("\n")[0].strip()
            # 去除BOM
            if clean_hash.startswith(codecs.BOM_UTF8.decode()):
                clean_hash = clean_hash.lstrip(codecs.BOM_UTF8.decode())
            hash_file = tempfile.NamedTemporaryFile(delete=False, suffix='.hash')
            hash_file.write(clean_hash.encode('utf-8'))
            hash_file.close()
            self.log_signal.emit(f"哈希已写入临时文件: {hash_file.name}")
        except Exception as e:
            self.log_signal.emit(f"写入哈希文件出错: {str(e)}")
            if hash_file:
                hash_file.close()
        
        # 基本命令
        self.cmd.append(hash_file.name)
        self.cmd.append('--status')
        self.cmd.append('--status-timer=1')
        
        # 添加--force参数，忽略警告和错误
        self.cmd.append('--force')
        
        # 禁用potfile，避免hashcat报告"所有哈希已在potfile中"的问题
        self.cmd.append('--potfile-disable')
        
        # 添加性能设置
        if not use_gpu:
            self.cmd.extend(['--opencl-device-types=1'])  # 使用CPU
        elif device is not None:
            self.cmd.extend([f'--opencl-devices={device}'])  # 指定GPU设备
        
        # 工作负载
        self.cmd.extend([f'--workload-profile={workload}'])
        
        # 线程数
        if threads:
            self.cmd.extend([f'--threads={threads}'])
        
        # GPU模式下内存限制（用--segment-size参数）
        if self.use_gpu and self.memory_limit:
            # 只取数字部分，单位MB
            m = re.match(r"(\d+)(?:\s*[MG]B)?", str(self.memory_limit), re.IGNORECASE)
            if m:
                seg_size = m.group(1)
                self.cmd.extend([f'--segment-size={seg_size}'])
                self.log_signal.emit(f"[*] 已为GPU模式添加--segment-size={seg_size} (MB)，部分显卡有效")
        
        # 攻击模式和相关参数
        if attack_mode is not None:
            self.cmd.extend(['-a', str(attack_mode)])
            
            # 根据攻击模式添加必要参数
            if attack_mode == 0:  # 字典攻击
                if dict_path:
                    self.cmd.append(dict_path)
                # 如果有规则文件
                if rule_path:
                    self.cmd.extend(['-r', rule_path])
            elif attack_mode == 1:  # 组合攻击
                if dict1_path and dict2_path:
                    self.cmd.extend([dict1_path, dict2_path])
            elif attack_mode == 3:  # 掩码攻击
                if mask:
                    # 使用引号包围掩码以避免PowerShell等Shell解析问题
                    if ' ' in mask or '?' in mask or '*' in mask:
                        # 不再使用引号包围，而是直接传递掩码，避免PowerShell的引号解析问题
                        self.log_signal.emit(f"掩码包含特殊字符: {mask}")
                        self.cmd.append(mask)
                    else:
                        self.cmd.append(mask)
            elif attack_mode == 6 or attack_mode == 7:  # 混合攻击
                if dict_path and mask:
                    self.cmd.extend([dict_path, mask])
        
        # 对于RAR5哈希，添加额外调试参数
        if hash_mode == 13000:
            self.log_signal.emit("注意: RAR5掩码攻击可能需要较长时间")
            # 添加以下注释行的代码以获取更多调试信息（仅在需要时打开）
            # self.cmd.extend(['--debug-mode=1'])
            # self.cmd.extend(['--debug-file=rar5-debug.txt'])
        
        # 禁用警告
        self.cmd.append('--quiet')
        
        # 记录临时文件路径
        self.temp_file = hash_file.name
    
    def __del__(self):
        """析构函数，清理临时文件"""
        if hasattr(self, 'temp_file') and self.temp_file:
            try:
                import os
                if os.path.exists(self.temp_file):
                    os.unlink(self.temp_file)
            except:
                pass
    
    def run(self):
        import subprocess
        import re
        import os
        import threading
        self.start_time = time.time()
        
        # 新增：超时参数（可配置）
        MAX_RUNTIME_SECONDS = 2 * 60 * 60  # 2小时
        NO_OUTPUT_TIMEOUT = 10 * 60        # 10分钟
        
        try:
            self.log_signal.emit("[*] 启动破解进程...")
            
            # 如果cmd为空，说明前置检测未通过，直接返回
            if not self.cmd:
                self.log_signal.emit("[!] 未生成破解命令，已中止运行。")
                return
            
            # 记录完整命令
            cmd_str = " ".join(str(c) for c in self.cmd)
            self.log_signal.emit(f"[*] 执行命令: {cmd_str}")
            
            # 检查hashcat.potfile是否存在并备份
            if self.cwd:
                potfile_path = os.path.join(self.cwd, "hashcat.potfile")
                if os.path.exists(potfile_path):
                    backup_path = os.path.join(self.cwd, "hashcat.potfile.bak")
                    try:
                        import shutil
                        shutil.copy2(potfile_path, backup_path)
                        self.log_signal.emit(f"[*] 已备份hashcat.potfile到 {backup_path}")
                    except Exception as e:
                        self.log_signal.emit(f"[!] 备份hashcat.potfile失败: {str(e)}")
                    self.log_signal.emit("[*] 检测到hashcat.potfile，已禁用potfile功能")
            
            # 创建进程
            try:
                self.process = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    cwd=self.cwd,  # 指定工作目录
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.log_signal.emit(f"[*] 进程ID: {self.process.pid}")
            except Exception as e:
                self.log_signal.emit(f"[!] 创建进程失败: {str(e)}")
                if "找不到指定的文件" in str(e):
                    self.log_signal.emit("[!] 找不到hashcat可执行文件，请检查路径设置")
                elif "拒绝访问" in str(e):
                    self.log_signal.emit("[!] 访问被拒绝，可能需要管理员权限运行或文件被占用")
                raise
            
            # 新增：进程超时和无输出超时检测线程
            def timeout_watcher():
                while True:
                    if self._stop_event.is_set():
                        break
                    now = time.time()
                    if now - self.start_time > MAX_RUNTIME_SECONDS:
                        self.log_signal.emit(f"[!] 进程运行超出最大时长({MAX_RUNTIME_SECONDS//3600}小时)，已自动终止！")
                        try:
                            self.process.terminate()
                        except Exception:
                            pass
                        break
                    if now - self.last_progress_time > NO_OUTPUT_TIMEOUT:
                        self.log_signal.emit(f"[!] 进程{self.process.pid} {NO_OUTPUT_TIMEOUT//60}分钟无输出，已自动终止！")
                        try:
                            self.process.terminate()
                        except Exception:
                            pass
                        break
                    if self.process.poll() is not None:
                        break
                    time.sleep(5)
            watcher_thread = threading.Thread(target=timeout_watcher, daemon=True)
            watcher_thread.start()
            
            # 读取进程输出
            progress_re = re.compile(r'Progress\.+:\s+(\d+)%')
            speed_re = re.compile(r'Speed\.+:\s+(.+)$')
            time_re = re.compile(r'Time\.Estimated\.+:\s+(.+)$')
            recovered_re = re.compile(r'Recovered\.+:\s+(\d+)/\d+')
            status_prompt_re = re.compile(r'\[s\]tatus \[p\]ause \[b\]ypass \[c\]heckpoint \[f\]inish \[q\]uit')
            
            result_dict = {}
            showed_running = False
            error_detected = False
            error_msg = ""
            
            # 计数器，用于记录输出行数
            line_count = 0
            has_output = False
            start_time = time.time()
            last_output_time = start_time
            password_found = False  # 新增变量，确保只提取第一个有效密码
            
            for line in self.process.stdout:
                # 记录有输出
                has_output = True
                line_count += 1
                
                # 检查线程是否被终止
                if self._stop_event.is_set():
                    break
                
                # 保存输出行
                line_text = line.strip()
                self.cmd_output.append(line_text)
                    
                # 输出日志
                self.log_signal.emit(line_text)
                
                # 检测错误信息
                if "error" in line_text.lower() or "Separator unmatched" in line_text or "No hashes loaded" in line_text:
                    error_detected = True
                    error_msg = line_text
                
                # 检测特定的RAR5错误
                if "$rar5$" in " ".join(str(c) for c in self.cmd) and "OpenCL" in line_text and "error" in line_text.lower():
                    error_detected = True
                    error_msg = line_text
                    self.log_signal.emit("[!] 检测到OpenCL错误，RAR5破解需要OpenCL支持")
                
                # 当首次看到状态提示时，增加一条额外日志，表明破解正在进行中
                if status_prompt_re.search(line) and not showed_running:
                    self.log_signal.emit("[*] hashcat已初始化完成，正在破解中...")
                    self.log_signal.emit("[*] 该过程可能需要较长时间，您可以随时点击\"停止破解\"按钮")
                    showed_running = True
                
                # 匹配进度
                progress_match = progress_re.search(line)
                if progress_match:
                    progress = int(progress_match.group(1))
                    # 限制进度更新频率，避免UI卡顿
                    current_time = time.time()
                    if current_time - self.last_progress_time > 0.5:  # 每0.5秒最多更新一次
                        self.progress_signal.emit(progress)
                        self.last_progress_time = current_time
                
                # 匹配速度
                speed_match = speed_re.search(line)
                if speed_match:
                    result_dict['speed'] = speed_match.group(1)
                
                # 匹配估计时间
                time_match = time_re.search(line)
                if time_match:
                    result_dict['estimated_time'] = time_match.group(1)
                
                # 匹配恢复数量 - 如果大于0，表示找到了密码
                recovered_match = recovered_re.search(line)
                if recovered_match and int(recovered_match.group(1)) > 0:
                    result_dict['status'] = 'found'
                
                # 检查是否找到密码（只提取第一个有效密码，兼容所有hashcat格式）
                if not password_found and ":" in line_text:
                    hash_part, password = line_text.split(":", 1)
                    password = password.strip()
                    # 整合并增强：排除所有hashcat状态/特征行
                    hashcat_status_keywords = [
                        "pure kernel", "optimized kernel", "device", "speed", "progress", "candidates", "recovered",
                        "session", "status", "hash.mode", "hash.target", "time.started", "time.estimated", "kernel.feature",
                        "salt:", "amplifier:", "iteration:", "restore.point", "restore.sub", "rejected", "digests", "hashes"
                    ]
                    if any(kw in password.lower() for kw in hashcat_status_keywords):
                        continue
                    # 排除所有掩码格式如 ?d?d?d?d?d?d 或 ?d?d?d?d?d?d [6]
                    if re.match(r"^(?:\?[a-z0-9])+(?:\s*\[\d+\])?$", password, re.IGNORECASE):
                        continue
                    # 排除已知非密码行和模式号描述
                    if password and password.lower() not in [
                        "device generator", "hashcat", "candidates", "progress", "recovered", "session", "status"
                    ] and len(password) <= 128:
                        # 只允许 hash_part 以 $7z$、$rar5$、$zip2$、$office$、$pdf$ 等哈希前缀开头
                        if not hash_part.startswith(("$7z$", "$rar5$", "$zip2$", "$office$", "$pdf$")):
                            continue
                        # 排除明显为时间、日期、状态等内容
                        if any(x in password for x in [",", "(", ")", "AM", "PM", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
                            continue
                        if re.match(r"^\d{4,6} ?\([^)]+\)$", password):
                            continue  # 跳过如"11600 (7-Zip)"
                        if password.isdigit() and int(password) in [11600, 13000, 13600, 10500, 9800, 9400]:
                            continue  # 跳过模式号
                        # 再排除 hash_part 明显不是 hash（如包含空格、tab、特殊提示等）
                        if len(hash_part) > 0 and " " not in hash_part and "\t" not in hash_part and not hash_part.lower().startswith(("session", "status", "device", "hashcat")):
                            self.log_signal.emit(f"[*] 找到密码: {password}")
                            result_dict = {'success': True, 'password': password}
                            password_found = True
                            break
                        # 新增：排除所有 guess 相关状态行
                        if "guess" in password.lower():
                            continue
                    # 排除包含范围/列表符号的内容
                    if "->" in password or "..." in password:
                        continue
            
            # 如果没有任何输出，记录警告
            if not has_output:
                self.log_signal.emit("[!] 警告：进程没有产生任何输出，可能启动失败")
                
                # 检查OpenCL目录是否存在
                if self.cwd and "-a 3" in cmd_str:
                    opencl_path = os.path.join(self.cwd, "OpenCL")
                    if not os.path.exists(opencl_path):
                        self.log_signal.emit("[!] 错误: 未找到OpenCL目录，这是GPU破解必需的")
                        self.log_signal.emit("[!] 建议: 安装OpenCL驱动或使用CPU引擎")
                        error_detected = True
                        error_msg = "未找到OpenCL目录，这是GPU破解必需的"
            elif line_count < 3:
                self.log_signal.emit(f"[!] 警告：进程只产生了 {line_count} 行输出，异常终止")
            
            # 等待进程结束
            return_code = self.process.wait()
            elapsed_time = time.time() - start_time
            self.log_signal.emit(f"[*] 进程退出代码: {return_code}")
            self.log_signal.emit(f"[*] 进程运行时间: {elapsed_time:.2f} 秒")
            
            # 如果是掩码攻击且迅速返回，提供更多信息
            if "-a 3" in cmd_str and (line_count < 5 or elapsed_time < 3.0):
                self.log_signal.emit("[*] 掩码攻击过快结束，可能原因:")
                self.log_signal.emit("   1. 掩码格式不正确")
                self.log_signal.emit("   2. 哈希格式不兼容")
                self.log_signal.emit("   3. GPU驱动或Hashcat版本问题")
                self.log_signal.emit(f"[*] 建议尝试简单掩码如 ?d?d?d?d 或使用字典攻击")
                
                # 检查hashcat.log文件
                if self.cwd:
                    log_path = os.path.join(self.cwd, "hashcat.log")
                    if os.path.exists(log_path):
                        self.log_signal.emit("[*] 检测到hashcat.log文件，尝试分析错误...")
                        try:
                            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                                log_content = f.read()
                                # 提取最后500个字符作为错误分析
                                last_part = log_content[-500:] if len(log_content) > 500 else log_content
                                self.log_signal.emit(f"[*] hashcat.log最后部分内容:\n{last_part}")
                        except Exception as e:
                            self.log_signal.emit(f"[!] 无法读取hashcat.log: {str(e)}")
            
            # 检查是否找到密码
            if result_dict.get('status') == 'found' and result_dict.get('password'):
                # 破解成功
                result_dict['success'] = True
                result_dict['message'] = "破解成功"
                self.status_signal.emit("破解成功", "success")
                self.log_signal.emit(f"[!] 找到密码: {result_dict['password']}")
            else:
                # 尝试再次从输出中查找密码模式
                # 特别是检查 RAR5 特有的密码输出格式
                rar5_pattern = r'\$rar5\$.*?:([0-9a-zA-Z]+)(?:\s|$)'
                for line in self.cmd_output:
                    if '$rar5$' in line and ':' in line:
                        match = re.search(rar5_pattern, line)
                        if match:
                            password = match.group(1)
                            # 验证是否像有效的密码（不包含非预期文本）
                            if not any(x in password for x in ["Device", "Candidate", "Progress", "Recovered"]):
                                result_dict['success'] = True
                                result_dict['password'] = password
                                result_dict['message'] = "破解成功"
                                self.status_signal.emit("破解成功", "success")
                                self.log_signal.emit(f"[!] 找到密码（从输出重新提取）: {password}")
                                break
                
                # 如果仍未找到密码
                if not result_dict.get('success', False):
                    # 破解失败或未找到密码
                    result_dict['success'] = False
                    
                    # 检查是否有特定的错误信息
                    if error_detected:
                        result_dict['error'] = error_msg
                    else:
                        # 检查完整输出中是否有任何错误信息
                        for line in self.cmd_output:
                            if "error" in line.lower() or "failed" in line.lower():
                                result_dict['error'] = line
                                break
                        
                        # 如果没有找到具体错误，使用通用消息
                        if 'error' not in result_dict:
                            result_dict['error'] = "未找到破解结果"
                    
                    self.log_signal.emit(f"[!] 未找到破解结果")
                    self.status_signal.emit("破解失败", "error")
            
            # 发送结果信号
            self.finished_signal.emit(result_dict)
            
        except Exception as e:
            # 处理异常
            import traceback
            self.log_signal.emit(f"[!] 错误: {str(e)}")
            self.log_signal.emit(f"[!] 详细错误: {traceback.format_exc()}")
            self.status_signal.emit("破解错误", "error")
            
            # 创建错误结果
            result_dict = {
                'success': False,
                'error': str(e),
                'message': "破解过程中发生错误"
            }
            
            # 发送结果信号
            self.finished_signal.emit(result_dict)
        
        finally:
            # 清理资源
            if hasattr(self, 'process') and self.process:
                try:
                    self.process.terminate()
                except:
                    pass

    def kill(self):
        """终止进程"""
        if self.process and self.process.poll() is None:
            self._stop_event.set()
            try:
                self.process.terminate()
                # 给进程一些时间来终止
                time.sleep(0.5)
                # 如果进程还在运行，强制终止
                if self.process.poll() is None:
                    self.process.kill()
                    self.log_signal.emit("[*] 进程已强制终止")
                else:
                    self.log_signal.emit("[*] 进程已正常终止")
            except Exception as e:
                self.log_signal.emit(f"[!] 终止进程时出错: {str(e)}")
                # 尝试强制终止
                try:
                    self.process.kill()
                except:
                    pass

# 文件下载线程
class DownloadThread(QtCore.QThread):
    """文件下载线程类，支持进度报告和下载状态返回"""
    
    # 定义信号
    progress_signal = pyqtSignal(int)  # 进度信号 (0-100)
    finished_signal = pyqtSignal(bool, str)  # 完成信号 (成功标志, 文件路径/错误信息)
    
    def __init__(self, url, save_path):
        """初始化下载线程
        
        Args:
            url (str): 下载URL
            save_path (str): 保存路径
        """
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.is_canceled = False
        
    def cancel(self):
        """取消下载"""
        self.is_canceled = True
        
    def run(self):
        """运行下载线程"""
        try:
            import requests
            import time
            from urllib.parse import urlparse
            
            # 验证URL
            parsed_url = urlparse(self.url)
            if not parsed_url.scheme or not parsed_url.netloc:
                self.finished_signal.emit(False, "无效的URL")
                return
            
            # 创建保存目录
            os.makedirs(os.path.dirname(os.path.abspath(self.save_path)), exist_ok=True)
            
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # 创建会话，添加重试功能
            session = requests.Session()
            
            # 尝试使用新版参数名，如果失败则回退到旧版
            try:
                retry_strategy = requests.packages.urllib3.util.retry.Retry(
                    total=3,  # 总重试次数
                    backoff_factor=0.5,  # 重试间隔因子
                    status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
                    allowed_methods=["GET"]  # 新版本参数名
                )
            except TypeError:
                # 旧版本requests库
                retry_strategy = requests.packages.urllib3.util.retry.Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    method_whitelist=["GET"]  # 旧版本参数名
                )
                
            adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            # 使用流式下载以获取进度
            response = session.get(self.url, stream=True, headers=headers, timeout=30)
            response.raise_for_status()  # 检查HTTP错误
            
            # 获取文件大小
            total_size = int(response.headers.get('content-length', 0))
            
            # 更新间隔参数
            update_interval = 0.1  # 更新进度的最小时间间隔(秒)
            chunk_size = 8192  # 块大小
            
            if total_size == 0:
                # 无法获取文件大小，使用模拟进度
                downloaded = 0
                with open(self.save_path, 'wb') as f:
                    for i, chunk in enumerate(response.iter_content(chunk_size=chunk_size)):
                        if self.is_canceled:
                            self.finished_signal.emit(False, "下载已取消")
                            return
                            
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            # 每20个块更新一次进度
                            if i % 20 == 0:
                                # 模拟进度，最大到99%
                                percent = min(int(i / 100), 99)
                                self.progress_signal.emit(percent)
                
                # 完成下载
                self.progress_signal.emit(100)
                self.finished_signal.emit(True, self.save_path)
                return
                
            # 有文件大小，显示实际进度
            downloaded = 0
            last_percent = 0
            last_update_time = time.time()
            
            with open(self.save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self.is_canceled:
                        # 删除未完成的文件
                        f.close()
                        try:
                            os.remove(self.save_path)
                        except:
                            pass
                        self.finished_signal.emit(False, "下载已取消")
                        return
                        
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        percent = int(downloaded * 100 / total_size)
                        
                        # 限制更新频率，避免UI卡顿
                        current_time = time.time()
                        if percent != last_percent and (current_time - last_update_time) >= update_interval:
                            self.progress_signal.emit(percent)
                            last_percent = percent
                            last_update_time = current_time
            
            # 完成下载
            self.progress_signal.emit(100)
            self.finished_signal.emit(True, self.save_path)
            
        except requests.exceptions.RequestException as e:
            error_msg = f"下载请求错误: {str(e)}"
            print(error_msg)
            self.finished_signal.emit(False, error_msg)
        except Exception as e:
            error_msg = f"下载失败: {str(e)}"
            print(error_msg)
            self.finished_signal.emit(False, error_msg)

# 历史记录类
class CrackHistory:
    def __init__(self, history_file="crack_history.json"):
        self.history_file = history_file
        self.history_data = []
        # 自动创建历史文件（如不存在）
        if not os.path.exists(self.history_file):
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        self.load_history()
    
    def load_history(self):
        """加载历史记录"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history_data = json.load(f)
        except Exception as e:
            print(f"加载历史记录失败: {str(e)}")
            self.history_data = []
    
    def save_history(self):
        """保存历史记录"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存历史记录失败: {str(e)}")
    
    def add_record(self, file_path, hash_value, password, crack_time=None):
        """添加一条破解记录
        
        Args:
            file_path (str): 文件路径
            hash_value (str): 哈希值
            password (str): 破解出的密码
            crack_time (float, optional): 破解用时（秒）
        """
        if not hash_value or not password:
            return False
            
        # 获取当前时间，并确保年份正确（修复可能的系统日期问题）
        now = datetime.datetime.now()
        if now.year > 2024:  # 如果年份超过2024（可能系统日期有问题）
            print(f"系统日期异常: {now}，使用固定日期")
            # 使用当前时间但年份固定为2024
            now = now.replace(year=2024)
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # 提取文件类型
        file_ext = os.path.splitext(file_path)[1].lower().strip(".")
        
        # 创建记录
        record = {
            "id": len(self.history_data) + 1,
            "file_path": file_path,
            "file_type": file_ext,
            "hash_value": hash_value,
            "password": password,
            "crack_time": crack_time,  # 破解用时（秒）
            "timestamp": timestamp
        }
        
        # 添加到历史记录
        self.history_data.append(record)
        self.save_history()
        return True
    
    def delete_record(self, record_id):
        """删除一条记录"""
        for i, record in enumerate(self.history_data):
            if record.get("id") == record_id:
                del self.history_data[i]
                self.save_history()
                return True
        return False
    
    def clear_history(self):
        """清空历史记录"""
        self.history_data = []
        self.save_history()
        return True
    
    def get_all_records(self):
        """获取所有记录"""
        return self.history_data
    
    def get_count(self):
        """获取记录数量"""
        return len(self.history_data)
        
    def export_to_csv(self, export_file):
        """导出历史记录为CSV格式"""
        try:
            import csv
            with open(export_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "文件类型", "哈希值", "密码", "破解用时(秒)", "破解时间"])
                for record in self.history_data:
                    writer.writerow([
                        record.get('id', ''),
                        record.get('file_type', ''),
                        record.get('hash_value', ''),
                        record.get('password', ''),
                        record.get('crack_time', ''),
                        record.get('timestamp', '')
                    ])
            return True
        except Exception as e:
            print(f"导出CSV历史记录失败: {str(e)}")
            return False
    
    def export_to_json(self, export_file):
        """导出历史记录为JSON格式"""
        try:
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"导出JSON历史记录失败: {str(e)}")
            return False
    
    def export_to_text(self, export_file):
        """导出历史记录为文本格式"""
        try:
            with open(export_file, 'w', encoding='utf-8') as f:
                f.write("=== ZIP Cracker 破解历史记录 ===\n\n")
                for record in self.history_data:
                    f.write(f"ID: {record.get('id', '')}\n")
                    f.write(f"文件类型: {record.get('file_type', '')}\n")
                    f.write(f"哈希值: {record.get('hash_value', '')}\n")
                    f.write(f"密码: {record.get('password', '')}\n")
                    f.write(f"破解用时: {record.get('crack_time', '')} 秒\n")
                    f.write(f"破解时间: {record.get('timestamp', '')}\n")
                    f.write("-" * 50 + "\n\n")
            return True
        except Exception as e:
            print(f"导出文本历史记录失败: {str(e)}")
            return False

class DownloadThreadWithRetry(QtCore.QThread):
    """支持多源和重试的下载线程类"""
    
    # 定义信号
    progress_signal = QtCore.pyqtSignal(int)
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(bool, str)
    
    def __init__(self, urls, save_path, max_retries=3, timeout=30):
        """初始化下载线程
        
        Args:
            urls (list): 下载URL列表，按优先顺序排列
            save_path (str): 保存路径
            max_retries (int): 每个URL的最大重试次数
            timeout (int): 下载超时时间(秒)
        """
        super().__init__()
        self.urls = urls
        self.save_path = save_path
        self.max_retries = max_retries
        self.timeout = timeout
        self.is_cancelled = False
    
    def run(self):
        """运行下载线程"""
        # 尝试每个URL
        for url_index, url in enumerate(self.urls):
            if self.is_cancelled:
                break
                
            self.status_signal.emit(f"正在尝试下载源 {url_index+1}/{len(self.urls)}...")
            
            # 针对当前URL的重试
            for retry in range(self.max_retries):
                if self.is_cancelled:
                    break
                
                if retry > 0:
                    self.status_signal.emit(f"下载重试 ({retry}/{self.max_retries})...")
                    # 重试前等待一小段时间
                    time.sleep(1)
                
                try:
                    self.download_file(url)
                    # 下载成功，发送完成信号
                    self.finished_signal.emit(True, "下载成功")
                    return
                except Exception as e:
                    # 如果是最后一次重试，并且是最后一个URL
                    if retry == self.max_retries - 1 and url_index == len(self.urls) - 1:
                        error_msg = f"下载失败: {str(e)}"
                        self.status_signal.emit(error_msg)
                        self.finished_signal.emit(False, error_msg)
                    else:
                        # 准备下一次重试
                        self.status_signal.emit(f"下载出错: {str(e)}，准备重试...")
        
    def download_file(self, url):
        """下载文件
        
        Args:
            url (str): 下载URL
        
        Raises:
            Exception: 下载失败时抛出异常
        """
        try:
            # 创建会话，添加重试适配器
            session = requests.Session()
            
            # 尝试使用新版参数名，如果失败则回退到旧版
            try:
                retry_strategy = requests.packages.urllib3.util.retry.Retry(
                    total=3,  # 总重试次数
                    backoff_factor=0.5,  # 重试间隔因子
                    status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
                    allowed_methods=["GET"]  # 新版本参数名
                )
            except TypeError:
                # 旧版本requests库
                retry_strategy = requests.packages.urllib3.util.retry.Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    method_whitelist=["GET"]  # 旧版本参数名
                )
            
            adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            # 发起请求，添加更多的用户代理信息
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0'
            }
            
            response = session.get(url, stream=True, headers=headers, timeout=self.timeout)
            response.raise_for_status()  # 检查HTTP错误
            
            # 获取文件大小
            total_size = int(response.headers.get('content-length', 0))
            
            # 创建临时文件
            temp_file = self.save_path + ".tmp"
            
            # 下载文件
            downloaded_size = 0
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.is_cancelled:
                        f.close()
                        os.remove(temp_file)
                        return
                    
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # 更新进度
                        if total_size > 0:
                            progress = int(downloaded_size * 100 / total_size)
                            self.progress_signal.emit(progress)
                        else:
                            # 如果无法获取总大小，使用不确定的进度显示
                            self.progress_signal.emit(-1)
            
            # 重命名临时文件
            os.replace(temp_file, self.save_path)
            
            # 下载完成
            self.progress_signal.emit(100)
            
        except requests.exceptions.RequestException as e:
            # 处理请求异常
            error_msg = str(e)
            if "Connection aborted" in error_msg:
                error_msg = "连接被中断，请检查网络连接"
            elif "Remote end closed" in error_msg:
                error_msg = "远程服务器关闭了连接，可能是服务器过载"
            elif "Read timed out" in error_msg:
                error_msg = "读取超时，请检查网络连接或稍后重试"
            elif "Connection refused" in error_msg:
                error_msg = "连接被拒绝，服务器可能不可用"
            elif "Name or service not known" in error_msg:
                error_msg = "DNS解析失败，请检查网络连接"
            
            # 删除可能的临时文件
            temp_file = self.save_path + ".tmp"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            
            raise Exception(error_msg)
    
    def cancel(self):
        """取消下载"""
        self.is_cancelled = True 
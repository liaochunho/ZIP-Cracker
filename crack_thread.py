import os
import sys
import re
import subprocess
import time
from PySide6.QtCore import QThread, Signal
from utils import get_current_dir, check_cuda_support, find_tool, get_file_format

class CrackThread(QThread):
    update_log = Signal(str)  # 只接收一个字符串参数
    update_progress = Signal(int)
    crack_result = Signal(str)
    process_started = Signal()

    def __init__(self, file_path, mode='cpu'):
        super().__init__()
        self.file_path = file_path
        self.current_dir = get_current_dir()
        self.is_running = True
        self.temp_files = []
        self.enable_cuda = check_cuda_support()
        self.max_password_length = 12
        self.timeout_seconds = 30
        self.file_format = get_file_format(file_path)
        self.mode = mode  # 添加模式参数
        self.tool_paths = {}  # 存储工具路径
        self.hash_patterns = {
            'rar': re.compile(r'\$rar5\$.*'),
            'zip': re.compile(r'\$zip2\$.*'),
            '7z': re.compile(r'\$7z\$.*'),
            'word': re.compile(r'\$office\$.*?\*.*'),
            'pdf': re.compile(r'\$pdf\$.*')
        }

    def create_temp_file(self, hash_value):
        """创建临时哈希文件"""
        try:
            temp_hash_file = os.path.join(self.current_dir, "temp_hash.txt")
            with open(temp_hash_file, "w", encoding='utf-8') as f:
                f.write(hash_value)
            return temp_hash_file
        except Exception as e:
            raise Exception(f"创建临时文件失败: {str(e)}")

    def get_algorithm_id(self, hash_value):
        """根据文件格式和哈希值返回对应的算法ID"""
        # 特定格式检测
        if '$rar5$' in hash_value:
            return 13000  # RAR5
        elif '$rar3$' in hash_value:
            return 12500  # RAR3
        elif '$ssh$' in hash_value:
            return 22911  # SSH
        elif '$keepass$' in hash_value:
            return 13400  # KeePass
        elif '$gpg$' in hash_value:
            return 16700  # GPG
        elif '$bitlocker$' in hash_value:
            return 22100  # BitLocker
        elif '$WPAPSK$' in hash_value:
            return 2500   # WPA/WPA2
        # 移除: elif '$vnc$' in hash_value: return 11600  # VNC
        
        # 其他格式的算法ID映射
        algo_map = {
            'zip': 13600,    # WinZip
            'rar': 13000,    # RAR5 (默认)
            '7z': 11600,     # 7-Zip
            'word': 9400,    # MS Office 2007
            'pdf': 10500,    # PDF 1.7 Level 8
            'excel': 9400,   # MS Office 2007
            'powerpoint': 9400,  # MS Office 2007
            'ssh': 22911,    # SSH
            'keepass': 13400,  # KeePass
            'gpg': 16700,    # GPG
            'bitlocker': 22100,  # BitLocker
            'wifi': 2500,    # WPA/WPA2
            'vnc': 11600,    # VNC
            'shadow': 1800   # Unix Shadow
        }
        
        algo_id = algo_map.get(self.file_format)
        if not algo_id:
            raise Exception(f"无法识别文件格式: {self.file_format}")
            
        self.update_log.emit(f"使用算法ID: {algo_id}")
        return algo_id

    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            temp_hash_file = os.path.join(self.current_dir, "temp_hash.txt")
            if os.path.exists(temp_hash_file):
                os.remove(temp_hash_file)
        except Exception as e:
            self.update_log.emit(f"清理临时文件时出错: {str(e)}")

    def run(self):
        try:
            self.update_log.emit("=== 开始破解过程 ===")
            
            # 1. 提取哈希
            self.update_log.emit("步骤1: 提取哈希值")
            self.update_log.emit(f"处理文件: {self.file_path}")
            hash_value = self.extract_hash()
            if hash_value:
                self.update_log.emit(f"哈希值: {hash_value}")
            else:
                raise Exception("无法提取哈希值")

            # 2. 获取算法编号
            self.update_log.emit("步骤2: 识别哈希类型")
            algo_id = self.get_algorithm_id(hash_value)
            if not algo_id:
                raise Exception("无法识别算法类型")
            self.update_log.emit(f"算法编号: {algo_id}")

            # 3. 创建临时文件
            temp_hash_file = self.create_temp_file(hash_value)
            
            # 4. 调用Hashcat破解
            self.update_log.emit("步骤3: 开始破解")
            hashcat_path = find_tool("hashcat.exe", self.tool_paths)
            if not hashcat_path:
                raise Exception("找不到hashcat工具")
            
            # 设置工作目录为 hashcat 所在目录
            hashcat_dir = os.path.dirname(hashcat_path)
            
            # 创建临时字典文件
            dict_file = os.path.join(self.current_dir, "common_passwords.txt")
            with open(dict_file, "w", encoding='utf-8') as f:
                # 添加常见密码
                common_passwords = [
                    "123456", "123456789", "12345678", "password", "12345",
                    "1234", "1234567", "123123", "111111", "666666",
                    "888888", "000000", "abc123", "password123", "admin",
                    "admin123", "root", "121212", "123", "1234567890"
                ]
                f.write("\n".join(common_passwords))

            try:
                # 1. 先使用字典模式尝试常见密码
                dict_cmd = (f'cd /d "{hashcat_dir}" && hashcat.exe -m {algo_id} -a 0 "{temp_hash_file}" '
                          f'"{dict_file}" --potfile-disable --session=crack_session --restore-disable '
                          f'--status --status-timer=1 --force')
                
                self.update_log.emit("第1阶段: 尝试常见密码")
                self.update_log.emit(f"执行命令: {dict_cmd}")
                
                proc = subprocess.Popen(dict_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                     text=True, bufsize=1, universal_newlines=True)
                
                # 处理输出
                password = self.process_output(proc)
                if password:
                    return

                # 2. 如果字典模式失败，尝试6位数字组合
                if self.is_running:
                    num_cmd = (f'cd /d "{hashcat_dir}" && hashcat.exe -m {algo_id} -a 3 "{temp_hash_file}" '
                             f'"?d?d?d?d?d?d" --potfile-disable --session=crack_session --restore-disable '
                             f'--status --status-timer=1 --force')
                    
                    self.update_log.emit("第2阶段: 尝试6位数字组合")
                    self.update_log.emit(f"执行命令: {num_cmd}")
                    
                    proc = subprocess.Popen(num_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                         text=True, bufsize=1, universal_newlines=True)
                    
                    # 处理输出
                    password = self.process_output(proc)
                    if password:
                        return

                # 3. 如果还是失败，尝试1-8位任意字符组合
                if self.is_running:
                    brute_cmd = (f'cd /d "{hashcat_dir}" && hashcat.exe -m {algo_id} -a 3 "{temp_hash_file}" '
                                f'--increment --increment-min=1 --increment-max=8 "?a?a?a?a?a?a?a?a" '
                                f'--potfile-disable --session=crack_session --restore-disable '
                                f'--status --status-timer=1 --force')
                    
                    self.update_log.emit("第3阶段: 尝试1-8位任意字符组合")
                    self.update_log.emit(f"执行命令: {brute_cmd}")
                    
                    proc = subprocess.Popen(brute_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                         text=True, bufsize=1, universal_newlines=True)
                    
                    # 处理输出
                    password = self.process_output(proc)
                    if password:
                        return

            finally:
                # 清理临时字典文件
                try:
                    if os.path.exists(dict_file):
                        os.remove(dict_file)
                except:
                    pass

        except Exception as e:
            self.handle_error(str(e))
        finally:
            self.cleanup_temp_files()

    def extract_hash(self):
        tool_map = {
            'rar': 'rar2john.exe',
            'zip': 'zip2john.exe',
            '7z': '7z2john.pl',      # 确保使用 .pl 扩展名
            'word': 'office2john.py',
            'pdf': 'pdf2john.pl',    # 确保使用 .pl 扩展名
            'ssh': 'ssh2john.py',
            'keepass': 'keepass2john.exe',
            'gpg': 'gpg2john.exe',
            'bitlocker': 'bitlocker2john.exe',
            'wifi': 'hccap2john.exe'
            # 移除: 'vnc': 'vncpcap2john.exe'
        }
        
        tool_name = tool_map.get(self.file_format)
        if not tool_name:
            raise Exception(f"不支持的文件格式: {self.file_format}")
            
        # 尝试查找工具，如果有变体则尝试所有变体
        tool_path = find_tool(tool_name, self.tool_paths)
        if not tool_path and self.file_format in tool_variants:
            for variant in tool_variants[self.file_format]:
                tool_path = find_tool(variant, self.tool_paths)
                if tool_path:
                    tool_name = variant
                    break
                    
        if not tool_path:
            raise Exception(f"找不到工具: {tool_name}")
    
        try:
            # 特殊处理unshadow工具，它需要两个文件参数
            if tool_name == 'unshadow.exe':
                # 假设第二个文件是passwd文件，需要用户提供
                passwd_file = self.file_path.replace('shadow', 'passwd')
                if not os.path.exists(passwd_file):
                    raise Exception("处理shadow文件需要对应的passwd文件")
                cmd = f'"{tool_path}" "{passwd_file}" "{self.file_path}"'
            else:
                cmd = f'"{tool_path}" "{self.file_path}"'
                
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                encoding='utf-8'
            )
            if result.returncode != 0:
                error_msg = self.parse_tool_error(result.stderr)
                raise Exception(error_msg)
            return self.parse_hash_output(result.stdout)
        except subprocess.TimeoutExpired:
            raise Exception("哈希提取超时，可能遇到大文件或复杂加密")

    def parse_hash_output(self, output):
        """解析哈希输出"""
        if not output:
            raise Exception("无法提取哈希值")
            
        hash_lines = [line.strip() for line in output.split("\n") if line.strip()]
        if not hash_lines:
            raise Exception("提取的哈希值为空")
            
        raw_hash = hash_lines[-1]
        # 添加更多的哈希格式检测
        hash_prefixes = [
            '$rar5$', '$rar3$', '$zip2$', '$7z$', '$office$', 
            '$pdf$', '$ssh$', '$keepass$', '$gpg$', 
            '$bitlocker$', '$WPAPSK$', '$vnc$'
        ]
        
        if ':' in raw_hash:
            parts = raw_hash.split(':')
            for part in parts:
                for prefix in hash_prefixes:
                    if part.startswith(prefix):
                        return part
            # 如果没找到特定格式，返回最后一部分
            return parts[-1]
        return raw_hash

    def parse_tool_error(self, stderr):
        """解析工具错误输出"""
        if not stderr:
            return "未知错误"
        return stderr.strip()

    def handle_error(self, error_message):
        """处理错误"""
        self.update_log.emit(f"错误: {error_message}")
        self.crack_result.emit(f"破解失败: {error_message}")
        self.is_running = False

    def parse_progress(self, line):
        """解析进度信息"""
        try:
            if "Progress" in line:
                progress_part = line.split("Progress")[1].strip()
                if "/" in progress_part:
                    current, total = progress_part.split("/")[0:2]
                    current = int(current.strip())
                    total = int(total.split()[0].strip())
                    return int((current / total) * 100)
        except:
            pass
        return 0

    def process_output(self, proc):
        """处理破解进程的输出"""
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                    
                line = line.strip()
                if line:
                    self.update_log.emit(line)
                
                # 检测错误信息
                if "ERROR" in line.upper() or "FAILED" in line.upper():
                    self.update_log.emit(f"检测到错误: {line}")
                
                # 处理成功信息
                if ":" in line and not line.startswith("[") and not line.startswith("*") and not line.startswith("Approaching"):
                    try:
                        # 格式应该是 hash:password
                        hash_part, password = line.split(":", 1)
                        # 验证这是否真的是结果行
                        if hash_part.startswith("$"):
                            self.is_running = False
                            self.crack_result.emit(password.strip())
                            return password.strip()
                    except Exception as e:
                        self.update_log.emit(f"解析结果时出错: {str(e)}")
                
                # 处理进度信息
                if "Progress" in line:
                    try:
                        progress_part = line.split("Progress")[1].strip()
                        if "/" in progress_part:
                            current, total = progress_part.split("/")[0:2]
                            current = int(current.strip())
                            total = int(total.split()[0].strip())
                            progress = int((current / total) * 100)
                            self.update_progress.emit(progress)
                    except Exception as e:
                        self.update_log.emit(f"解析进度时出错: {str(e)}")
        except Exception as e:
            self.update_log.emit(f"处理输出时出错: {str(e)}")
        finally:
            proc.wait()
        return None
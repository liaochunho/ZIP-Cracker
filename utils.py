import os
import sys
import subprocess
import re

def get_current_dir():
    """获取程序运行目录（考虑打包为exe的情况）"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe，使用exe所在目录
        return os.path.dirname(sys.executable)
    else:
        # 如果是脚本运行
        return os.path.dirname(os.path.abspath(__file__))

def check_cuda_support():
    """检查是否支持CUDA"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--list-gpus'],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def find_tool(tool_name, tool_paths=None):
    """查找工具路径"""
    if tool_paths and tool_name in tool_paths:
        return tool_paths[tool_name]
        
    current_dir = get_current_dir()
    
    # 特别处理John工具，它们通常在run目录下
    for root, dirs, files in os.walk(current_dir):
        # 对于John工具
        if ('john' in os.path.basename(root).lower() or 
            any(f.startswith('rar2john') for f in files)) and tool_name != 'hashcat.exe':
            # 优先检查run子目录
            run_dir = os.path.join(root, "run")
            if os.path.exists(run_dir):
                tool_path = os.path.join(run_dir, tool_name)
                if os.path.exists(tool_path):
                    if tool_paths is not None:
                        tool_paths[tool_name] = tool_path
                    return tool_path
                    
                # 检查run目录下的子目录
                for subdir in os.listdir(run_dir):
                    subdir_path = os.path.join(run_dir, subdir)
                    if os.path.isdir(subdir_path):
                        tool_path = os.path.join(subdir_path, tool_name)
                        if os.path.exists(tool_path):
                            if tool_paths is not None:
                                tool_paths[tool_name] = tool_path
                            return tool_path
            
            # 如果没有run子目录或在run目录中找不到，尝试当前目录
            tool_path = os.path.join(root, tool_name)
            if os.path.exists(tool_path):
                if tool_paths is not None:
                    tool_paths[tool_name] = tool_path
                return tool_path
        
        # 对于hashcat，直接在目录中查找
        if ('hashcat' in os.path.basename(root).lower() or 
            'hashcat.exe' in files) and tool_name == 'hashcat.exe':
            tool_path = os.path.join(root, tool_name)
            if os.path.exists(tool_path):
                if tool_paths is not None:
                    tool_paths[tool_name] = tool_path
                return tool_path
    
    # 如果上面的方法找不到，尝试使用where命令
    try:
        path = subprocess.check_output(f"where {tool_name}", shell=True).decode().strip()
        if path:
            if tool_paths is not None:
                tool_paths[tool_name] = path
            return path
    except:
        pass
        
    return None

def get_file_format(file_path):
    """获取文件格式"""
    ext_map = {
        '.zip': 'zip', '.rar': 'rar', '.7z': '7z',
        '.doc': 'word', '.docx': 'word',
        '.xls': 'excel', '.xlsx': 'excel',
        '.ppt': 'powerpoint', '.pptx': 'powerpoint',
        '.pdf': 'pdf',
        '.kdb': 'keepass', '.kdbx': 'keepass',
        '.gpg': 'gpg', '.pgp': 'gpg',
        '.vhd': 'bitlocker', '.vhdx': 'bitlocker',
        '.hccap': 'wifi', '.hccapx': 'wifi'
        # 移除: '.pcap': 'vnc', '.pcapng': 'vnc'
    }
    
    ext = os.path.splitext(file_path)[1].lower()
    
    # 特殊处理SSH密钥文件
    if ext == '.pem' or ext == '.key' or ext == '.ppk':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(100)  # 只读取前100个字符进行判断
            if 'BEGIN' in content and ('RSA' in content or 'DSA' in content or 'EC' in content):
                return 'ssh'
    
    # 特殊处理shadow文件
    if os.path.basename(file_path) == 'shadow':
        return 'shadow'
    
    return ext_map.get(ext, "unknown")
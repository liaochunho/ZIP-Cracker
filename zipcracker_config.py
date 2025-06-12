#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ZIP Cracker - 配置管理模块
负责加载和保存应用程序配置
"""

import os
import json

CONFIG_FILE = "zipcracker_config.json"

# 默认配置
DEFAULT_CONFIG = {
    "john_path": "",
    "hashcat_path": "",
    "opencl_path": "",
    "perl_path": "",
    "last_dictionary_path": "",
    "last_rule_path": "",
    "last_attack_mode": 0,
    "recent_files": [],
    "ui": {
        "theme": "dark",
        "font_size": 12
    },
    # 日志相关配置
    "log_dir": "logs",
    "log_file": "zipcracker.log",
    "log_max_bytes": 5 * 1024 * 1024,  # 5MB
    "log_backup_count": 10,
    "log_level": "INFO",
    "log_console": True
}

class Config:
    """配置管理类，单例模式"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._config = DEFAULT_CONFIG.copy()
            cls._instance.load()
        return cls._instance
    
    def load(self):
        """加载配置"""
        try:
            # 自动创建配置文件（如不存在）
            if not os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 更新配置，保持默认值为基础
                    for key, value in loaded_config.items():
                        if key in self._config:
                            if isinstance(value, dict) and isinstance(self._config[key], dict):
                                # 如果是嵌套字典，递归更新
                                self._config[key].update(value)
                            else:
                                self._config[key] = value
        except Exception as e:
            try:
                from zipcracker_utils import log_error
                log_error(f"加载配置失败: {str(e)}")
            except Exception:
                pass
            print(f"加载配置失败: {str(e)}")
    
    def save(self):
        """保存配置"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            try:
                from zipcracker_utils import log_error
                log_error(f"保存配置失败: {str(e)}")
            except Exception:
                pass
            print(f"保存配置失败: {str(e)}")
    
    def get(self, key, default=None):
        """获取配置项"""
        # 支持使用点号分隔的嵌套键
        if "." in key:
            parts = key.split(".")
            value = self._config
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            return value
        
        return self._config.get(key, default)
    
    def set(self, key, value):
        """设置配置项"""
        # 支持使用点号分隔的嵌套键
        if "." in key:
            parts = key.split(".")
            config = self._config
            for part in parts[:-1]:
                if part not in config:
                    config[part] = {}
                elif not isinstance(config[part], dict):
                    config[part] = {}
                config = config[part]
            config[parts[-1]] = value
        else:
            self._config[key] = value
        
        # 自动保存配置
        self.save()
    
    def add_recent_file(self, file_path):
        """添加最近使用的文件"""
        if not file_path:
            return
            
        recent_files = self.get("recent_files", [])
        
        # 如果已存在，移到列表首位
        if file_path in recent_files:
            recent_files.remove(file_path)
        
        # 添加到列表首位
        recent_files.insert(0, file_path)
        
        # 限制列表长度为10
        if len(recent_files) > 10:
            recent_files = recent_files[:10]
            
        self.set("recent_files", recent_files)
    
    def clear_recent_files(self):
        """清空最近使用的文件列表"""
        self.set("recent_files", [])

# 创建全局配置实例
config = Config() 
import os
import shutil
import subprocess
import sys
import PyInstaller.__main__
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def clean_build():
    """清理构建目录"""
    dirs_to_clean = ['build', 'dist']
    files_to_clean = ['version_info.txt']
    
    # 清理目录
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                logging.info(f"已清理目录: {dir_name}")
            except Exception as e:
                logging.exception(f"清理目录 {dir_name} 时出错")
    
    # 清理文件
    for file_name in files_to_clean:
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
                logging.info(f"已清理文件: {file_name}")
            except Exception as e:
                logging.exception(f"清理文件 {file_name} 时出错")

def build_exe():
    """构建主程序exe"""
    PyInstaller.__main__.run([
        'zipcracker_app.py',
        '--name=ZIP-Cracker 4.0.5',
        '--windowed',
        '--onefile',
        '--icon=app.ico',
        '--add-data=app.ico;.',
        '--add-data=zipcracker.qss;.',
        '--add-data=dark.qss;.',
        '--add-data=zipcracker_models.py;.',
        '--add-data=zipcracker_utils.py;.',
        '--add-data=zipcracker_config.py;.',
        '--add-data=zipcracker_dialogs.py;.',
        '--add-data=zipcracker_config.json;.',
        '--add-data=crack_history.json;.',
        '--add-data=zipcracker_ui.py;.',
        '--noconfirm',
        '--clean',
        '--noupx',
        '--hidden-import=PyQt5',
        '--hidden-import=PyQt5.QtWidgets',
        '--hidden-import=PyQt5.QtCore',
        '--hidden-import=PyQt5.QtGui',
        '--hidden-import=qdarkstyle',
        '--hidden-import=requests',
        '--version-file=version_info.txt',
        '--optimize=2',
        '--noconsole'
    ])

def create_version_info():
    """创建版本信息文件"""
    version_info = """
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(4, 0, 4, 0),
    prodvers=(4, 0, 4, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'ZIPCracker Team'),
        StringStruct(u'FileDescription', u'ZIP-Cracker - 专业压缩包密码破解工具'),
        StringStruct(u'FileVersion', u'4.0.5'),
        StringStruct(u'InternalName', u'ZIP-Cracker'),
        StringStruct(u'LegalCopyright', u'Copyright (c) 2024 ZIPCracker Team'),
        StringStruct(u'OriginalFilename', u'ZIP-Cracker.exe'),
        StringStruct(u'ProductName', u'ZIP-Cracker'),
        StringStruct(u'ProductVersion', u'4.0.5'),
        StringStruct(u'Comments', u'压缩包密码破解工具')])
      ]), 
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
"""
    try:
        with open('version_info.txt', 'w', encoding='utf-8') as f:
            f.write(version_info)
        logging.info("版本信息文件创建成功")
    except Exception as e:
        logging.exception("创建版本信息文件时出错")
        raise

def check_and_install_dependencies():
    """检查并安装必要的依赖，并自动生成 requirements.txt（如不存在）"""
    required_packages = [
        'PyQt5',
        'qdarkstyle',
        'requests'
    ]
    if not os.path.exists('requirements.txt'):
        with open('requirements.txt', 'w', encoding='utf-8') as f:
            for pkg in required_packages:
                f.write(pkg + '\n')
        logging.info("已自动生成 requirements.txt")
    logging.info("检查依赖...")
    for package in required_packages:
        try:
            __import__(package)
            logging.info(f"✓ {package} 已安装")
        except ImportError:
            logging.warning(f"! {package} 未安装，正在安装...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                logging.info(f"✓ {package} 安装成功")
            except subprocess.CalledProcessError as e:
                logging.error(f"× {package} 安装失败: {str(e)}")
                return False
    return True

def main():
    try:
        logging.info("=== 开始打包准备 ===")
        if not check_and_install_dependencies():
            logging.error("依赖安装失败，打包终止")
            return 1
        import PyInstaller.__main__
        logging.info("1. 检查依赖...")
        check_and_install_dependencies()
        logging.info("2. 清理旧的构建文件...")
        clean_build()
        logging.info("3. 创建版本信息文件...")
        create_version_info()
        logging.info("4. 构建主程序exe...")
        build_exe()
        logging.info("5. 清理临时文件...")
        if os.path.exists('version_info.txt'):
            os.remove('version_info.txt')
        logging.info("=== 打包完成！===\n输出文件位于 dist 目录中")
    except Exception as e:
        logging.exception("打包过程出错")
        return 1
    return 0

if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        print("\n打包失败！")
    input("\n按回车键退出...") 
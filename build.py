import os
import PyInstaller.__main__

# 确保当前目录是项目目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 打包参数
params = [
    "main.py",                  # 主脚本
    "--name=ZIP Cracker2.0.1.2 by阿修",        # 应用名称
    "--noconsole",              # 不显示控制台
    "--onefile",                # 打包成单个文件
    "--clean",                  # 清理临时文件
    "--upx-dir=upx",            # 指定UPX目录
    "--icon=app.ico",           # 指定图标文件
]

# 执行打包
PyInstaller.__main__.run(params)

print("打包完成！")
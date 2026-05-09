import os
import shutil
import sys
import subprocess
from pathlib import Path


def print_separator():
    print("-" * 60)


def print_header():
    print_separator()
    print("\033[31m   警告：正在执行出厂设置重置操作   \033[0m")
    print_separator()
    print("此操作将永久删除以下所有本地数据：")
    print(" - 所有账号会话和 Cookie (data/cookies/)")
    print(" - 所有本地加密密钥 (data/keys/)")
    print(" - 核心数据库及发布历史 (data/database.db)")
    print(" - 所有运行日志和缓存文件")
    print("\n注意：源代码及虚拟环境 (.venv) 不受影响。\n")


def clean_directory(path):
    path_obj = Path(path)
    if path_obj.exists():
        print(f"正在移除目录: {path}")
        try:
            shutil.rmtree(path_obj)
        except Exception as e:
            print(f"移除 {path} 失败: {e}")


def main():
    # 启用 Windows 终端颜色支持并强制 UTF-8 输出
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass  # Python < 3.7

    # 检查命令行参数
    force_reset = "-Force" in sys.argv

    print_header()

    if force_reset:
        confirm = "y"
    else:
        try:
            user_input = input("确认恢复出厂设置？(y/n): ").strip().lower()
            confirm = user_input
        except KeyboardInterrupt:
            print("\n操作已取消。")
            return

    if confirm in ["y", "yes", "reset"]:
        print("\n\033[36m正在开始出厂重置流程...\033[0m")

        # 1. 清理目录
        targets = ["data", "logs", ".pytest_cache"]
        project_root = Path(__file__).parent.parent.parent

        for t in targets:
            clean_directory(project_root / t)

        # 2. 清理 __pycache__
        print("正在清理 Python 编译缓存 (__pycache__) ...")
        for p in project_root.rglob("__pycache__"):
            if p.is_dir():
                try:
                    shutil.rmtree(p)
                except Exception:
                    pass

        # 3. 重新初始化数据库
        print("\n\033[36m正在重新初始化数据库...\033[0m")
        db_init_script = project_root / "src" / "infrastructure" / "storage" / "database_init.py"

        if db_init_script.exists():
            try:
                # 优先使用 .venv 中的 python
                venv_python = project_root / ".venv" / "Scripts" / "python.exe"
                python_cmd = str(venv_python) if venv_python.exists() else sys.executable

                subprocess.run([python_cmd, str(db_init_script)], check=True)
                print("\n\033[32m出厂设置重置成功！项目已恢复到初始空状态。\033[0m")
            except subprocess.CalledProcessError:
                print("\n\033[31m数据库初始化失败，请检查错误日志。\033[0m")
        else:
            print(f"\n\033[33m未找到数据库初始化脚本: {db_init_script}\033[0m")

    else:
        print("\n\033[33m操作已取消。未对数据进行任何更改。\033[0m")

    print_separator()
    if not force_reset:
        input("按 Enter 键退出...")


if __name__ == "__main__":
    main()



import os
import re
import sys
import datetime
import argparse
from pathlib import Path

# 定义项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 定义文件路径
PYPROJECT_TOML = PROJECT_ROOT / "pyproject.toml"
VERSION_PY = PROJECT_ROOT / "src/version.py"
CHANGELOG_MD = PROJECT_ROOT / "CHANGELOG.md"
INNO_SETUP_ISS = PROJECT_ROOT / "installers/inno_setup/setup_script.iss"
VERSION_JSON = PROJECT_ROOT / "version.json"

def get_current_version():
    """从 pyproject.toml 读取当前版本"""
    content = PYPROJECT_TOML.read_text(encoding="utf-8")
    match = re.search(r'version = "(.*?)"', content)
    if match:
        return match.group(1)
    raise ValueError("无法在 pyproject.toml 中找到版本号")

def bump_version(current_version, part):
    """计算新版本号"""
    major, minor, patch = map(int, current_version.split('.'))
    
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1
    else:
        raise ValueError(f"未知的更新类型: {part}")
        
    return f"{major}.{minor}.{patch}"

def update_files(new_version):
    """更新所有相关文件"""
    
    # 1. 更新 pyproject.toml
    content = PYPROJECT_TOML.read_text(encoding="utf-8")
    new_content = re.sub(r'version = ".*?"', f'version = "{new_version}"', content, count=1)
    PYPROJECT_TOML.write_text(new_content, encoding="utf-8")
    print(f"✅ 更新 pyproject.toml -> {new_version}")
    
    # 2. 更新 src/version.py
    content = VERSION_PY.read_text(encoding="utf-8")
    new_content = re.sub(r'__version__ = ".*?"', f'__version__ = "{new_version}"', content)
    VERSION_PY.write_text(new_content, encoding="utf-8")
    print(f"✅ 更新 src/version.py -> {new_version}")
    
    # 3. 更新 Inno Setup 版本号
    update_inno_setup(new_version)
    
    # 4. 更新 CHANGELOG.md
    update_changelog(new_version)
    
    # 5. 更新根目录 version.json（供 Gitee 更新检测；download_url 需发版后手动填或从 Release 复制）
    update_version_json(new_version)

def update_inno_setup(new_version):
    """更新 Inno Setup 脚本中的版本号"""
    if not INNO_SETUP_ISS.exists():
        print("⚠️ setup_script.iss 不存在，跳过更新")
        return
    
    content = INNO_SETUP_ISS.read_text(encoding="utf-8")
    new_content = re.sub(
        r'#define MyAppVersion ".*?"',
        f'#define MyAppVersion "{new_version}"',
        content,
        count=1
    )
    INNO_SETUP_ISS.write_text(new_content, encoding="utf-8")
    print(f"✅ 更新 setup_script.iss -> {new_version}")


def update_version_json(new_version):
    """更新根目录 version.json（version、release_date、notes）。
    download_url 默认为飞书发版说明页，用户「前往下载」在浏览器中按文档指引获取安装包。"""
    import json
    today = datetime.date.today().strftime("%Y-%m-%d")
    data = {
        "version": new_version,
        "release_date": today,
        "notes": "发版后请在此填写更新说明。",
        "download_url": "https://my.feishu.cn/docx/DpotdqxU8owf15xD54oc6P9KnWf",
    }
    VERSION_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 更新 version.json -> {new_version}（download_url 默认为飞书说明页）")


def update_changelog(new_version):
    """在 CHANGELOG.md 顶部插入新条目"""
    if not CHANGELOG_MD.exists():
        print("⚠️ CHANGELOG.md 不存在，跳过更新")
        return
        
    content = CHANGELOG_MD.read_text(encoding="utf-8")
    
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    # 构建新条目模板
    new_entry = f"""
## [{new_version}] - {today}

### 新增

### 优化

### 修复

"""
    
    # 查找 "## [Unreleased]" 或第一个版本标题作为插入点
    # 这里简单地在 "## [..." 第一次出现的地方之前插入
    # 或者寻找 "# 更新日志" 标题后的空行
    
    lines = content.splitlines()
    insert_index = -1
    
    for i, line in enumerate(lines):
        if line.startswith("## ["):
            insert_index = i
            break
            
    if insert_index != -1:
        lines.insert(insert_index, new_entry.strip() + "\n")
        new_content = "\n".join(lines)
        CHANGELOG_MD.write_text(new_content, encoding="utf-8")
        print(f"✅ 更新 CHANGELOG.md -> 添加 [{new_version}] 条目")
    else:
        # 如果没找到现有版本条目，追加到文件末尾（不太可能，除非是空文件）
        print("⚠️ 无法定位 CHANGELOG.md 插入点，请手动更新")

def main():
    parser = argparse.ArgumentParser(description="项目版本更新脚本")
    parser.add_argument("part", choices=["major", "minor", "patch", "set"], help="更新类型: major, minor, patch, set")
    parser.add_argument("version", nargs="?", default=None, help="当 part=set 时，直接指定目标版本号，如 1.2.3")
    
    args = parser.parse_args()
    
    try:
        current_version = get_current_version()
        
        if args.part == "set":
            if not args.version:
                print("❌ 使用 set 模式时必须提供目标版本号，例如: python update_version.py set 1.2.3")
                sys.exit(1)
            # 简单校验格式
            if not re.match(r'^\d+\.\d+\.\d+$', args.version):
                print(f"❌ 版本号格式无效: {args.version}（应为 X.Y.Z）")
                sys.exit(1)
            new_version = args.version
        else:
            new_version = bump_version(current_version, args.part)
        
        print(f"🚀 准备从 {current_version} 更新到 {new_version}")
        update_files(new_version)
        print("\n🎉 版本更新完成！请记得完善 CHANGELOG.md 中的具体变更内容。")
        
    except Exception as e:
        print(f"❌ 更新失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

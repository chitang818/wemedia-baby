"""
媒小宝 - 一键测试入口脚本

用法:
  python scripts/test/run_tests.py                    # 全量测试（单元 + 集成）
  python scripts/test/run_tests.py unit               # 仅单元测试
  python scripts/test/run_tests.py integration        # 仅集成测试
  python scripts/test/run_tests.py --quick            # 快速模式（跳过 slow 标记的测试）
  python scripts/test/run_tests.py --module encrypt   # 按关键字筛选（pytest -k）
  python scripts/test/run_tests.py unit --no-cov      # 不生成覆盖率报告
  python scripts/test/run_tests.py --open             # 测试完成后自动打开 HTML 报告
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# 项目根目录（本文件位于 scripts/test/）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = PROJECT_ROOT / "test-reports"
COVERAGE_DIR = REPORT_DIR / "coverage"

REQUIRED_PACKAGES = [
    "pytest",
    "pytest_asyncio",
    "pytest_cov",
    "pytest_mock",
    "pytest_html",
]


def check_dependencies() -> bool:
    """检查测试依赖是否已安装"""
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg.replace("_", "-"))
    if missing:
        print(f"[错误] 缺少测试依赖，请先运行：pip install {' '.join(missing)}")
        return False
    return True


def build_pytest_args(
    mode: str,
    quick: bool,
    keyword: str | None,
    no_cov: bool,
) -> list[str]:
    """根据运行模式构建 pytest 命令行参数"""
    args: list[str] = [sys.executable, "-m", "pytest"]

    # 测试范围
    if mode == "unit":
        args += ["tests/unit"]
    elif mode == "integration":
        args += ["tests/integration"]
    else:
        args += ["tests"]

    # 快速模式：跳过 slow 标记
    if quick:
        args += ["-m", "not slow"]

    # 按关键字筛选
    if keyword:
        args += ["-k", keyword]

    # 测试结果报告
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "report.html"
    args += [
        f"--html={report_path}",
        "--self-contained-html",
        f"--junitxml={REPORT_DIR / 'junit.xml'}",
    ]

    # 覆盖率报告
    if not no_cov:
        COVERAGE_DIR.mkdir(parents=True, exist_ok=True)
        args += [
            "--cov=src",
            "--cov-report=term-missing",
            f"--cov-report=html:{COVERAGE_DIR}",
            "--cov-branch",
        ]

    return args


def print_banner(mode: str, quick: bool, keyword: str | None) -> None:
    width = 60
    print("=" * width)
    print("  媒小宝 - 自动化测试".center(width))
    print("=" * width)
    print(f"  模式: {mode or '全量'}")
    if quick:
        print("  选项: 快速模式（跳过 slow 测试）")
    if keyword:
        print(f"  关键字筛选: {keyword}")
    print(f"  报告目录: {REPORT_DIR}")
    print("=" * width)
    print()


def run_encoding_check() -> int:
    """Run the UTF-8 repository text gate before pytest."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "maintenance" / "check_text_encoding.py"),
        str(PROJECT_ROOT),
    ]
    print(f"Encoding check: {' '.join(cmd)}\n")
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT)).returncode


def parse_junit_stats(junit_path: Path) -> tuple[int, int, int] | None:
    """从 pytest --junitxml 输出解析 (通过数, 失败数含 error, 跳过数)；文件缺失或解析失败时返回 None。"""
    if not junit_path.is_file():
        return None
    try:
        import xml.etree.ElementTree as ET

        root = ET.parse(junit_path).getroot()
        suites: list[ET.Element] = []
        if root.tag == "testsuites":
            suites = list(root.findall("testsuite"))
        elif root.tag == "testsuite":
            suites = [root]
        else:
            return None
        tests = failures = errors = skipped = 0
        for s in suites:
            tests += int(s.get("tests") or 0)
            failures += int(s.get("failures") or 0)
            errors += int(s.get("errors") or 0)
            skipped += int(s.get("skipped") or 0)
        failed = failures + errors
        passed = max(0, tests - failed - skipped)
        return passed, failed, skipped
    except (ET.ParseError, ValueError, TypeError):
        return None


def update_summary_report(passed: int, failed: int, skipped: int, elapsed: float) -> None:
    """将测试结果写入 summary.html 的数字占位符"""
    summary_path = REPORT_DIR / "summary.html"
    if not summary_path.exists():
        return
    from datetime import datetime
    from re import sub

    content = summary_path.read_text(encoding="utf-8")
    total = passed + failed + skipped
    pass_rate = int(passed / total * 100) if total > 0 else 0
    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    content = sub(r"生成时间：.*?</div>", f"生成时间：{now_str}</div>", content)
    content = sub(r'id="stat-passed">[^<]*<', f'id="stat-passed">{passed}<', content)
    content = sub(r'id="stat-failed">[^<]*<', f'id="stat-failed">{failed}<', content)
    content = sub(r'id="stat-skipped">[^<]*<', f'id="stat-skipped">{skipped}<', content)
    content = sub(r'id="stat-skipped2">[^<]*<', f'id="stat-skipped2">{skipped}<', content)
    content = sub(r'id="stat-total">[^<]*<', f'id="stat-total">{total}<', content)
    content = sub(r'id="stat-rate">[^<]*<', f'id="stat-rate">{pass_rate}%<', content)
    content = sub(
        r'id="progress-bar"[^>]*style="width:[^"]*"',
        f'id="progress-bar" style="width:{pass_rate}%"',
        content,
    )
    summary_path.write_text(content, encoding="utf-8")


def print_summary(return_code: int, elapsed: float, no_cov: bool) -> None:
    print()
    print("=" * 60)
    if return_code == 0:
        print("  测试结果: 全部通过 [OK]".center(60))
    elif return_code == 1:
        print("  测试结果: 有测试失败 [FAIL]".center(60))
    elif return_code == 2:
        print("  测试结果: 测试中断 [INTERRUPTED]".center(60))
    elif return_code == 5:
        print("  测试结果: 未收集到任何测试 [NO TESTS]".center(60))
    else:
        print(f"  退出码: {return_code}".center(60))
    print(f"  耗时: {elapsed:.1f} 秒".center(60))
    print("=" * 60)
    print()
    print(f"  测试结果报告: {REPORT_DIR / 'report.html'}")
    if not no_cov:
        print(f"  覆盖率报告:   {COVERAGE_DIR / 'index.html'}")
    print()


def open_report(no_cov: bool) -> None:
    """在默认浏览器中打开测试报告"""
    report_path = REPORT_DIR / "report.html"
    if report_path.exists():
        import webbrowser

        webbrowser.open(str(report_path))
        print(f"已打开测试报告: {report_path}")
    if not no_cov:
        cov_path = COVERAGE_DIR / "index.html"
        if cov_path.exists():
            import webbrowser

            webbrowser.open(str(cov_path))
            print(f"已打开覆盖率报告: {cov_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="媒小宝一键测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["unit", "integration", "all"],
        default="all",
        help="测试范围：unit（单元）、integration（集成）、all（全量，默认）",
    )
    parser.add_argument("--quick", action="store_true", help="快速模式：跳过标记为 slow 的测试")
    parser.add_argument(
        "--module",
        "-k",
        metavar="KEYWORD",
        default=None,
        help="按关键字筛选测试（传给 pytest -k）",
    )
    parser.add_argument("--no-cov", action="store_true", help="不生成覆盖率报告（加快速度）")
    parser.add_argument(
        "--skip-encoding-check",
        action="store_true",
        help="Skip UTF-8 text encoding check",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_report",
        help="测试完成后自动在浏览器中打开报告",
    )

    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)
    if not check_dependencies():
        return 1

    print_banner(args.mode, args.quick, args.module)

    if not args.skip_encoding_check:
        encoding_result = run_encoding_check()
        if encoding_result != 0:
            print("[ERROR] UTF-8 encoding check failed")
            return encoding_result

    pytest_args = build_pytest_args(
        mode=args.mode,
        quick=args.quick,
        keyword=args.module,
        no_cov=args.no_cov,
    )

    print(f"执行命令: {' '.join(pytest_args)}\n")

    start = time.time()
    result = subprocess.run(pytest_args, cwd=str(PROJECT_ROOT))
    elapsed = time.time() - start

    print_summary(result.returncode, elapsed, args.no_cov)

    junit_path = REPORT_DIR / "junit.xml"
    stats = parse_junit_stats(junit_path)
    if stats is not None:
        p, f, s = stats
        update_summary_report(p, f, s, elapsed)
        print(f"  通俗摘要已更新: {REPORT_DIR / 'summary.html'}")
    else:
        print(
            f"  [提示] 未读取到 {junit_path.name}，summary.html 未更新。"
            "请确认通过 python scripts/test/run_tests.py（或 scripts/test/run_tests.bat）运行完整 pytest。"
        )

    if args.open_report:
        open_report(args.no_cov)

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())


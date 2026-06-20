path = 'scripts/build/build_nuitka.ps1'
with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith('$CheckImports = @('):
        skip = True
        new_lines.append('''$CheckImports = @(
    "PySide6",
    "qasync",
    "patchright",
    "tortoise.backends.sqlite",
    "aiosqlite",
    "aerich",
    "pydantic",
    "pydantic_core"
)
$Missing = @()
foreach ($imp in $CheckImports) {
    $code = "try:`n import $imp`n print('OK')`nexcept Exception:`n pass"
    $r = & $PythonExe -c $code 2>$null
    if ($r -ne 'OK') { $Missing += $imp }
}
if ($Missing.Count -gt 0) {
    Write-Log "以下包/模块无法导入，Nuitka 会报错。请检查 requirements.txt 与虚拟环境。" 'Red'
    Write-Log ($Missing -join ", ") 'Red'
    exit 1
}
Write-Log "已校验 Nuitka 将包含的包/模块均可导入。" 'Green'

# ============================================================
# 3.4 固化发行模式到产物（供用户机器运行时读取）
# ============================================================
''')
    elif line.startswith('$DistModeFile = Join-Path'):
        skip = False
        new_lines.append(line)
    else:
        if not skip:
            new_lines.append(line)

with open(path, 'w', encoding='utf-8-sig') as f:
    f.writelines(new_lines)

print("Fixed!")

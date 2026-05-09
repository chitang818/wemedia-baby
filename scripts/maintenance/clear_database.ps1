# Moved from scripts/utils/clear_database.ps1

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  清空数据库脚本" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 数据库路径
$dbPath = "$env:LOCALAPPDATA\\WeMediaBaby\\data\\database.db"

Write-Host "数据库路径: $dbPath" -ForegroundColor Yellow

if (-not (Test-Path $dbPath)) {
    Write-Host "错误: 数据库文件不存在！" -ForegroundColor Red
    exit 1
}

# 确认操作
Write-Host ""
Write-Host "警告: 此操作将删除所有账号和发布记录！" -ForegroundColor Red
Write-Host "数据库结构将保留，但所有数据将被清空。" -ForegroundColor Yellow
Write-Host ""
$confirm = Read-Host "确认继续？(输入 'yes' 确认)"

if ($confirm -ne "yes") {
    Write-Host "操作已取消。" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "开始清空数据库..." -ForegroundColor Cyan

try {
    # 加载 SQLite
    Add-Type -Path "System.Data.SQLite.dll" -ErrorAction Stop

    # 连接数据库
    $connectionString = "Data Source=$dbPath;Version=3;"
    $connection = New-Object System.Data.SQLite.SQLiteConnection($connectionString)
    $connection.Open()

    # 删除发布记录
    Write-Host "删除发布记录..." -ForegroundColor Yellow
    $command = $connection.CreateCommand()
    $command.CommandText = "DELETE FROM publish_records"
    $rowsAffected = $command.ExecuteNonQuery()
    Write-Host "  已删除 $rowsAffected 条发布记录" -ForegroundColor Green

    # 删除账号
    Write-Host "删除账号..." -ForegroundColor Yellow
    $command.CommandText = "DELETE FROM platform_accounts"
    $rowsAffected = $command.ExecuteNonQuery()
    Write-Host "  已删除 $rowsAffected 个账号" -ForegroundColor Green

    # 重置自增ID（可选）
    Write-Host "重置自增ID..." -ForegroundColor Yellow
    $command.CommandText = "DELETE FROM sqlite_sequence WHERE name IN ('publish_records', 'platform_accounts')"
    $command.ExecuteNonQuery() | Out-Null
    Write-Host "  自增ID已重置" -ForegroundColor Green

    # 关闭连接
    $connection.Close()

    Write-Host ""
    Write-Host "数据库清空完成！" -ForegroundColor Green
    Write-Host "现在可以重新登录账号并测试。" -ForegroundColor Cyan

} catch {
    Write-Host ""
    Write-Host "错误: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "如果上述方法失败，可以直接删除数据库文件：" -ForegroundColor Yellow
    Write-Host "  Remove-Item '$dbPath' -Force" -ForegroundColor White
    Write-Host "应用会在下次启动时自动重建数据库。" -ForegroundColor Yellow
    exit 1
}


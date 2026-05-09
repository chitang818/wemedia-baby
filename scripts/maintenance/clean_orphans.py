import sys
import os
import asyncio

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.infrastructure.common.path_manager import PathManager
from src.infrastructure.storage.tortoise_manager import init_tortoise
from src.infrastructure.storage.orm_models.random_copywriting import (
    RandomCopywritingItem,
    RandomCopywritingCategory,
)
from tortoise import Tortoise


async def clean_orphans():
    try:
        print("正在连接数据库...")
        db_path = str(PathManager.get_db_path())
        await init_tortoise(db_path)

        # 获取所有现存的分类 ID
        cat_ids = await RandomCopywritingCategory.all().values_list("id", flat=True)

        # 查找 category_id 不在现有分类中的记录
        orphan_query = RandomCopywritingItem.filter(category_id__not_in=cat_ids)
        count = await orphan_query.count()

        if count > 0:
            print(f"发现 {count} 条孤儿文案记录，正在删除...")
            await orphan_query.delete()
            print("删除完成！")
        else:
            print("太棒了，没有发现幽灵孤儿文案！")

    except Exception as e:
        print(f"清理失败: {e}")
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(clean_orphans())


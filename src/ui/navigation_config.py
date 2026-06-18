from typing import List, Dict, Any, Optional
from qfluentwidgets import FluentIcon, NavigationItemPosition

class NavigationConfig:
    """导航栏配置管理"""
    
    @staticmethod
    def get_items(
        batch_feature: bool = False,
        data_center: bool = False,
        interaction: bool = False,
        subscription: bool = False,
        material_library: bool = False,
        commerce_promotion: bool = False,
    ) -> List[Dict[str, Any]]:
        """获取导航菜单配置"""
        
        items = [
            # 1. 工作台
            {
                "route_key": "workspace_page",
                "icon": FluentIcon.HOME,
                "text": "工作台",
                "position": NavigationItemPosition.TOP,
                "selectable": True
            },
            
            # 2. 账号库 (父级)
            {
                "route_key": "account_container",
                "icon": FluentIcon.PEOPLE,
                "text": "账号库",
                "selectable": False,
                "expanded": False, # [Fix] 禁用默认展开以防止UI初始化时的布局重叠问题
                "children": [
                    {
                        "route_key": "account_page",
                        "icon": FluentIcon.PEOPLE,
                        "text": "账号管理",
                    },
                    {
                        "route_key": "account_group_page",
                        "icon": FluentIcon.FOLDER,
                        "text": "账号组管理",
                    },
                    {
                        "route_key": "account_tag_page",
                        "icon": FluentIcon.TAG,
                        "text": "账号标签",
                    }
                ]
            },
            
            # 3. 发布管理 (父级)
            {
                "route_key": "publish_container",
                "icon": FluentIcon.SEND,
                "text": "发布管理",
                "selectable": True, # [Fix] 设置为True以确保显示，点击逻辑由手风琴处理覆盖
                "children": [
                    {
                        "route_key": "publish_list_page",
                        "icon": FluentIcon.VIEW,
                        "text": "待发布",
                    },
                    {
                        "route_key": "publish_records_page",
                        "icon": FluentIcon.HISTORY,
                        "text": "已发布",
                    },
                    {
                        "route_key": "publish_recycle_bin_page",
                        "icon": FluentIcon.DELETE,
                        "text": "任务回收站",
                    },
                ]
            },
            
            # 4. 视频任务创建（写入发布列表，非立即上传）
            {
                "route_key": "video_publish_container",
                "icon": FluentIcon.VIDEO,
                "text": "视频任务",
                "selectable": False,
                "children": [
                    {
                        "route_key": "single_task_creation_page",
                        "icon": FluentIcon.MOVIE,
                        "text": "单视频任务",
                    }
                ]
            },
            
            # 5. 图文任务创建（写入发布列表，非立即上传）
            {
                "route_key": "image_publish_container",
                "icon": FluentIcon.PHOTO,
                "text": "图文任务",
                "selectable": False,
                "children": [
                    {
                        "route_key": "image_single_task_creation_page",
                        "icon": FluentIcon.EDIT,
                        "text": "单图文任务",
                    }
                ]
            },

        ]

        # 6. 媒体库 (Pro/闭源)
        if material_library:
            items.append(
                {
                    "route_key": "material_library_container",
                    "icon": FluentIcon.LIBRARY,
                    "text": "媒体库",
                    "selectable": False,
                    "children": [
                        {"route_key": "video_library_page", "icon": FluentIcon.VIDEO, "text": "视频库"},
                        {"route_key": "image_library_page", "icon": FluentIcon.PHOTO, "text": "图片库"},
                        {"route_key": "copywriting_library_page", "icon": FluentIcon.EDIT, "text": "标准文案库"},
                        {"route_key": "random_copywriting_page", "icon": FluentIcon.TILES, "text": "随机文案库"},
                    ],
                }
            )

        # 7. 带货推广 (Pro/闭源)
        if commerce_promotion:
            items.append(
                {
                    "route_key": "commerce_promotion_container",
                    "icon": FluentIcon.SHOPPING_CART,
                    "text": "带货推广",
                    "selectable": False,
                    "children": [
                        {"route_key": "cart_promotion_page", "icon": FluentIcon.SHOPPING_CART, "text": "购物车推广"},
                        {"route_key": "location_promotion_page", "icon": FluentIcon.PIN, "text": "位置推广"},
                        {"route_key": "group_buy_promotion_page", "icon": FluentIcon.TAG, "text": "团购推广"},
                    ],
                }
            )

        # 动态注入 - 批量视频
        if batch_feature:
            NavigationConfig._append_child(items, "video_publish_container", {
                "route_key": "batch_task_creation_page",
                "icon": FluentIcon.LIBRARY,
                "text": "批量视频任务",
            })

        # 动态注入 - 批量图文
        if batch_feature:
            NavigationConfig._append_child(items, "image_publish_container", {
                "route_key": "image_batch_task_creation_page",
                "icon": FluentIcon.TILES,
                "text": "批量图文任务",
            })

        # 7. 数据中心 (Pro)
        if data_center:
            items.append({
                "route_key": "data_center_page",
                "icon": FluentIcon.PIE_SINGLE,
                "text": "数据中心",
                "selectable": True
            })

        # 8. 评论及私信 (Pro)
        if interaction:
            interaction_group = {
                "route_key": "interaction_container",
                "icon": FluentIcon.CHAT,
                "text": "评论及私信",
                "selectable": False,
                "children": [
                    {
                        "route_key": "comment_page",
                        "icon": FluentIcon.PEOPLE,
                        "text": "评论管理",
                    },
                    {
                        "route_key": "private_message_page",
                        "icon": FluentIcon.MESSAGE,
                        "text": "私信管理",
                    }
                ]
            }
            items.append(interaction_group)

        # 底部菜单
        # 个人中心
        if subscription:
            items.append({
                "route_key": "personal_center_page",
                "icon": FluentIcon.CERTIFICATE,
                "text": "个人中心",
                "position": NavigationItemPosition.BOTTOM,
                "selectable": True
            })

        # 使用手册
        items.append({
            "route_key": "user_manual_action",
            "icon": FluentIcon.HELP,
            "text": "使用手册",
            "position": NavigationItemPosition.BOTTOM,
            "selectable": False
        })

        # 设置
        items.append({
            "route_key": "settings_page",
            "icon": FluentIcon.SETTING,
            "text": "设置",
            "position": NavigationItemPosition.BOTTOM,
            "selectable": True
        })

        return items

    @staticmethod
    def _append_child(items: List[Dict], parent_key: str, child: Dict):
        """辅助方法：向指定父级添加子项"""
        for item in items:
            if item.get("route_key") == parent_key:
                if "children" not in item:
                    item["children"] = []
                item["children"].append(child)
                return

    @staticmethod
    def get_accordion_mapping() -> Dict[str, str]:
        """获取手风琴父子映射 (Parent Key -> First Child Key)"""
        return {
            "account_container": "account_page",
            "publish_container": "publish_list_page",
            "video_publish_container": "single_task_creation_page",
            "image_publish_container": "image_single_task_creation_page",
            "interaction_container": "comment_page",
            "material_library_container": "video_library_page",
            "commerce_promotion_container": "cart_promotion_page",
        }
    
    @staticmethod
    def get_child_to_parent_mapping() -> Dict[str, str]:
        """获取子页面到父级的映射 (用于跳转时自动展开)"""
        return {
            # 发布管理
            "publish_list_page": "publish_container",
            "publish_records_page": "publish_container",
            "publish_recycle_bin_page": "publish_container",
            # 视频
            "single_task_creation_page": "video_publish_container",
            "batch_task_creation_page": "video_publish_container",
            # 图文
            "image_single_task_creation_page": "image_publish_container",
            "image_batch_task_creation_page": "image_publish_container",
            # 互动
            "comment_page": "interaction_container",
            "private_message_page": "interaction_container",
            # 账号库
            "account_page": "account_container",
            "account_group_page": "account_container",
            "account_tag_page": "account_container",
            # 媒体库
            "video_library_page": "material_library_container",
            "image_library_page": "material_library_container",
            "copywriting_library_page": "material_library_container",
            "random_copywriting_page": "material_library_container",
            # 带货推广是顶层一级菜单，两个子页归属于它
            "cart_promotion_page": "commerce_promotion_container",
            "location_promotion_page": "commerce_promotion_container",
            "group_buy_promotion_page": "commerce_promotion_container",
        }

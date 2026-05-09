"""
CurrentUserService 线程安全单元测试
覆盖：并发读写不会读到半更新状态
"""
import threading
import pytest


@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试前重置单例。"""
    from src.proprietary.auth.current_user_service import CurrentUserService
    CurrentUserService._instance = None
    yield
    CurrentUserService._instance = None


class TestCurrentUserServiceThreadSafety:
    """线程安全测试"""

    def test_singleton_returns_same_instance(self):
        from src.proprietary.auth.current_user_service import CurrentUserService
        a = CurrentUserService()
        b = CurrentUserService()
        assert a is b

    def test_concurrent_singleton_creation(self):
        """多线程并发创建单例应返回同一实例。"""
        from src.proprietary.auth.current_user_service import CurrentUserService
        instances = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            instances.append(id(CurrentUserService()))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(set(instances)) == 1

    def test_set_and_get_user_thread_safe(self):
        """并发写入和读取不应抛异常或返回不一致数据。"""
        from src.proprietary.auth.current_user_service import CurrentUserService
        svc = CurrentUserService()
        errors = []

        def writer():
            for i in range(100):
                try:
                    svc.set_user(user_id=i, username=f"user_{i}", level="vip0")
                except Exception as e:
                    errors.append(e)

        def reader():
            for _ in range(100):
                try:
                    user = svc.get_user()
                    if user is not None:
                        assert "id" in user
                        assert "username" in user
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"并发读写出错: {errors}"

    def test_clear_user(self):
        from src.proprietary.auth.current_user_service import CurrentUserService
        svc = CurrentUserService()
        svc.set_user(user_id=1, username="test")
        assert svc.is_logged_in() is True
        svc.clear_user()
        assert svc.is_logged_in() is False
        assert svc.get_user() is None

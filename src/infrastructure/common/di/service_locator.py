"""
服务定位器模块（优化版）
文件路径：src/core/common/di/service_locator.py
功能：统一管理服务实例，提供依赖注入，支持多种作用域
"""

from typing import Any, Dict, Type, Optional, Callable, List, get_type_hints, get_origin, get_args
import inspect
import logging
import threading

from .scopes import Scope

logger = logging.getLogger(__name__)


class ServiceNotFoundError(Exception):
    """服务未找到异常"""
    pass


class ServiceFactory:
    """服务工厂 - 用于延迟创建服务实例"""
    
    def __init__(self, factory_func: Callable[[], Any], scope: Scope = Scope.SINGLETON):
        """初始化服务工厂
        
        Args:
            factory_func: 工厂函数，无参数，返回服务实例
            scope: 服务作用域
        """
        self.factory_func = factory_func
        self.scope = scope
        self._instance: Optional[Any] = None
    
    def create(self) -> Any:
        """创建服务实例
        
        Returns:
            服务实例，根据作用域返回单例或新实例
        """
        if self.scope == Scope.SINGLETON:
            if self._instance is not None:
                return self._instance
            instance = self.factory_func()
            self._instance = instance
            return instance
        elif self.scope == Scope.PROTOTYPE:
            return self.factory_func()
        else:  # REQUEST scope (可模拟为PROTOTYPE)
            return self.factory_func()


class ServiceLocator:
    """服务定位器 - 统一管理服务实例，支持多种作用域和自动依赖解析"""
    
    _instance: Optional['ServiceLocator'] = None
    _lock = threading.RLock()
    _services: Dict[Type, Any] = {}
    _factories: Dict[Type, ServiceFactory] = {}
    _aliases: Dict[str, Type] = {}
    _initializers: Dict[Type, List[Callable[[Any], None]]] = {}
    _lifecycle_hooks: Dict[Type, Dict[str, Callable]] = {}
    _request_context: Dict[Type, Any] = {}
    
    def __new__(cls) -> 'ServiceLocator':
        """单例模式实现"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def register(
        self, 
        service_type: Type, 
        instance: Any, 
        scope: Scope = Scope.SINGLETON
    ) -> None:
        """注册服务实例
        
        Args:
            service_type: 服务类型（类）
            instance: 服务实例
            scope: 服务作用域（默认SINGLETON）
        
        Raises:
            ValueError: 服务实例类型不匹配
        """
        if not isinstance(instance, service_type):
            raise ValueError(
                f"服务实例类型不匹配: 期望 {service_type}, 实际 {type(instance)}"
            )
        
        with self._lock:
            if scope == Scope.SINGLETON:
                self._services[service_type] = instance
                self._run_initializers(service_type, instance)
                logger.debug(f"注册服务: {service_type.__name__} (SINGLETON)")
            else:
                factory = ServiceFactory(lambda: instance, scope)
                self._factories[service_type] = factory
                logger.debug(f"注册服务: {service_type.__name__} ({scope.value})")
    
    def register_factory(
        self,
        service_type: Type,
        factory_func: Callable[[], Any],
        scope: Scope = Scope.SINGLETON
    ) -> None:
        """注册服务工厂
        
        Args:
            service_type: 服务类型
            factory_func: 工厂函数，无参数，返回服务实例
            scope: 服务作用域（默认SINGLETON）
        """
        with self._lock:
            factory = ServiceFactory(factory_func, scope)
            self._factories[service_type] = factory
            logger.debug(f"注册服务工厂: {service_type.__name__} ({scope.value})")
    
    def register_class(
        self,
        service_type: Type,
        implementation: Type,
        scope: Scope = Scope.SINGLETON
    ) -> None:
        """注册服务类（自动解析构造函数依赖）
        
        Args:
            service_type: 服务接口类型
            implementation: 实现类
            scope: 服务作用域（默认SINGLETON）
        """
        def factory() -> Any:
            """工厂函数，自动解析依赖"""
            return self._create_instance(implementation)
        
        self.register_factory(service_type, factory, scope)
    
    def _create_instance(self, cls: Type) -> Any:
        """创建实例，自动解析构造函数依赖
        
        Args:
            cls: 要实例化的类
            
        Returns:
            实例化的对象
        """
        # 获取构造函数签名
        sig = inspect.signature(cls.__init__)
        params = {}
        
        # 解析参数
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            
            # 获取参数类型注解
            param_type = param.annotation
            
            # 如果类型注解是inspect.Parameter.empty，跳过
            if param_type == inspect.Parameter.empty:
                # 尝试从类型提示获取
                hints = get_type_hints(cls.__init__)
                param_type = hints.get(param_name)
            
            if param_type is None or param_type == inspect.Parameter.empty:
                # 如果没有类型注解，使用默认值
                if param.default != inspect.Parameter.empty:
                    params[param_name] = param.default
                else:
                    raise ValueError(
                        f"无法解析依赖: {cls.__name__}.__init__ 的参数 {param_name} 缺少类型注解"
                    )
            else:
                # 处理泛型类型（如 Optional[Type], List[Type]）
                origin = get_origin(param_type)
                if origin is not None:
                    # 对于 Optional[Type]，提取实际类型
                    args = get_args(param_type)
                    if args:
                        param_type = args[0]
                
                # 从服务定位器获取依赖
                try:
                    params[param_name] = self.get(param_type)
                except ServiceNotFoundError:
                    # 如果依赖未注册，使用默认值
                    if param.default != inspect.Parameter.empty:
                        params[param_name] = param.default
                    else:
                        raise ValueError(
                            f"无法解析依赖: {cls.__name__}.__init__ 的参数 {param_name} "
                            f"类型 {param_type} 未注册"
                        )
        
        return cls(**params)
    
    def register_alias(self, alias: str, service_type: Type) -> None:
        """注册服务别名
        
        Args:
            alias: 别名
            service_type: 服务类型
        """
        self._aliases[alias] = service_type
        logger.debug(f"注册服务别名: {alias} -> {service_type.__name__}")
    
    def add_initializer(self, service_type: Type, initializer: Callable[[Any], None]) -> None:
        """添加服务初始化回调
        
        Args:
            service_type: 服务类型
            initializer: 初始化函数 (instance) -> None
        """
        if service_type not in self._initializers:
            self._initializers[service_type] = []
        self._initializers[service_type].append(initializer)
        logger.debug(f"添加初始化回调: {service_type.__name__}")
    
    def _run_initializers(self, service_type: Type, instance: Any) -> None:
        """执行初始化回调"""
        if service_type in self._initializers:
            for initializer in self._initializers[service_type]:
                try:
                    initializer(instance)
                except Exception as e:
                    logger.error(f"执行初始化回调失败 {service_type.__name__}: {e}", exc_info=True)
    
    def get(self, service_type: Type) -> Any:
        """获取服务实例
        
        Args:
            service_type: 服务类型
            
        Returns:
            服务实例，根据作用域返回单例或新实例
            
        Raises:
            ServiceNotFoundError: 服务未注册
        """
        with self._lock:
            if isinstance(service_type, str):
                if service_type in self._aliases:
                    service_type = self._aliases[service_type]
                else:
                    raise ServiceNotFoundError(f"服务别名未找到: {service_type}")
            
            if service_type in self._services:
                return self._services[service_type]
            
            if service_type in self._factories:
                factory = self._factories[service_type]
                
                if factory.scope == Scope.REQUEST:
                    if service_type not in self._request_context:
                        instance = factory.create()
                        self._request_context[service_type] = instance
                        self._run_initializers(service_type, instance)
                    return self._request_context[service_type]
                else:
                    instance = factory.create()
                    
                    if factory.scope == Scope.SINGLETON:
                        self._services[service_type] = instance
                        self._run_initializers(service_type, instance)
                    elif factory.scope == Scope.PROTOTYPE:
                        self._run_initializers(service_type, instance)
                    
                    return instance
            
            raise ServiceNotFoundError(f"服务未注册: {service_type.__name__}")
    
    def get_optional(self, service_type: Type) -> Optional[Any]:
        """获取服务（可选，不存在返回None）
        
        Args:
            service_type: 服务类型
        
        Returns:
            服务实例，不存在返回None
        """
        try:
            return self.get(service_type)
        except ServiceNotFoundError:
            return None
    
    def clear_request_context(self) -> None:
        """清空请求上下文（用于REQUEST作用域）"""
        self._request_context.clear()
        logger.debug("清空请求上下文")
    
    def unregister(self, service_type: Type) -> None:
        """注销服务
        
        Args:
            service_type: 服务类型
        """
        with self._lock:
            if service_type in self._services:
                if service_type in self._lifecycle_hooks:
                    hooks = self._lifecycle_hooks[service_type]
                    if 'cleanup' in hooks:
                        try:
                            hooks['cleanup'](self._services[service_type])
                        except Exception as e:
                            logger.error(f"执行清理钩子失败 {service_type.__name__}: {e}", exc_info=True)
                
                del self._services[service_type]
                logger.debug(f"注销服务: {service_type.__name__}")
            
            if service_type in self._factories:
                del self._factories[service_type]
                logger.debug(f"注销服务工厂: {service_type.__name__}")
    
    def is_registered(self, service_type: Type) -> bool:
        """检查服务是否已注册
        
        Args:
            service_type: 服务类型
        
        Returns:
            如果已注册返回True，否则返回False
        """
        return (service_type in self._services or 
                service_type in self._factories or
                (isinstance(service_type, str) and service_type in self._aliases))
    
    def get_all_services(self) -> Dict[Type, Any]:
        """获取所有已注册的服务实例
        
        Returns:
            服务字典
        """
        return self._services.copy()
    
    def clear(self) -> None:
        """清空所有服务"""
        with self._lock:
            for service_type, instance in self._services.items():
                if service_type in self._lifecycle_hooks:
                    hooks = self._lifecycle_hooks[service_type]
                    if 'cleanup' in hooks:
                        try:
                            hooks['cleanup'](instance)
                        except Exception as e:
                            logger.error(f"执行清理钩子失败 {service_type.__name__}: {e}", exc_info=True)
            
            self._services.clear()
            self._factories.clear()
            self._aliases.clear()
            self._initializers.clear()
            self._lifecycle_hooks.clear()
            self._request_context.clear()
            logger.debug("清空所有服务")


# 全局服务定位器实例（单例）
def get_service_locator() -> ServiceLocator:
    """获取全局服务定位器实例
    
    Returns:
        服务定位器实例
    """
    return ServiceLocator()


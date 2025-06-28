# Developer Guide: Working with Dependency Injection

## Quick Start

### Adding a New Service

1. **Define the Interface** (`app/core/di/interfaces.py`):
```python
class IMyNewService(Protocol):
    """Interface for my new service"""
    async def do_something(self, param: str) -> str:
        """Service method"""
        ...
```

2. **Implement the Service** (`app/core/services/my_new_service.py`):
```python
from ..di.interfaces import IMyNewService, ILogger

class MyNewService(IMyNewService):
    def __init__(self, logger: ILogger):
        self.logger = logger
    
    async def do_something(self, param: str) -> str:
        self.logger.info(f"Doing something with {param}")
        return f"Result: {param}"
```

3. **Register in Composition Root** (`app/api/composition_root.py`):
```python
# In configure_services():
async def create_my_service():
    logger = await container.resolve(ILogger)
    return MyNewService(logger)

container.register_singleton(IMyNewService, create_my_service)
```

4. **Use in Other Components**:
```python
class SomeOtherService:
    def __init__(self, my_service: IMyNewService):
        self.my_service = my_service
    
    async def use_it(self):
        result = await self.my_service.do_something("test")
```

### Writing Tests

1. **Create a Mock in conftest.py**:
```python
# In test_container fixture:
mock_my_service = AsyncMock(spec=IMyNewService)
mock_my_service.do_something.return_value = "Mocked result"
container.register_singleton(IMyNewService, lambda: mock_my_service)
```

2. **Write Your Test**:
```python
@pytest.mark.asyncio
async def test_my_feature(test_container):
    # Get the mock
    mock_service = await test_container.resolve(IMyNewService)
    
    # Test your component that uses the service
    component = MyComponent(mock_service)
    result = await component.do_work()
    
    # Verify
    mock_service.do_something.assert_awaited_once_with("expected_param")
```

## Common Patterns

### 1. Factory Pattern with DI

When you need to create objects dynamically:

```python
class IWidgetFactory(Protocol):
    def create_widget(self, widget_type: str) -> IWidget:
        ...

class WidgetFactory(IWidgetFactory):
    def __init__(self, logger: ILogger):
        self.logger = logger
        self.widget_types = {}
    
    def register_type(self, name: str, widget_class: Type[IWidget]):
        self.widget_types[name] = widget_class
    
    def create_widget(self, widget_type: str) -> IWidget:
        if widget_type not in self.widget_types:
            raise ValueError(f"Unknown widget type: {widget_type}")
        return self.widget_types[widget_type]()
```

### 2. Optional Dependencies

For services that might not always be available:

```python
class ServiceWithOptionalDeps:
    def __init__(self, 
                 required_service: IRequiredService,
                 optional_service: Optional[IOptionalService] = None):
        self.required = required_service
        self.optional = optional_service
    
    async def do_work(self):
        result = await self.required.process()
        
        if self.optional:
            # Use optional service if available
            await self.optional.enhance(result)
        
        return result
```

### 3. Configuration Injection

Injecting configuration alongside services:

```python
@dataclass
class ServiceConfig:
    timeout: int = 30
    retries: int = 3

class ConfiguredService:
    def __init__(self, 
                 http_client: IHTTPClient,
                 config: ServiceConfig):
        self.client = http_client
        self.config = config
```

## Debugging DI Issues

### Common Problems and Solutions

1. **Circular Dependencies**
   ```python
   # BAD: A depends on B, B depends on A
   
   # GOOD: Extract common interface or use events
   class IEventBus(Protocol): ...
   
   class ServiceA:
       def __init__(self, event_bus: IEventBus): ...
   
   class ServiceB:
       def __init__(self, event_bus: IEventBus): ...
   ```

2. **Missing Registration**
   ```python
   # Error: No service registered for type 'IMyService'
   
   # Fix: Add to composition root
   container.register_singleton(IMyService, create_my_service)
   ```

3. **Async Initialization Issues**
   ```python
   # BAD: Trying to await in __init__
   class BadService:
       def __init__(self):
           self.data = await load_data()  # SyntaxError!
   
   # GOOD: Separate initialization
   class GoodService:
       def __init__(self):
           self.data = None
       
       async def initialize(self):
           self.data = await load_data()
   ```

### Debug Helper

Add this to see what's registered:

```python
def debug_container(container: ServiceContainer):
    print("Registered Services:")
    for service_type, info in container._services.items():
        print(f"  - {service_type}: {info['lifetime']}")
```

## Best Practices Checklist

✅ **DO:**
- Define interfaces for all services
- Use constructor injection exclusively
- Keep services focused on a single responsibility
- Make dependencies explicit
- Use async/await consistently
- Write tests with mocked dependencies

❌ **DON'T:**
- Create dependencies inside constructors
- Use global variables or singletons
- Pass the container around (Service Locator anti-pattern)
- Mix business logic with dependency creation
- Forget to dispose of resources

## Advanced Topics

### Custom Lifetimes

Create custom lifetime managers:

```python
class RequestScopedLifetime:
    """One instance per HTTP request"""
    def __init__(self):
        self.instances = {}
    
    def get_instance(self, request_id: str, factory: Callable):
        if request_id not in self.instances:
            self.instances[request_id] = factory()
        return self.instances[request_id]
```

### Decorator-based Registration

For a more declarative approach:

```python
@injectable(IMyService, lifetime="singleton")
class MyService:
    def __init__(self, logger: ILogger):
        self.logger = logger
```

### Performance Considerations

1. **Lazy Loading:** Services are created only when first requested
2. **Singleton Caching:** Singletons are created once and reused
3. **Async Resolution:** Supports async factory functions
4. **Minimal Overhead:** Direct dictionary lookups for resolution

## Resources

- [Python Dependency Injection Libraries](https://github.com/ets-labs/python-dependency-injector)
- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
- [Martin Fowler on DI](https://martinfowler.com/articles/injection.html)
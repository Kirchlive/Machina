# Visual Guide: LLM2LLM-Bridge DI Architecture

## Component Dependency Graph

```mermaid
graph TB
    subgraph "API Layer"
        API[FastAPI App]
        EP1[/v1/bridge]
        EP2[/v1/mission/execute]
        EP3[/v1/models]
    end
    
    subgraph "Core Services"
        Bridge[LLMBridgeCore]
        Router[Router]
        Orch[AgentOrchestrator]
    end
    
    subgraph "Infrastructure Services"
        Config[ConfigurationProvider]
        EventStore[EventStore]
        Telemetry[TelemetryService]
        Logger[LoggerService]
        Redis[RedisProvider]
        HTTP[HTTPClientProvider]
    end
    
    subgraph "Factories"
        AdapterFactory[AdapterFactory]
        CBFactory[CircuitBreakerFactory]
    end
    
    subgraph "Adapters"
        OpenAI[OpenAIAdapter]
        Claude[ClaudeAdapter]
        Gemini[GeminiAdapter]
        OR[OpenRouterAdapter]
    end
    
    API --> Bridge
    API --> Orch
    
    EP1 --> Bridge
    EP2 --> Orch
    EP3 --> Bridge
    
    Bridge --> Router
    Bridge --> Config
    Bridge --> EventStore
    Bridge --> Telemetry
    
    Router --> EventStore
    Router --> Telemetry
    Router --> Redis
    
    Orch --> Bridge
    Orch --> EventStore
    Orch --> Telemetry
    
    AdapterFactory --> HTTP
    AdapterFactory --> Config
    
    AdapterFactory -.-> OpenAI
    AdapterFactory -.-> Claude
    AdapterFactory -.-> Gemini
    AdapterFactory -.-> OR
    
    Router --> AdapterFactory
    Router --> CBFactory
    
    style API fill:#f9f,stroke:#333,stroke-width:2px
    style Bridge fill:#bbf,stroke:#333,stroke-width:2px
    style Router fill:#bbf,stroke:#333,stroke-width:2px
```

## Service Lifetime Flow

```mermaid
sequenceDiagram
    participant App as Application Start
    participant CR as Composition Root
    participant SC as Service Container
    participant S1 as ConfigService (Singleton)
    participant S2 as Router (Singleton)
    participant S3 as Adapter (Transient)
    
    App->>CR: initialize_application()
    CR->>SC: Create Container
    
    Note over CR: Register all services
    CR->>SC: register_singleton(IConfig, ...)
    CR->>SC: register_singleton(IRouter, ...)
    CR->>SC: register_transient(IAdapter, ...)
    
    App->>SC: resolve(IRouter)
    SC->>SC: Check if singleton exists
    SC->>S1: Create ConfigService (first time)
    SC->>S2: Create Router with Config
    SC-->>App: Return Router instance
    
    Note over App: Later request...
    App->>SC: resolve(IRouter)
    SC-->>App: Return same Router instance
    
    App->>SC: resolve(IAdapter)
    SC->>S3: Create new Adapter
    SC-->>App: Return new Adapter instance
```

## Testing Architecture

```mermaid
graph LR
    subgraph "Production"
        ProdContainer[Production Container]
        RealDB[(Redis)]
        RealHTTP[HTTP Client]
        RealServices[Real Services]
        
        ProdContainer --> RealServices
        RealServices --> RealDB
        RealServices --> RealHTTP
    end
    
    subgraph "Testing"
        TestContainer[Test Container]
        MockDB[Mock Redis]
        MockHTTP[Mock HTTP]
        MockServices[Mock Services]
        
        TestContainer --> MockServices
        MockServices --> MockDB
        MockServices --> MockHTTP
    end
    
    subgraph "Test Execution"
        Test[pytest test_case]
        Fixture[test_container fixture]
        
        Test --> Fixture
        Fixture --> TestContainer
    end
    
    style TestContainer fill:#9f9,stroke:#333,stroke-width:2px
    style ProdContainer fill:#f99,stroke:#333,stroke-width:2px
```

## Request Flow Through DI Components

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI Endpoint
    participant Container as DI Container
    participant Bridge as LLMBridgeCore
    participant Router
    participant CB as Circuit Breaker
    participant Adapter as LLM Adapter
    participant Event as Event Store
    participant Tel as Telemetry
    
    Client->>API: POST /v1/bridge
    API->>Container: Get Bridge from app.state
    Container-->>API: Bridge instance
    
    API->>Bridge: bridge_message()
    
    Bridge->>Tel: trace_start()
    Bridge->>Event: log_event("bridge_request")
    
    Bridge->>Router: route_message()
    
    Router->>Event: log_event("routing_start")
    Router->>CB: execute(adapter.send)
    
    CB->>Adapter: send(prompt)
    Adapter-->>CB: response
    CB-->>Router: response
    
    Router->>Event: log_event("routing_success")
    Router-->>Bridge: response
    
    Bridge->>Tel: trace_end()
    Bridge->>Event: log_event("bridge_success")
    
    Bridge-->>API: response
    API-->>Client: JSON response
```

## Error Handling Flow

```mermaid
graph TD
    A[Client Request] --> B{API Endpoint}
    B --> C[Try: Process Request]
    
    C --> D{Service Call}
    D -->|Success| E[Return Response]
    D -->|Error| F[Catch Exception]
    
    F --> G[Log to Event Store]
    F --> H[Update Telemetry]
    F --> I[Circuit Breaker Check]
    
    I -->|Open CB| J[Return 503 Service Unavailable]
    I -->|Closed CB| K[Return 500 Internal Error]
    
    G --> L[Error Details Logged]
    H --> M[Metrics Updated]
    
    style F fill:#f99,stroke:#333,stroke-width:2px
    style J fill:#f99,stroke:#333,stroke-width:2px
    style K fill:#f99,stroke:#333,stroke-width:2px
```

## Plugin Architecture Integration

```mermaid
graph TD
    subgraph "Plugin System"
        PD[Plugin Directory]
        BP[Base Plugin]
        
        P1[OpenAI Plugin]
        P2[Claude Plugin]
        P3[Gemini Plugin]
        P4[Custom Plugin]
        
        PD --> P1
        PD --> P2
        PD --> P3
        PD --> P4
        
        P1 -.-> BP
        P2 -.-> BP
        P3 -.-> BP
        P4 -.-> BP
    end
    
    subgraph "DI Integration"
        AF[AdapterFactory]
        Registry[Plugin Registry]
        
        AF --> Registry
        Registry --> PD
    end
    
    subgraph "Runtime"
        Router --> AF
        AF --> |"create_adapter('gpt-4')"| P1
        AF --> |"create_adapter('claude')"| P2
    end
    
    style PD fill:#9f9,stroke:#333,stroke-width:2px
    style AF fill:#bbf,stroke:#333,stroke-width:2px
```

## Key Benefits Visualized

```mermaid
mindmap
  root((DI Architecture))
    Testability
      Mock any dependency
      Isolated unit tests
      Fast test execution
      No external dependencies
    Flexibility
      Swap implementations
      Runtime configuration
      Plugin support
      Feature toggles
    Maintainability
      Clear contracts
      Single responsibility
      Explicit dependencies
      Easy debugging
    Scalability
      Async support
      Connection pooling
      Resource management
      Performance optimization
```

This visual guide helps developers quickly understand the DI architecture and how components interact within the LLM2LLM-Bridge system.
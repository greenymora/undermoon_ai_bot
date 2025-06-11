# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **ChatGPT-on-WeChat** (chatgpt-on-wechat) bot project that enables AI conversational capabilities across multiple messaging platforms. The project supports various AI models (GPT, Claude, Wenxin, Xunfei, etc.) and can be deployed on WeChat, WeCom, DingTalk, Feishu, and other platforms.

## Common Development Commands

### Running the Application

```bash
# Basic startup
python3 app.py

# Using the convenience scripts (recommended)
./run.sh start      # Start the application
./run.sh stop       # Stop the application  
./run.sh restart    # Restart the application
./run.sh update     # Update from git and restart

# Background execution
nohup python3 app.py & tail -f nohup.out
```

### Testing

```bash
# Test privacy API
python3 test_privacy_api.py

# Test MySQL connection
python3 test_mysql.py

# Test database setup
python3 scripts/test_db_only.py
```

### Code Quality

```bash
# Linting (configured in .flake8)
flake8

# Code formatting (configured in pyproject.toml)
black . --line-length 176
isort . --profile black
```

### Dependencies

```bash
# Install core dependencies
pip3 install -r requirements.txt

# Install optional dependencies  
pip3 install -r requirements-optional.txt

# Using Chinese mirror (for faster installation in China)
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## High-Level Architecture

### Core Components

1. **Bot Layer** (`bot/`)
   - Factory pattern for creating different AI bot implementations
   - Supports multiple AI providers: OpenAI, Claude, Baidu Wenxin, Xunfei, etc.
   - Each bot type has its own implementation and session management

2. **Channel Layer** (`channel/`)
   - Abstraction for different messaging platforms
   - Implementations for WeChat, WeCom, DingTalk, Feishu, Terminal, Web
   - Message handling and routing logic

3. **Bridge Layer** (`bridge/`)
   - Connects channels to bots
   - Manages context and reply formatting
   - Handles voice and translation services

4. **Plugin System** (`plugins/`)
   - Dynamic plugin loading and management
   - Event-driven architecture for extending functionality
   - Plugins can intercept and modify messages at various stages

5. **Configuration** (`config.py`, `config.json`)
   - Centralized configuration management
   - Support for multiple AI models and API keys
   - Channel-specific settings

### Key Design Patterns

- **Factory Pattern**: Used extensively for creating bots, channels, voices, and translators
- **Singleton Pattern**: Applied to managers like PluginManager, Bridge
- **Event-Driven**: Plugin system uses events for extensibility
- **Session Management**: Maintains conversation context per user/group

### Data Flow

1. Message received by Channel → 
2. Channel creates Context → 
3. Bridge processes Context → 
4. Bot generates Reply → 
5. Channel sends Reply back

### Database Integration

- MySQL support for user management and privacy consent tracking
- Redis support (in `db/redis/`)
- Privacy API server (`privacy_api_server.py`) for GDPR compliance

### Important Considerations

- The project uses modified itchat library (`lib/itchat/`) for WeChat integration
- Privacy consent system is implemented for compliance
- Supports both synchronous and asynchronous message handling
- Plugin system allows for custom business logic without modifying core code
- Multiple deployment options: local, Docker, Railway

### Security Notes

- API keys and sensitive data should be in `config.json` (not tracked by git)
- Privacy consent tracking for user data handling
- Support for proxy configuration for API access
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Repository documentation (LICENSE, CONTRIBUTING.md, CHANGELOG.md, ARCHITECTURE.md)

## [0.2.0] - 2024-10-27

### Added
- Modular architecture with separate files for API clients, personas, and utilities
- Command-line interface (CLI) support via `cli_chat.py`
- Analytics module for conversation summarization
- Configuration utilities with JSONC support

### Changed
- Refactored codebase into modules for better maintainability
- Improved code organization and structure

## [0.1.0] - Initial Release

### Added
- GUI application for AI-to-AI conversations using Tkinter
- Support for multiple LLM providers:
  - Ollama
  - LM Studio
  - OpenRouter
  - OpenAI
- Persona management system
- Conversation logging and export
- Narrator mode for system messages
- Topic control for guided conversations
- Modern UI with ttkbootstrap styling
- Persona generator tool
- Configuration management
- Example configuration files

### Features
- Dual AI persona conversations
- Turn-based chat system
- Real-time conversation display
- Pause/Resume functionality
- Conversation history saving
- Persistent API configuration

---

## Version History Notes

### Versioning Scheme
- **Major.Minor.Patch** (e.g., 1.0.0)
- **Major**: Breaking changes or major new features
- **Minor**: New features, backwards compatible
- **Patch**: Bug fixes and minor improvements

### Categories
- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security improvements

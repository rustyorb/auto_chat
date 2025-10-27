# Contributing to Auto Chat

Thank you for your interest in contributing to Auto Chat! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)

## Code of Conduct

This project adheres to a code of conduct that all contributors are expected to follow. Please be respectful and constructive in all interactions.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/auto_chat.git
   cd auto_chat
   ```
3. Add the upstream repository:
   ```bash
   git remote add upstream https://github.com/rustyorb/auto_chat.git
   ```

## Development Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up configuration files:
   ```bash
   cp config.json.example config.json
   cp personas.json.example personas.json
   ```

4. Create a `.env` file for API keys if needed:
   ```bash
   # Example .env
   OPENAI_API_KEY=your_key_here
   OPENROUTER_API_KEY=your_key_here
   ```

## How to Contribute

### Reporting Bugs

- Check if the bug has already been reported in [Issues](https://github.com/rustyorb/auto_chat/issues)
- If not, create a new issue with:
  - Clear, descriptive title
  - Steps to reproduce
  - Expected vs actual behavior
  - Your environment (OS, Python version, etc.)
  - Relevant logs or screenshots

### Suggesting Enhancements

- Open an issue with the `enhancement` label
- Describe the feature and its benefits
- Explain how it would work
- Provide examples if applicable

### Code Contributions

1. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following the [coding standards](#coding-standards)

3. Test your changes thoroughly

4. Commit your changes with clear messages

5. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

6. Open a Pull Request

## Coding Standards

### Python Style

- Follow [PEP 8](https://pep8.org/) style guide
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters
- Use type hints where appropriate
- Write docstrings for functions and classes

### Code Quality

- Keep functions focused and small
- Use meaningful variable and function names
- Comment complex logic
- Remove debug code and unused imports
- Ensure no hardcoded credentials or API keys

### Testing

- Test your changes with multiple LLM providers if applicable
- Test both GUI and CLI interfaces if your changes affect them
- Verify configuration file compatibility

## Commit Messages

Write clear, concise commit messages:

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Start with a capital letter
- Keep first line under 50 characters
- Add detailed description if needed after a blank line

Examples:
```
Add support for Claude API provider

- Implement ClaudeClient class in api_clients.py
- Add Claude configuration options
- Update documentation with setup instructions
```

## Pull Request Process

1. Update documentation for any changed functionality
2. Update CHANGELOG.md with your changes
3. Ensure your code follows the coding standards
4. Make sure all files are properly formatted
5. Reference any related issues in the PR description
6. Wait for review and address any feedback

### PR Title Format

Use descriptive titles that explain what the PR does:
- `Add: New feature description`
- `Fix: Bug description`
- `Update: What was updated`
- `Refactor: What was refactored`

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Enhancement
- [ ] Documentation update
- [ ] Refactoring

## Testing
How have you tested these changes?

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] No new warnings generated
```

## Questions?

Feel free to open an issue with the `question` label if you need help or clarification.

Thank you for contributing to Auto Chat!

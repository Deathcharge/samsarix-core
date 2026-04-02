# Contributing to Helix Collective

Thank you for your interest in contributing to the Helix Collective! We welcome contributions from developers, researchers, and enthusiasts. This guide will help you get started.

## Code of Conduct

We are committed to providing a welcoming and inclusive environment for all contributors. Please read our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

### 1. Fork and Clone

```bash
# Fork the repository on GitHub
git clone https://github.com/YOUR_USERNAME/repository-name.git
cd repository-name
git remote add upstream https://github.com/Deathcharge/repository-name.git
```

### 2. Set Up Development Environment

```bash
# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### 3. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or for bug fixes:
git checkout -b fix/issue-description
```

## Development Workflow

### Code Style

We follow **PEP 8** and use automated tools for consistency:

#### Formatting with Black

```bash
black .
```

#### Linting with Flake8

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

#### Type Checking with Mypy

```bash
mypy . --ignore-missing-imports
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ -v --cov=. --cov-report=html

# Run specific test file
pytest tests/test_module.py -v

# Run with markers
pytest -m "not slow" tests/
```

### Writing Tests

- Place tests in the `tests/` directory
- Use descriptive test names: `test_function_does_something_specific()`
- Aim for 80%+ code coverage
- Use fixtures for common setup

```python
import pytest

def test_example_function():
    """Test that example_function returns expected output."""
    result = example_function(input_value)
    assert result == expected_output

@pytest.fixture
def sample_data():
    """Fixture providing sample data for tests."""
    return {"key": "value"}

def test_with_fixture(sample_data):
    """Test using a fixture."""
    assert sample_data["key"] == "value"
```

### Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Update README.md if adding new features
- Add examples for complex functionality

```python
def process_data(input_data: dict, timeout: int = 30) -> dict:
    """Process input data with optional timeout.
    
    Longer description of what this function does and any
    important details about its behavior.
    
    Args:
        input_data: Dictionary containing the data to process.
        timeout: Maximum time in seconds to wait. Defaults to 30.
        
    Returns:
        Dictionary containing processed results with keys:
        - 'status': 'success' or 'error'
        - 'data': Processed data (if successful)
        - 'error': Error message (if failed)
        
    Raises:
        ValueError: If input_data is empty or invalid.
        TimeoutError: If processing exceeds timeout.
        
    Example:
        >>> result = process_data({'key': 'value'})
        >>> print(result['status'])
        'success'
    """
    pass
```

## Commit Guidelines

### Commit Message Format

We follow conventional commits for clear, semantic commit messages:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation only changes
- **style**: Changes that don't affect code meaning (formatting, missing semicolons, etc.)
- **refactor**: Code change that neither fixes a bug nor adds a feature
- **perf**: Code change that improves performance
- **test**: Adding missing tests or correcting existing tests
- **ci**: Changes to CI/CD configuration files and scripts
- **chore**: Changes to build process, dependencies, or tooling

### Examples

```
feat(llm-bridge): add support for Claude 3 models

- Implement Claude 3 provider integration
- Add streaming support for long responses
- Update documentation with examples

Closes #123
```

```
fix(agent-swarm): resolve memory leak in agent coordinator

Memory was not being properly released when agents completed tasks.
This was causing the coordinator to consume increasing amounts of memory
over time.

Fixes #456
```

## Pull Request Process

### Before Submitting

1. **Update from upstream**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks locally**
   ```bash
   black .
   flake8 .
   mypy .
   pytest tests/ -v --cov=.
   ```

3. **Ensure tests pass**
   - All existing tests must pass
   - Add new tests for new functionality
   - Maintain or improve code coverage

### Submitting a PR

1. Push your branch to your fork
   ```bash
   git push origin feature/your-feature-name
   ```

2. Create a Pull Request on GitHub with:
   - Clear title describing the change
   - Description of what changed and why
   - Reference to related issues (e.g., "Closes #123")
   - Screenshots for UI changes (if applicable)

3. PR Template
   ```markdown
   ## Description
   Brief description of changes
   
   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update
   
   ## Testing
   - [ ] Unit tests added/updated
   - [ ] Integration tests added/updated
   - [ ] All tests passing
   
   ## Checklist
   - [ ] Code follows style guidelines
   - [ ] Self-review completed
   - [ ] Comments added for complex logic
   - [ ] Documentation updated
   - [ ] No new warnings generated
   
   ## Related Issues
   Closes #(issue number)
   ```

### PR Review

- Maintainers will review your PR
- Respond to feedback and make requested changes
- Push additional commits to the same branch
- Once approved, your PR will be merged

## Reporting Issues

### Bug Reports

Include:
- Clear description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Python version and OS
- Relevant code or error messages
- Screenshots (if applicable)

### Feature Requests

Include:
- Clear description of the feature
- Use cases and motivation
- Proposed implementation (if you have ideas)
- Potential drawbacks or considerations

## Integration with Helix Ecosystem

When contributing to a Helix repository:

1. **Understand the ecosystem**: Familiarize yourself with how your repo integrates with others
2. **Maintain compatibility**: Don't break existing APIs without discussion
3. **Follow patterns**: Use the same patterns and conventions as other Helix repos
4. **Test integration**: Test your changes with related repositories if applicable

### Key Repositories

- **helix-core**: LLM reasoning and provider routing
- **helix-agent-swarm**: Multi-agent orchestration
- **routine-engine**: Workflow automation
- **helix-web-os**: Browser-based AI service
- **helix-discord-bot**: Discord integration

## Development Tips

### Debugging

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Use in your code
logger.debug(f"Variable value: {variable}")
logger.info("Operation completed")
logger.warning("Potential issue detected")
logger.error("An error occurred", exc_info=True)
```

### Performance Profiling

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Your code here
function_to_profile()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)  # Print top 10 functions
```

### Type Checking

```python
from typing import List, Dict, Optional, Union

def process_items(
    items: List[str],
    config: Optional[Dict[str, Union[str, int]]] = None
) -> Dict[str, List[str]]:
    """Process items with optional configuration."""
    pass
```

## Documentation Standards

### README Structure

- Overview and features
- Installation instructions
- Quick start guide
- Architecture overview
- Integration with Helix ecosystem
- Development setup
- Contributing guidelines
- License

### API Documentation

- Docstrings for all public APIs
- Type hints on all functions
- Examples for complex functionality
- Architecture diagrams where helpful

## Release Process

1. Update version number in `__init__.py` or `setup.py`
2. Update CHANGELOG.md with changes
3. Create a git tag: `git tag v1.0.0`
4. Push tag: `git push origin v1.0.0`
5. Create GitHub release with changelog

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue with bug report template
- **Ideas**: Open a GitHub Discussion or Issue with feature request template
- **Chat**: Join our community Discord (link in README)

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (typically MIT).

## Recognition

Contributors are recognized in:
- CONTRIBUTORS.md file
- GitHub contributors page
- Release notes (for significant contributions)

---

## Additional Resources

- [Python Style Guide (PEP 8)](https://www.python.org/dev/peps/pep-0008/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [Git Commit Best Practices](https://chris.beams.io/posts/git-commit/)
- [Semantic Versioning](https://semver.org/)

---

**Thank you for contributing to Helix Collective!** 🚀

Your contributions help make this project better for everyone.

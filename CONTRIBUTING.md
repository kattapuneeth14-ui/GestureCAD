# Contributing to GestureCAD 🤝

Thank you for considering contributing to **GestureCAD**! We welcome contributions from developers, designers, researchers, and enthusiasts. This document provides guidelines and instructions for contributing.

---

## 📋 Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code. Please report unacceptable behavior to the project maintainers.

---

## 🎯 How to Contribute

We welcome contributions in several forms:

### 🐛 Bug Reports

Found a bug? Please report it using our [Issue Template](ISSUE_TEMPLATE.md):

1. **Check existing issues** to avoid duplicates
2. **Create a new issue** with detailed steps to reproduce
3. **Include environment information** (OS, Python version, dependencies)
4. **Attach screenshots/videos** if applicable

### 💡 Feature Requests

Have an idea? Submit a feature request:

1. **Use the Issue Template** and select "Feature Request"
2. **Describe the use case** and why it would be valuable
3. **Provide examples** or mockups if applicable
4. **Discuss alternatives** you've considered

### 🔧 Code Contributions

Want to submit code? Follow these steps:

1. **Fork the repository**
2. **Create a feature branch** (see naming conventions below)
3. **Make your changes**
4. **Write/update tests** if applicable
5. **Follow the Code Style Guide** (see below)
6. **Create a Pull Request** using the [PR Template](PULL_REQUEST_TEMPLATE.md)

### 📚 Documentation

Improving documentation is always appreciated:

- Clarify existing documentation
- Add examples or tutorials
- Improve code comments
- Add API documentation
- Translate documentation

### 🔍 Code Review

Reviewing pull requests helps us maintain quality:

- Test PRs locally
- Provide constructive feedback
- Ask clarifying questions
- Suggest improvements

---

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- Git
- Webcam (for testing gesture features)

### Setup Development Environment

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/GestureCAD.git
cd GestureCAD

# Create a virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r polygon/src/requirements.txt

# Install development dependencies (optional)
pip install pytest black flake8 mypy
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_gesture_detector.py

# Run with coverage
pytest --cov=polygon/src
```

### Testing Gesture Features

```bash
# Launch the application
python polygon/src/main.py

# Test with your webcam to ensure gesture detection works
```

---

## 📝 Code Style Guide

### Python Code Style

We follow **PEP 8** with these guidelines:

```python
# Good: Clear variable names
hand_landmarks = extract_hand_landmarks(frame)
centroid = polygon.calculate_centroid()

# Bad: Vague abbreviations
hl = extract_hand_landmarks(frame)
cc = polygon.calculate_centroid()
```

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|----------|
| **Functions** | snake_case | `calculate_distance()`, `detect_gesture()` |
| **Classes** | PascalCase | `HandTracker`, `GestureDetector`, `Polygon` |
| **Constants** | UPPER_SNAKE_CASE | `MAX_VERTICES = 100`, `PINCH_THRESHOLD = 0.02` |
| **Private methods** | _snake_case | `_normalize_coordinates()` |
| **Protected methods** | _snake_case | `_validate_input()` |

### Code Quality Tools

**Format code with Black:**

```bash
black polygon/src/
```

**Check style with Flake8:**

```bash
flake8 polygon/src/
```

**Type checking with mypy:**

```bash
mypy polygon/src/
```

### Comments and Docstrings

```python
class Polygon:
    """Represents a 2D polygon with vertices and color.
    
    Attributes:
        vertices (list): List of (x, y) coordinate tuples
        color (tuple): BGR color tuple (B, G, R)
        is_closed (bool): Whether polygon is finalized
    """
    
    def calculate_centroid(self) -> tuple:
        """Calculate the geometric center of the polygon.
        
        Returns:
            tuple: (x, y) coordinates of the centroid
            
        Raises:
            ValueError: If polygon has fewer than 3 vertices
        """
        # Implementation here
        pass
```

---

## 🌿 Git Workflow

### Branch Naming

Use descriptive branch names:

```
feature/gesture-rotation          # New feature
fix/pinch-detection-issue         # Bug fix
docs/improve-installation-guide   # Documentation
refactor/hand-tracker-class       # Code refactoring
test/add-gesture-tests            # Tests
```

### Commit Messages

Write clear, descriptive commit messages:

```bash
# Good
git commit -m "feat: Add rotate gesture detection using hand roll angle"
git commit -m "fix: Correct polygon centroid calculation for non-convex shapes"
git commit -m "docs: Clarify gesture control section in README"

# Bad
git commit -m "fix stuff"
git commit -m "Update code"
git commit -m "asdf"
```

**Commit message format:**

```
<type>(<scope>): <subject>

<body>

<footer>
```

- **type**: feat, fix, docs, style, refactor, test, chore
- **scope**: gesture_detector, hand_tracker, ui, renderer, etc.
- **subject**: 50 character limit, imperative mood
- **body**: Explain what and why (not how)
- **footer**: Reference issues (Fixes #123)

### Pull Request Process

1. **Update your branch** with latest main:
   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. **Push your changes**:
   ```bash
   git push origin feature/your-feature
   ```

3. **Open a Pull Request** on GitHub
   - Use the [PR Template](PULL_REQUEST_TEMPLATE.md)
   - Link related issues
   - Provide clear description of changes

4. **Address review feedback**:
   - Push additional commits
   - Use `git commit --amend` for minor fixes
   - Don't force-push to preserve review history

5. **Merge**:
   - Squash commits if requested
   - Ensure CI/CD passes
   - Delete feature branch after merge

---

## 🧪 Testing Requirements

### Unit Tests

Write tests for new features:

```python
# tests/test_gesture_detector.py
import pytest
from polygon.src.gesture_detector import GestureDetector

def test_pinch_detection():
    """Test pinch gesture detection."""
    detector = GestureDetector()
    # Setup test data
    # Assert expected behavior
    assert result == expected
```

### Integration Tests

Test component interactions:

```python
def test_gesture_to_polygon_creation():
    """Test that pinch gestures create polygon vertices."""
    # Setup hand tracker, gesture detector, state machine
    # Simulate pinch gestures
    # Verify polygon is created with correct vertices
```

### Manual Testing

For gesture-based features:

1. Run `python polygon/src/main.py`
2. Test each gesture thoroughly
3. Document any issues found

---

## 📚 Documentation Guidelines

### Docstring Format

Use Google-style docstrings:

```python
def detect_pinch(landmarks: list) -> bool:
    """Detect if user is making a pinch gesture.
    
    Args:
        landmarks: List of 21 hand landmark positions
        
    Returns:
        bool: True if pinch gesture detected, False otherwise
        
    Examples:
        >>> landmarks = get_hand_landmarks(frame)
        >>> is_pinching = detect_pinch(landmarks)
    """
```

### README Updates

When submitting PRs that affect user-facing features:

- Update README.md with new features
- Update keyboard shortcuts or gesture controls
- Update installation instructions if dependencies change
- Add examples if applicable

---

## 🚨 Security Considerations

When contributing code:

- Don't hardcode API keys or credentials
- Don't expose user data
- Validate user input
- Use secure defaults
- Report security vulnerabilities privately (see SECURITY.md)

---

## 📈 Performance Considerations

When optimizing code:

- Profile before and after optimization
- Maintain readability
- Document performance improvements
- Target bottlenecks (gesture detection, rendering)

**Performance targets:**
- Gesture detection: <50ms per frame
- Rendering: 30+ FPS
- Memory usage: <200MB

---

## 🎨 UI/UX Guidelines

For UI contributions:

- Maintain consistent visual design
- Ensure accessibility (contrast, text size)
- Test with different screen resolutions
- Provide visual feedback for all interactions
- Document UI changes with screenshots

---

## ❓ Getting Help

- **Documentation**: Check [README.md](README.md) and existing issues
- **Discussions**: Use GitHub Discussions for questions
- **Issues**: Browse open issues for similar problems
- **Contact**: Reach out to maintainers for guidance

---

## 🏆 Recognition

Contributors will be recognized in:

- GitHub contributor list
- Release notes
- Project documentation

Thank you for making GestureCAD better! 🎉

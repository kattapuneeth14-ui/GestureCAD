# Security Policy for GestureCAD 🔒

## Reporting Security Vulnerabilities

At GestureCAD, we take security seriously. If you discover a security vulnerability, please report it **responsibly and confidentially**.

### ⚠️ DO NOT

- **Do NOT** open a public GitHub issue for security vulnerabilities
- **Do NOT** post security details on social media
- **Do NOT** publicly disclose the vulnerability without allowing time for a fix
- **Do NOT** exploit the vulnerability beyond what is necessary to confirm it

### ✅ DO

- **DO** report vulnerabilities privately to the maintainers
- **DO** include detailed information about the vulnerability
- **DO** give maintainers reasonable time to respond and fix the issue
- **DO** follow responsible disclosure practices

---

## How to Report a Security Vulnerability

### Method 1: GitHub Security Advisory (Recommended)

1. Go to: `https://github.com/kattapuneeth14-ui/GestureCAD/security/advisories`
2. Click **"Report a vulnerability"**
3. Fill in the vulnerability details
4. Click **"Draft a security advisory"**

### Method 2: Email

Send a detailed report to the maintainers:

📧 **Email**: [security@kattapuneeth14-ui.dev](mailto:your-security-email@example.com)

**Include the following:**

- **Type of vulnerability**: (e.g., Code Injection, Information Disclosure, etc.)
- **Affected component**: (e.g., gesture_detector.py, hand_tracker.py)
- **Description**: Clear description of the vulnerability
- **Steps to reproduce**: Detailed instructions
- **Impact**: Severity and potential consequences
- **Proof of concept**: Code or steps demonstrating the issue
- **Suggested fix**: If you have one
- **Your contact information**: For follow-up communication

### Method 3: GitHub Issue (For Public Discussion After Fix)

Once a fix is available and deployed:

1. Open an issue with a clear title
2. Reference the security advisory
3. Provide the fixed version information

---

## Vulnerability Types We Care About

### 🔴 Critical

- Remote code execution
- SQL injection or code injection
- Authentication bypass
- Privilege escalation
- Arbitrary file access

### 🟠 High

- Significant information disclosure
- Denial of service
- Unauthorized data access
- Security bypass

### 🟡 Medium

- Minor information disclosure
- Limited impact on functionality
- Requires user interaction

### 🟢 Low

- Minimal security impact
- Requires specific conditions
- Workarounds available

---

## Responsible Disclosure Timeline

1. **Report**: You discover and report a vulnerability
2. **Acknowledge**: We confirm receipt within 48 hours
3. **Assess**: We investigate and determine severity (3-5 days)
4. **Fix**: We develop and test a fix (timeline depends on severity)
5. **Coordinate**: We coordinate with you on release timing
6. **Release**: We release a patched version
7. **Disclose**: We publicly disclose the vulnerability with credit

**Typical Timeline**: 30-90 days from report to public disclosure

---

## Security Best Practices for Users

### Webcam Privacy

- GestureCAD processes video only locally; no data is sent to external servers
- Disable your webcam when not in use
- Grant camera permissions only when running GestureCAD
- Review your OS camera permission settings

### Data Files

- Exported JSON files contain polygon coordinates only
- Screenshots are saved locally in the `assets/` folder
- Delete sensitive screenshots manually
- Don't share exported files if they contain sensitive information

### Dependencies

- Keep Python and dependencies updated: `pip install --upgrade -r requirements.txt`
- Review `requirements.txt` regularly for security updates
- Use virtual environments to isolate dependencies
- Don't run untrusted code

---

## Security Considerations for Developers

### Code Review

- All code changes are subject to security review
- Focus on input validation, safe defaults, and error handling
- Avoid hardcoding sensitive values

### Dependencies

- Only use well-maintained, trusted libraries
- Check for security advisories before adding dependencies
- Specify exact versions in requirements.txt
- Regularly check for security updates

### Input Validation

- Validate all user input
- Use safe defaults
- Implement rate limiting where applicable
- Sanitize file paths

### Testing

- Write security-focused tests
- Test edge cases and error conditions
- Use type hints for early error detection

---

## Known Limitations

### Current Security Scope

GestureCAD is a **local application** without:
- Network communication
- User authentication
- Database storage
- Cloud synchronization (future feature)

This simplifies the security scope, but doesn't eliminate all risks:

### Potential Risks

1. **Local file access**: The application can read/write files in the `assets/` directory
2. **Webcam access**: Requires camera permissions at OS level
3. **Dependency vulnerabilities**: Third-party libraries may contain vulnerabilities
4. **User data**: Exported screenshots and JSON files are user's responsibility

---

## Security Headers & Policies

### Code Integrity

- Commits are made by verified contributors
- All pull requests require code review
- No direct pushes to main branch
- Changes are documented and tracked

### Release Process

- Releases are tagged with version numbers
- Release notes document changes and fixes
- Security fixes are prioritized

---

## Supported Versions

| Version | Status | Security Updates |
|---------|--------|------------------|
| 1.0.x   | Current | Yes |
| 0.x     | Deprecated | No |

Users should update to the latest version to receive security patches.

---

## Third-Party Security Advisories

### Monitored Dependencies

- **OpenCV**: Regularly updated, check [GitHub security advisories](https://github.com/opencv/opencv/security/advisories)
- **MediaPipe**: Google's active project, see [GitHub releases](https://github.com/google/mediapipe/releases)
- **NumPy**: Widely used, monitored for vulnerabilities

We monitor these for security updates and apply patches promptly.

---

## Contact & Credits

### Security Contact

**Maintainer**: Kattapuneeth Vaddadi
- Email: [your-security-email@example.com](mailto:your-security-email@example.com)
- GitHub: [@kattapuneeth14-ui](https://github.com/kattapuneeth14-ui)

### Acknowledgments

We appreciate security researchers who responsibly disclose vulnerabilities. All reporters will be credited in release notes (with permission).

---

## Additional Resources

- **OWASP**: [Top 10 Web Application Security Risks](https://owasp.org/www-project-top-ten/)
- **CWE**: [Common Weakness Enumeration](https://cwe.mitre.org/)
- **CVSS**: [Vulnerability Severity Calculator](https://www.first.org/cvss/)

---

## Policy Version

- **Last Updated**: June 2024
- **Version**: 1.0

For questions about this security policy, please contact the maintainers.

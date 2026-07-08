# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.8.x   | ✓         |
| < 0.8   | ✗         |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email **rasinbinabdulla@gmail.com** with the subject line `[SECURITY] Misata – <short description>`.

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce or a minimal proof-of-concept
- The Misata version and Python version you tested against

You will receive an acknowledgement within **72 hours**. If the report is confirmed, a fix will be released within **14 days** for critical issues and **30 days** for lower-severity ones. You are welcome to request credit in the release notes.

## Scope

Misata generates synthetic data from user-supplied schemas and stories. The main risk surface is:

- **Schema parsing / LLM-assisted generation**: malformed or adversarial YAML/JSON input leading to unexpected code execution
- **MCP server**: the `misata-mcp` process exposes tools to local AI agents; untrusted schema dicts passed through MCP could trigger path traversal or large file writes

Out of scope: issues that require physical access to the machine running Misata, or that only affect the statistical properties of generated data (not a security concern).

## Disclosure Policy

We follow coordinated disclosure. We ask that you give us reasonable time to patch before public disclosure. We will credit reporters by name (or anonymously if preferred) in the changelog.

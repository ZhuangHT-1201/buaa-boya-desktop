# Security Policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository instead of opening a
public issue with exploit details.

## Credential handling

- Passwords are stored through the operating system keyring when available.
- `config.yaml` never contains a password.
- Session cookies and local caches are stored under the user's `.autoboya` directory.
- Do not include passwords, cookies, exported session files, or identifiable account screenshots
  in issues, pull requests, or release artifacts.

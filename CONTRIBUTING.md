# Contributing

Thanks for improving Boya Automation.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m boya_kit init
python -m pytest -q
```

Launch the desktop console from source:

```powershell
python -m boya_kit.launcher
```

## Pull requests

- Keep credentials, cookies, course caches, and personal screenshots out of commits.
- Add or update tests when changing filtering, configuration, or localization behavior.
- Keep all user-facing strings available in both Chinese and English.
- Describe the user-facing impact and the verification you performed.

## Scope

The project targets the BUAA Boya web application through the upstream
[AutoBoya](https://github.com/DeNeRATe-cool/AutoBoya) package. Upstream HTML or API changes
should be handled in AutoBoya where possible.

"""Export both contracts without connecting to the database."""

import json
import os
from pathlib import Path

# Contract generation uses explicit nonproduction settings, never deployment credentials.
os.environ["KITCHEN_ENVIRONMENT"] = "test"

from kitchen_admin_api.main import create_app as create_admin_app
from kitchen_api.main import create_app

directory = Path("docs/openapi")
directory.mkdir(parents=True, exist_ok=True)
for name, app in (("api", create_app()), ("admin", create_admin_app())):
    (directory / f"{name}.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")

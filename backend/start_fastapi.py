import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

import uvicorn
uvicorn.run("api.main:app", host="0.0.0.0", port=8001, reload=False)

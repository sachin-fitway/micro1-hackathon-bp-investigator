#!/usr/bin/env python3
"""Launch the Incident Investigator web UI."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("ui.app:app", host="127.0.0.1", port=8080, reload=False)

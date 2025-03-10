# How to run the test

Under the root folder, run the following commands

```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r metadata/ota_metadata/requirements.txt
pip3 install -r metadata/ota_metadata/tests/requirements.txt
pytest metadata/ota_metadata/tests/

# Initial commit provenance

`initial-commit.json` records the author, UTC creation time, GPG signing key and SHA-256 hashes of the project files. The `provenance/` directory is excluded from the file manifest. FreeTSA's RFC 3161 response timestamps the SHA-256 digest of this record. The signed Git commit covers the complete tree, including this evidence.

From the repository root, verify the timestamp and file hashes at the initial commit:

```sh
openssl ts -verify -data provenance/initial-commit.json -in provenance/initial-commit.tsr -CAfile provenance/cacert.pem -untrusted provenance/tsa.crt
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess

revision = subprocess.check_output(['git', 'rev-list', '--max-parents=0', 'HEAD'], text=True).strip()
record = json.loads(Path('provenance/initial-commit.json').read_text())
for entry in record['files']:
    contents = subprocess.check_output(['git', 'show', f"{revision}:{entry['path']}"])
    assert hashlib.sha256(contents).hexdigest() == entry['sha256'], entry['path']
print('File hashes verified.')
PY
git verify-commit "$(git rev-list --max-parents=0 HEAD)"
```

`signer.asc` contains the public GPG key. Import it with `gpg --import provenance/signer.asc` if the key is not in your keyring. Inspect the authority's timestamp with `openssl ts -reply -in provenance/initial-commit.tsr -text`. Certificates were obtained from [FreeTSA](https://freetsa.org/).

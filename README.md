# Immich Sync (minimal CLI)

Asset-by-asset synchroniser for Immich servers. The tool reads a single JSON
configuration that lists every server/album pair and then ensures every asset
appears on every server. Missing assets are copied from the first server that
already contains them; if an asset already exists remotely it is simply added to
the configured album.

## Install

The project uses [uv](https://github.com/astral-sh/uv) but any PEP 517 compatible
installer works.

```powershell
uv sync
```

## Configure

Create a JSON file (see `config.example.json`) that lists all servers to take
part in the sync. The shape is:

```json
{
	"servers": [
		{
			"name": "primary",
			"base_url": "https://immich.example",
			"api_key": "YOUR_API_KEY",
			"album_id": "UUID-OF-ALBUM",
			"size_limit_bytes": 524288000
		},
		{
			"name": "secondary",
			"base_url": "https://immich.other",
			"api_key": "ANOTHER_KEY",
			"album_id": "UUID-OF-ALBUM"
		}
	]
}
```

`size_limit_bytes` is optional; assets larger than the limit are skipped for
that target.

## Run

```powershell
uv run immich-sync --config config.json
```

Use `--dry-run` to compute the plan without transferring data and `--verbose`
for additional logging. Each missing asset/target pair is processed
individually and the CLI displays a `tqdm` progress bar so you can follow the
sync in real time.

The CLI prints a short summary that includes copy counts, link counts (when an
asset already exists on a target) and any errors that occurred.

## Development

- Lint: `uv run ruff check .`
- Tests: `uv run pytest`

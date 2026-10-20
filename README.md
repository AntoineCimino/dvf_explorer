# DVF Explorer

DVF Explorer is an open-source project to preserve successive public DVF
publication snapshots, track row-level changes, and serve geographic summaries
and transaction details through browser explorers covering the source's French
territory. The [ChatGPT Site](https://dvf-explorer.sci-cimino-eggrickx.chatgpt.site/)
is public. Transaction datasets and derived exports are hosted separately from
this code repository.

## Source and reuse

The source data is **DGFiP — Demandes de valeurs foncières (DVF)**, published
under [Licence Ouverte 2.0](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres).
The MIT license in this repository applies to the code, not to DVF data.

Reuse of DVF data must follow the [source dataset's conditions](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres)
and [article R*112 A-3 of the Livre des procédures fiscales](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000038001715/):
processing must not enable re-identification of people, and DVF information
must not be indexed by online search engines. The planned public interfaces
will include `robots.txt` and `<meta name="robots" content="noindex, nofollow">`.
The public Site and downloads attribute the source to DGFiP and link to the
[data.gouv.fr dataset](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres).
The Site keeps its data routes out of search indexes and offers source,
versioned Parquet, indicator, search-index, and row-history downloads from its
separate data host. See [the export contract](docs/exports_contract.md).

## Local commands

From this directory:

```sh
python -m src.main --help
pytest tests/ -v
```

Raw text files belong under the ignored `data/raw_txt/` directory. Generated
Parquet and browser exports are also ignored. Use the local archive import for
historical files and the weekly sync job for future data.gouv.fr publications.

## Local pipeline

Install dependencies with `python -m pip install -r requirements.txt`, then:

```sh
python -m src.main import-archive /path/to/local/dvf-archive
python -m src.main sync --dry-run
python -m src.main view
```

The source registry stores only source basenames and must never store private
archive paths. Do not publish DVF data that could enable re-identification or
allow external search indexing.

See [the backup and restore procedure](docs/backup_restore.md) for restoring an
exact published year and version from the separate public data host.

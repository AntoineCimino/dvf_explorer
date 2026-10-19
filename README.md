# DVF Explorer

DVF Explorer is an open-source project to preserve successive public DVF
publication snapshots, track row-level changes, and serve geographic summaries
and transaction details through browser explorers covering the source's French
territory. The repository is currently in its local pipeline stage; there is
not yet a published explorer front.

The project goal is a versioned historical transaction dataset, geographic
summaries, and two browser explorer fronts. Historical data ingestion and
public data release are separate steps; the code repository does not include DVF data.

## Source and reuse

The source data is **DGFiP — Demandes de valeurs foncières (DVF)**, published
under [Licence Ouverte 2.0](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres).
The MIT license in this repository applies to the code, not to DVF data.

Reuse of DVF data must follow the [source dataset's conditions](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres)
and [article R*112 A-3 of the Livre des procédures fiscales](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000038001715/):
processing must not enable re-identification of people, and DVF information
must not be indexed by online search engines. The planned public interfaces
will include `robots.txt` and `<meta name="robots" content="noindex, nofollow">`.
Publishing the historical archive and derived data remains an owner decision.

## Local commands

From this directory:

```sh
python -m src.main --help
pytest tests/ -v
```

Raw text files belong under the ignored `data/raw_txt/` directory. Generated
Parquet and browser exports are also ignored. Release assets and public browser
fronts require validation of the publishing and hosting approach first.

## Local pipeline

Install dependencies with `python -m pip install -r requirements.txt`, then:

```sh
python -m src.main ingest /path/to/valeursfoncieres-2024.txt --origin datagouv
python -m src.main view
```

The source registry stores only source basenames and must never store private
archive paths. Do not publish DVF data that could enable re-identification or
allow external search indexing.

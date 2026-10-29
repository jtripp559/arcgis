# Crop Loss News Web Scraper

Scrapes news articles related to agricultural crop loss using the **GDELT** project (Global Database of Events, Language, and Tone) and applies NLP filtering to identify relevant stories.

## Contents

- `CropLossNewsScrapper.py` - main script. Queries GDELT via `gdeltdoc`, fetches article HTML with `requests` + `BeautifulSoup`, then applies tokenization / keyword filtering (NLTK `punkt`, gensim, iNLTK for Indic languages).
- `keywords.json` - search and filter keyword configuration.
- `punkt.lnk` - Windows shortcut to a local NLTK `punkt` tokenizer data directory.

## Dependencies

Not part of the ArcGIS Pro conda env by default - see the install comments at the top of `CropLossNewsScrapper.py`:

```
pip install gdeltdoc
conda install requests bs4 gensim nltk scikit-learn pydantic typing_extensions googletrans
pip install inltk
```

NLTK requires the `punkt` tokenizer data. The `punkt.lnk` shortcut points at a local copy; if it's missing, run `nltk.download('punkt')` in the active env.

## Notes

iNLTK is cited via the Arora 2020 paper bundled in the script docstring - keep that attribution if redistributing.

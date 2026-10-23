"""WebforAI regional travel-site pipeline: one engine, one data/<city>/site.json per city.

Modules
- city      : site.json -> City (addresses, 구·군, region names, summary rules, designations) — the only
              place city-specific behaviour is derived
- romanize  : Revised Romanization of Korean (English pages, slugs)
- slugs     : ASCII URL slugs and fragment ids
- textutil  : text cleaning, hashes, national address renames
- schema    : entity/field definitions, licence codes, labels
- maplinks  : map / navigation links (precise vs search)
- tourapi   : TourAPI client with disk cache
- importer  : CSV -> places.json (contract for collectors / v0 data)
- enrich    : match entities to TourAPI and fill facts, geo, nearby, images
- jsonld    : schema.org graphs
- build     : static site renderer
- validate  : QA checks and report
"""

__version__ = "0.1.0"

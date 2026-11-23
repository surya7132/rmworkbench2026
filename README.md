# Compass: RM workbench for RBL Bank

All data is synthetic. No real client, person or company.

## Run it (Python 3.11 or newer)
    pip install -r requirements.txt
    python -m app.main              # or: uvicorn app.main:app --reload
    # open http://127.0.0.1:8000  (demo logins are on the sign-in page; password Demo@2026)

The database (`data/compass.db`) is built from the seed on first start. "Reset demo" in the user menu rebuilds it.
Styling comes from CDN scripts (Tailwind, htmx, Alpine, Cytoscape), so the machine needs internet for the look to load.

Demo logins (password `Demo@2026`): rohan.rm, karan.rm, meera.lead, kavita.trade, ananya.credit

## Folder structure
    compass/
      app/                         the web app
        main.py                    starts the app and plugs in every feature
        config.py db.py auth.py clock.py templating.py     shared plumbing
        templates/                 pages every feature shares
          base.html                the frame: sidebar, top bar
          _macros.html             small reusable chips
        static/
          css/app.css              styles
          js/relmap.js             the relationship map drawing
        features/                  one folder per screen; its code and its HTML sit together
          auth/                    sign-in, sign-out, Reset demo, demo clock
            router.py  login.html
          home/                    "/" goes to the work queue
            router.py
          work/                    work queue
            router.py  service.py  index.html  _list.html  _row.html  _thread.html
          clients/                 client list, client page, relationship map
            router.py  service.py  detail.py  index.html  detail.html  _table.html
          events/                  market events and routing ("Process")
            router.py  service.py  index.html  detail.html  _list.html
          meetings/                brief, debrief, dictation, optional AI
            router.py  service.py  ai.py  index.html  detail.html
          alerts/                  early warning triage
            router.py  service.py  index.html  _list.html  _card.html  _tiles.html
          spreading/               upload a report, read it, check it beside the report, sign off, export to Excel or CSV
            router.py  service.py  extract.py  export.py  index.html  detail.html  _body.html
      seed/                        builds the fake world
        ids.py                     CIN, PAN, LEI, DIN generators with real check rules
        financials.py              Vantage and Meridian statements that tie out
        make_pdfs.py make_scan.py  the two sample annual-report PDFs (Meridian is made to look scanned)
        world_nodes.py world_ops.py expand.py realworld.py     companies, people, events, alerts, work items
        graph.py routing.py        walks the graph; one event to the right people with "why you see this"
        build_db.py validate.py    build the database; 1,367 data-quality checks (must say 0 failed)
        data/mockup_seed.json      starting data from the mockup
      db/schema.sql                the tables
      data/
        compass.db                 created on first start
        sample_docs/               the two sample annual reports
        uploads/                   reports uploaded on the Spreading screen (cleared by Reset demo)
        real_world_sources.csv     sources for the real news items
        compass_data_preview.xlsx  a spreadsheet view of the data
      tests/                       one file per feature; run each with python tests/<file>
        test_shell_work_clients.py test_events.py test_meetings.py test_alerts.py test_spreading.py test_spreading_upload.py
        asgi_client.py shim/       test helpers
      requirements.txt

## How a feature is wired
A feature folder holds everything for one screen: `router.py` (the web addresses), `service.py` (the rules and database
work) and the HTML pages. Pages are named by their folder, for example `alerts/index.html` (the list) and
`alerts/_card.html` (a piece of it that the page swaps in place). A leading underscore means "a piece, not a full page".
A feature that needs another's logic imports it by folder, for example `from ..work import service as W`.

## Tests
    python tests/test_shell_work_clients.py
    python tests/test_events.py
    python tests/test_meetings.py
    python tests/test_alerts.py
    python tests/test_spreading.py
    python tests/test_spreading_upload.py
    python -m seed.build_db        # builds data/compass.db if it is not there yet (the app also does it on first start)
    python -m seed.validate        # must say 0 failed

## Optional
`ANTHROPIC_API_KEY` switches on AI help on the meeting screen (off when not set). Dictation uses the browser's own speech service.

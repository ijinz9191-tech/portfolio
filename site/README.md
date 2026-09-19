# Engineering Portfolio site

Static, dependency-free public introduction. Publish ONLY `index.html` and `styles.css` from this directory. This page has no API, account integration, application data, cookies, forms or external fonts.

## Local checks

From repository root, Node.js 24:

```
node --test --test-isolation=none site/test.mjs
node site/serve.mjs
```

Preview: http://127.0.0.1:4189 (local only). Stop with Ctrl+C. The preview allows two public assets; unknown paths return 404 and writes return 405. Automated tests cover content, links/anchors, CSS asset, headers, forbidden paths and writes. Browser mobile/desktop visual verification is a separate check.

## Publication

No deployment is performed by these commands. GitHub Pages can serve these static assets through an approved Pages workflow or a publishing branch. Repository Pages settings, credentials and actual anonymous URL must be verified by the publisher. Do not publish the whole repository or runtime SQLite files. The `ai/sre` application needs its own local Node API and is linked as source, not an online demo.

## Truth and maintenance

Existing Incident Replay Lab is not attributed to a new job application. Append newly verified projects to the site and `ai/PROJECTS.md`; preserve `ai/README.md`. Public application counts and unmeasured automation metrics are omitted. AI authored these site files under user-provided goals; no claim of independent user implementation is made.

# pablopunk's AltStore PAL source

[![Add to AltStore PAL](https://img.shields.io/badge/AltStore_PAL-Add_source-1DB954?logo=apple)](https://altstore.io/source/pablopunk.github.io/altstore/apps.json)

Notarized builds of my iOS apps for [AltStore PAL](https://altstore.io) (EU, Japan and Brazil).

Source URL: `https://pablopunk.github.io/altstore/apps.json`

| App | Repo |
| --- | --- |
| Spotifin | [pablopunk/spotifin](https://github.com/pablopunk/spotifin) |

## How it works

1. An app repo uploads a release build to App Store Connect and submits it for **Notarization**.
2. Every 3 hours, [`sync.yml`](.github/workflows/sync.yml) looks for notarized versions that `apps.json` does not have yet.
3. For each one, it asks AltStore PAL to process the alternative distribution package (ADP), uploads the ADP files to a release of this repo, and adds the version to `apps.json`.

## Add an app

1. In App Store Connect, give AltStore PAL permission to distribute the app (Users and Access → Integrations → Marketplace).
2. Add the app to `apps` in `apps.json` (leave `versions` empty and `marketplaceID` blank; the sync fills them).
3. Map its bundle ID to its GitHub repo in `repos.json`, so release notes come from that repo's releases.

## Secrets

`ASC_KEY_ID`, `ASC_ISSUER_ID` and `ASC_PRIVATE_KEY`: an App Store Connect API key with the App Manager role.

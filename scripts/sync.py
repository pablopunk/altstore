#!/usr/bin/env python3
"""Add every newly notarized app version from App Store Connect to apps.json.

For each app: find notarized versions missing from the source, ask AltStore PAL to
process their ADP, then publish the ADP files as a GitHub release of this repo.
"""

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from app_store_connect import AppStoreConnect, AppStoreConnectError  # noqa: E402
from ipa_permissions import ipa_permissions  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "apps.json"
REPOS = ROOT / "repos.json"
ALTSTORE_API = "https://api.altstore.io"
ALTSTORE_USER_AGENT_ALLOWED_BY_CLOUDFLARE = "pablopunk-altstore-sync/1.0"
SOURCE_REPO = os.environ.get("GITHUB_REPOSITORY", "pablopunk/altstore")


def altstore(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(ALTSTORE_API + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", ALTSTORE_USER_AGENT_ALLOWED_BY_CLOUDFLARE)
    with urllib.request.urlopen(request) as response:
        payload = response.read()
    return json.loads(payload) if payload else {}


def published_builds(app):
    return {(version["version"], version["buildVersion"]) for version in app["versions"]}


def candidate_versions(api, app_id):
    response = api.get(
        f"/v1/apps/{app_id}/appStoreVersions",
        **{"filter[platform]": "IOS", "include": "build", "limit": 10},
    )
    builds = {item["id"]: item["attributes"]["version"] for item in response.get("included", []) if item["type"] == "builds"}
    for version in reversed(response["data"]):
        build = (version["relationships"].get("build") or {}).get("data")
        if build and build["id"] in builds:
            yield version["id"], version["attributes"]["versionString"], builds[build["id"]]


def adp_id(api, version_id):
    try:
        return api.get(f"/v1/appStoreVersions/{version_id}/alternativeDistributionPackage")["data"]["id"]
    except AppStoreConnectError as error:
        if "failed with 404" in str(error):
            return None
        raise


def processed_adp_download_url(adp):
    try:
        status = altstore("GET", f"/adps/{adp}")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        altstore("POST", "/adps", {"adpID": adp})
        print(f"Asked AltStore to process ADP {adp}")
        return None
    if status.get("downloadURL"):
        return status["downloadURL"]
    print(f"AltStore is still processing ADP {adp}: {status.get('status')}")
    return None


def download_adp(url, directory):
    archive = directory / "adp.zip"
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as adp:
        adp.extractall(directory / "adp")
    return [path for path in (directory / "adp").rglob("*") if path.is_file() and path.name != ".DS_Store"]


def release_notes(bundle_id, version):
    repo = json.loads(REPOS.read_text()).get(bundle_id)
    if not repo:
        return None
    result = subprocess.run(
        ["gh", "release", "view", f"v{version}", "--repo", repo, "--json", "body", "--jq", ".body"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or f"https://github.com/{repo}/releases/tag/v{version}"


def publish_release_assets(tag, files):
    names = [path.name for path in files]
    if len(names) != len(set(names)):
        raise RuntimeError(f"ADP has files with the same name in different folders: {names}")
    release_exists = subprocess.run(["gh", "release", "view", tag, "--repo", SOURCE_REPO], capture_output=True).returncode == 0
    if not release_exists:
        subprocess.run(["gh", "release", "create", tag, "--repo", SOURCE_REPO, "--title", tag, "--notes", tag], check=True)
    subprocess.run(["gh", "release", "upload", tag, "--repo", SOURCE_REPO, "--clobber", *map(str, files)], check=True)
    base = f"https://github.com/{SOURCE_REPO}/releases/download/{tag}"
    return {path.stem: f"{base}/{path.name}" for path in files}


def sync_version(app, version, build_number, download_url):
    with tempfile.TemporaryDirectory() as temporary:
        files = download_adp(download_url, pathlib.Path(temporary))
        ipas = [path for path in files if path.suffix == ".ipa"]
        manifest = json.loads(next(path for path in files if path.name == "manifest.json").read_text())
        if zipfile.is_zipfile(ipas[0]):
            app["appPermissions"], _ = ipa_permissions(ipas[0])
        tag = f"{app['bundleIdentifier']}-{version}-{build_number}"
        asset_urls = publish_release_assets(tag, files)
        entry = {
            "version": version,
            "buildVersion": build_number,
            "date": datetime.date.today().isoformat(),
            "localizedDescription": release_notes(app["bundleIdentifier"], version),
            "downloadURL": asset_urls["manifest"],
            "assetURLs": asset_urls,
            "size": ipas[0].stat().st_size,
            "minOSVersion": manifest["minimumSystemVersions"]["ios"],
        }
    app["versions"].insert(0, {key: value for key, value in entry.items() if value})
    print(f"Published {app['name']} {version} ({build_number})")


def sync_app(api, app):
    app_id = api.app_id_for_bundle(app["bundleIdentifier"])
    app["marketplaceID"] = app_id
    published = published_builds(app)
    for version_id, version, build_number in candidate_versions(api, app_id):
        if (version, build_number) in published:
            continue
        adp = adp_id(api, version_id)
        if not adp:
            continue
        download_url = processed_adp_download_url(adp)
        if download_url:
            sync_version(app, version, build_number, download_url)


def main():
    source = json.loads(SOURCE.read_text())
    api = AppStoreConnect.from_environment()
    for app in source["apps"]:
        sync_app(api, app)
    SOURCE.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

"""Read the entitlements and privacy strings AltStore checks from a signed .ipa."""

import plistlib
import re
import zipfile

IMPLICIT_ENTITLEMENTS = {"application-identifier", "com.apple.developer.team-identifier"}
EMBEDDED_PLIST = re.compile(rb"<\?xml[^>]*\?>\s*<!DOCTYPE plist.*?</plist>", re.DOTALL)


def _app_dir(names):
    return next(name.split("/")[1] for name in names if re.match(r"Payload/[^/]+\.app/Info\.plist$", name))


def _entitlements_in_binary(binary):
    for match in EMBEDDED_PLIST.finditer(binary):
        plist = plistlib.loads(match.group(0))
        if isinstance(plist, dict) and "com.apple.developer.team-identifier" in plist:
            return plist
    raise ValueError("The app binary has no signed entitlements")


def ipa_permissions(ipa_path):
    with zipfile.ZipFile(ipa_path) as ipa:
        app = _app_dir(ipa.namelist())
        info = plistlib.loads(ipa.read(f"Payload/{app}/Info.plist"))
        binary = ipa.read(f"Payload/{app}/{info['CFBundleExecutable']}")
    entitlements = _entitlements_in_binary(binary)
    return {
        "entitlements": sorted(key for key in entitlements if key not in IMPLICIT_ENTITLEMENTS),
        "privacy": {key: value for key, value in sorted(info.items()) if key.endswith("UsageDescription")},
    }, info


def minimum_os_version(info):
    return info.get("MinimumOSVersion")

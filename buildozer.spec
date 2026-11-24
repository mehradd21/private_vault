[app]

title = App
package.name = privatevault
package.domain = org.mehrad

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,xml
source.exclude_dirs = tests,bin,.buildozer,docs,__pycache__

version = 1.0

# cryptography -> AES-256-GCM, argon2-cffi -> Argon2id, pyjnius -> Android API,
# Pillow -> thumbnails, ffpyplayer -> in-app video playback.
# ffpyplayer_codecs is intentionally omitted: current p4a/ffmpeg builds do not
# install libpostproc headers, which makes ffpyplayer fail to compile with it.
requirements = python3,kivy,cryptography,argon2-cffi,pyjnius,Pillow,ffpyplayer

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/icon.png

orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 24
android.sdk = 35
android.ndk = 27c
android.ndk_api = 24
android.archs = arm64-v8a

# Storage Access Framework works through URI permissions; no broad storage
# permission is requested. This vault never reads public storage directly.
android.permissions =

# FileProvider for safe, read-only "open with" sharing of temporary files.
android.gradle_dependencies = androidx.core:core:1.9.0
android.enable_androidx = True
android.add_resources = ./android/provider_paths.xml:xml/provider_paths.xml
android.extra_manifest_application_arguments = ./android/provider.xml

# No Google backup of the encrypted vault or its key material.
android.allow_backup = False

android.release_artifact = apk
android.debug_artifact = apk
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1

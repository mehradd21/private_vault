[app]

title = App
package.name = privatevault
package.domain = org.mehrad

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,xml
source.exclude_dirs = tests,bin,.buildozer,.p4a,docs,__pycache__

version = 1.0

# cryptography -> AES-256-GCM, argon2-cffi -> Argon2id, pyjnius -> Android API,
# Pillow -> thumbnails, ffpyplayer -> in-app video playback.
# ffpyplayer_codecs is intentionally omitted: it pulls extra codec libraries
# without adding codecs needed for ordinary MP4 playback on Android.
requirements = python3,kivy,cryptography,argon2-cffi,pyjnius,Pillow,ffpyplayer

# p4a develop now builds FFmpeg 8, whose headers are incompatible with
# ffpyplayer 4.5.1 (libavcodec/avfft.h was removed). This commit is the last
# known-good state with FFmpeg 6.1.2 and ffpyplayer 4.5.1.
p4a.branch = develop
p4a.commit = 37d272cc42f1ca0d0143743ccd3949cca56dfd5d
# The workflow clones and patches this checkout to pin build==1.4.2.
p4a.source_dir = .p4a

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/icon.png

orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 24
android.sdk = 35
android.ndk = 25b
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

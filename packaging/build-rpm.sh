#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
version="$(cat VERSION)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
spec_version="$(rpmspec -q --qf '%{version}' packaging/write-app.spec)"
[[ "$version" == "$spec_version" ]] || { echo 'VERSION and RPM spec disagree' >&2; exit 1; }
if [[ "${GITHUB_REF_TYPE:-}" == tag ]]; then
    [[ "$GITHUB_REF_NAME" == "v$version" ]] || { echo 'Tag and VERSION disagree' >&2; exit 1; }
fi
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT
mkdir -p "$build_dir/SOURCES" dist
tar --exclude='__pycache__' --exclude='*.pyc' \
    --transform="s,^,write-app-$version/," -czf "$build_dir/SOURCES/write-app-$version.tar.gz" \
    main.py app_settings.py project_colors.py project_search.py settings_ui.py themes.py spelling.py references.py reference_api.py reference_widgets.py updater.py update_helper.py WRITE-RPM-KEY.asc VERSION write.svg write.desktop README.md CHANGELOG.md \
    requirements.txt install.sh boxicons kokoro_tts tests packaging
rpmbuild -ba --define "_topdir $build_dir" packaging/write-app.spec
cp "$build_dir"/RPMS/noarch/*.rpm "$build_dir"/SRPMS/*.rpm dist/
(cd dist && sha256sum *.rpm > SHA256SUMS)

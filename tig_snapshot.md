---
{
  "tig_cli_version": "1.5",
  "generated_at": "2026-06-02T17:51:06Z",
  "target": "/Users/dmitrysolonnikov/PycharmProjects/overhead_analyzer",
  "mode": "compact",
  "fingerprint": "sha256:5d2214dd4877ad64",
  "git_head": "ffddf3cdbe0b58571e37e0fe769871b63cfac2f2",
  "git_dirty": true,
  "base_ref": "HEAD~1",
  "base_ref_note": "fallback:HEAD~1 (preferred 'origin/main' missing)",
  "file_count": 233,
  "total_files": 233
}
---

# TIG Snapshot

**Project:** `overhead_analyzer`
**Mode:** `compact` | **Fingerprint:** `sha256:5d2214dd4877ad64`
**Base ref:** `HEAD~1` (fallback:HEAD~1 (preferred 'origin/main' missing))

## Module map

| Module | Files | Size |
|--------|------:|-----:|
| `.cursor` | 37 | 164241 bytes |
| `.DS_Store` | 1 | 6148 bytes |
| `.github` | 1 | 650 bytes |
| `.gitignore` | 1 | 1445 bytes |
| `.key` | 1 | 394 bytes |
| `.runtime_store` | 2 | 32768 bytes |
| `app_gpa` | 172 | 1339223 bytes |
| `gpa_project_struct.md` | 1 | 1121732 bytes |
| `LICENSE` | 1 | 1074 bytes |
| `README.md` | 1 | 46380 bytes |
| `README_CUSTOM_RULES.md` | 1 | 3514 bytes |
| `scripts` | 12 | 145828 bytes |
| `tig_app_ru.py` | 1 | 40718 bytes |
| `todo.md` | 1 | 7350 bytes |

**Total:** 233 files

## Directory tree

*depth ≤ 2*

```text
overhead_analyzer/
├── .cursor/
│   ├── context/
│   │   ├── dialogs/ …
│   ├── dci/
│   │   ├── init/ …
│   ├── rules/
│   ├── skills/
│   │   ├── b2c-team/ …
│   │   ├── de-matrix-team/ …
│   │   ├── dialog-context-index/ …
│   │   ├── gpa-agent-team/ …
│   │   ├── presentation-team/ …
│   │   ├── sql-team/ …
│   │   ├── web-app-team/ …
├── .github/
│   ├── workflows/
├── .runtime_store/
│   ├── jobs_state/
│   │   ├── jobs/ …
│   ├── presets/
│   ├── app_state.sqlite3-shm
│   ├── app_state.sqlite3-wal
├── app_gpa/
│   ├── agent/
│   ├── api/
│   │   ├── routers/ …
│   ├── config/
│   ├── core/
│   ├── detailed/
│   │   ├── lint/ …
│   ├── infrastructure/
│   ├── modules/
│   │   ├── agents/ …
│   │   ├── analysis/ …
│   ├── scripts/
│   ├── services/
│   │   ├── agents/ …
│   │   ├── cache/ …
│   │   ├── runtime/ …
│   │   ├── sql/ …
│   ├── var/
│   │   ├── agent_cache/ …
│   ├── web/
│   │   ├── routes/ …
│   │   ├── static/ …
│   │   ├── templates/ …
│   ├── app_settings.py
│   ├── conftest.py
│   ├── main.py
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── webapp.py
│   ├── worker.py
├── scripts/
│   ├── dci-propagate.sh
│   ├── dci-setup-projects.sh
│   ├── dci-test.sh
│   ├── dci-validate-all-projects.sh
│   ├── dci-vector.sh
│   ├── dci_embed_server.py
│   ├── dci_vector_sync.py
│   ├── rules-validate-all-projects.sh
│   ├── run-app.sh
│   ├── sync-to-pycharm.sh
│   ├── tig-context.sh
│   ├── tig-test.sh
├── .DS_Store
├── .gitignore
├── .key
├── gpa_project_struct.md
├── LICENSE
├── README.md
├── README_CUSTOM_RULES.md
├── tig_app_ru.py
├── todo.md
```

## Git evolution (compact)

```text
Корень: /Users/dmitrysolonnikov/PycharmProjects/overhead_analyzer

=== STATUS ===
M .venv/bin/pip
 M .venv/bin/pip3
 M .venv/bin/pip3.9
 D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/INSTALLER
 D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/LICENSE.txt
 D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/METADATA
 D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/RECORD
 D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/REQUESTED
 D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/WHEEL
 D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/entry_points.txt
 D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/top_level.txt
 M .venv/lib/python3.9/site-packages/pip/__init__.py
 M .venv/lib/python3.9/site-packages/pip/__main__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/build_env.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cache.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/autocompletion.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/base_command.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/cmdoptions.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/command_context.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/main.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/main_parser.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/parser.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/progress_bars.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/req_command.py
 M .venv/lib/python3.9/site-packages/pip/_internal/cli/spinners.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/cache.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/check.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/completion.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/configuration.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/debug.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/download.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/freeze.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/hash.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/help.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/index.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/install.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/list.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/search.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/show.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/uninstall.py
 M .venv/lib/python3.9/site-packages/pip/_internal/commands/wheel.py
 M .venv/lib/python3.9/site-packages/pip/_internal/configuration.py
 M .venv/lib/python3.9/site-packages/pip/_internal/distributions/base.py
 M .venv/lib/python3.9/site-packages/pip/_internal/distributions/installed.py
 M .venv/lib/python3.9/site-packages/pip/_internal/distributions/sdist.py
 M .venv/lib/python3.9/site-packages/pip/_internal/distributions/wheel.py
 M .venv/lib/python3.9/site-packages/pip/_internal/exceptions.py
 M .venv/lib/python3.9/site-packages/pip/_internal/index/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/index/collector.py
 M .venv/lib/python3.9/site-packages/pip/_internal/index/package_finder.py
 M .venv/lib/python3.9/site-packages/pip/_internal/index/sources.py
 M .venv/lib/python3.9/site-packages/pip/_internal/locations/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/locations/_distutils.py
 M .venv/lib/python3.9/site-packages/pip/_internal/locations/_sysconfig.py
 M .venv/lib/python3.9/site-packages/pip/_internal/locations/base.py
 M .venv/lib/python3.9/site-packages/pip/_internal/main.py
 M .venv/lib/python3.9/site-packages/pip/_internal/metadata/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/metadata/base.py
 M .venv/lib/python3.9/site-packages/pip/_internal/metadata/pkg_resources.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/candidate.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/direct_url.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/format_control.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/index.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/link.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/scheme.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/search_scope.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/selection_prefs.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/target_python.py
 M .venv/lib/python3.9/site-packages/pip/_internal/models/wheel.py
 M .venv/lib/python3.9/site-packages/pip/_internal/network/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/network/auth.py
 M .venv/lib/python3.9/site-packages/pip/_internal/network/cache.py
 M .venv/lib/python3.9/site-packages/pip/_internal/network/download.py
 M .venv/lib/python3.9/site-packages/pip/_internal/network/lazy_wheel.py
 M .venv/lib/python3.9/site-packages/pip/_internal/network/session.py
 M .venv/lib/python3.9/site-packages/pip/_internal/network/utils.py
 M .venv/lib/python3.9/site-packages/pip/_internal/network/xmlrpc.py
 M .venv/lib/python3.9/site-packages/pip/_internal/operations/build/metadata.py
 D .venv/lib/python3.9/site-packages/pip/_internal/operations/build/metadata_legacy.py
 M .venv/lib/python3.9/site-packages/pip/_internal/operations/build/wheel.py
 D .venv/lib/python3.9/site-packages/pip/_internal/operations/build/wheel_legacy.py
 M .venv/lib/python3.9/site-packages/pip/_internal/operations/check.py
 M .venv/lib/python3.9/site-packages/pip/_internal/operations/freeze.py
 M .venv/lib/python3.9/site-packages/pip/_internal/operations/install/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_internal/operations/install/editable_legacy.py
 D .venv/lib/python3.9/site-packages/pip/_internal/operations/install/legacy.py
 M .venv/lib/python3.9/site-packages/pip/_internal/operations/install/wheel.py
 M .venv/lib/python3.9/site-packages/pip/_internal/operations/prepare.py
 M .venv/lib/python3.9/site-packages/pip/_internal/pyproject.py
 M .venv/lib/python3.9/site-packages/pip/_internal/req/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_internal/req/constructors.py
 M .venv/lib/python3.9/site-packages/pip/_internal/req/req_file.py
 M .venv/lib/python3.9/site-packages/pip/_internal/req/req_install.py
 M .venv/lib/python3.9/site-packages/pip/_internal/req/req_set.py
 D .venv/lib/python3.9/site-packages/pip/_internal/req/req_tracker.py
 M .venv/lib/python3.9/site-packages/pip/_internal/req/req_uninstall.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/base.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/legacy/resolver.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/base.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/candidates.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/factory.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/provider.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/reporter.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/requirements.py
 M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/resolver.py
 M .venv/lib/python3.9/site-packages/pip/_internal/self_outdated_check.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/appdirs.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/compat.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/compatibility_tags.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/datetime.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/deprecation.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/direct_url_helpers.py
 D .venv/lib/python3.9/site-packages/pip/_internal/utils/distutils_args.py
 D .venv/lib/python3.9/site-packages/pip/_internal/utils/encoding.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/entrypoints.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/filesystem.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/filetypes.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/glibc.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/hashes.py
 D .venv/lib/python3.9/site-packages/pip/_internal/utils/inject_securetransport.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/logging.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/misc.py
 D .venv/lib/python3.9/site-packages/pip/_internal/utils/models.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/packaging.py
 D .venv/lib/python3.9/site-packages/pip/_internal/utils/parallel.py
 D .venv/lib/python3.9/site-packages/pip/_internal/utils/pkg_resources.py
 D .venv/lib/python3.9/site-packages/pip/_internal/utils/setuptools_build.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/subprocess.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/temp_dir.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/unpacking.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/urls.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/virtualenv.py
 M .venv/lib/python3.9/site-packages/pip/_internal/utils/wheel.py
 M .venv/lib/python3.9/site-packages/pip/_internal/vcs/bazaar.py
 M .venv/lib/python3.9/site-packages/pip/_internal/vcs/git.py
 M .venv/lib/python3.9/site-packages/pip/_internal/vcs/mercurial.py
 M .venv/lib/python3.9/site-packages/pip/_internal/vcs/subversion.py
 M .venv/lib/python3.9/site-packages/pip/_internal/vcs/versioncontrol.py
 M .venv/lib/python3.9/site-packages/pip/_internal/wheel_builder.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/appdirs.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/_cmd.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/adapter.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/cache.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/caches/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/caches/file_cache.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/caches/redis_cache.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/compat.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/controller.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/filewrapper.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/heuristics.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/serialize.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/wrapper.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/certifi/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/certifi/cacert.pem
 M .venv/lib/python3.9/site-packages/pip/_vendor/certifi/core.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/big5freq.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/big5prober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/chardistribution.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/charsetgroupprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/charsetprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/cli/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/cli/chardetect.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/codingstatemachine.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/compat.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/cp949prober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/enums.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/escprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/escsm.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/eucjpprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/euckrfreq.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/euckrprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/euctwfreq.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/euctwprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/gb2312freq.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/gb2312prober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/hebrewprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/jisfreq.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/jpcntx.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langbulgarianmodel.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langgreekmodel.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langhebrewmodel.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langhungarianmodel.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langrussianmodel.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langthaimodel.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langturkishmodel.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/latin1prober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/mbcharsetprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/mbcsgroupprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/mbcssm.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/metadata/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/metadata/languages.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/sbcharsetprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/sbcsgroupprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/sjisprober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/universaldetector.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/utf8prober.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/version.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/ansi.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/ansitowin32.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/initialise.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/win32.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/winterm.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/misc.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/shutil.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/sysconfig.cfg
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/sysconfig.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/tarfile.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/compat.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/database.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/index.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/locators.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/manifest.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/markers.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/metadata.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/scripts.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/t32.exe
 M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/t64.exe
 M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/util.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/version.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/w32.exe
 M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/w64.exe
 D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/wheel.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/distro.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_ihatexml.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_inputstream.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_tokenizer.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_trie/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_trie/_base.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_trie/py.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_utils.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/constants.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/alphabeticalattributes.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/base.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/inject_meta_charset.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/lint.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/optionaltags.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/sanitizer.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/whitespace.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/html5parser.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/serializer.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treeadapters/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treeadapters/genshi.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treeadapters/sax.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/base.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/dom.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/etree.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/etree_lxml.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/base.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/dom.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/etree.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/etree_lxml.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/genshi.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/idna/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/idna/codec.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/idna/compat.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/idna/core.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/idna/idnadata.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/idna/intranges.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/idna/package_data.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/idna/uts46data.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/msgpack/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/msgpack/_version.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/msgpack/ext.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/msgpack/fallback.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/packaging/__about__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/_manylinux.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/_musllinux.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/_structures.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/markers.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/requirements.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/specifiers.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/tags.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/utils.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/version.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/build.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/check.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/colorlog.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/compat.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/dirtools.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/envbuild.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/in_process/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/in_process/_in_process.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/meta.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/wrappers.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/pkg_resources/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pkg_resources/py31compat.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/progress/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/progress/bar.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/progress/counter.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/progress/spinner.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/pyparsing.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/__version__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/_internal_utils.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/adapters.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/api.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/auth.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/certs.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/compat.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/cookies.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/exceptions.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/help.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/hooks.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/models.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/packages.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/sessions.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/status_codes.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/structures.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/requests/utils.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/resolvelib/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/resolvelib/compat/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/resolvelib/compat/collections_abc.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/resolvelib/providers.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/resolvelib/reporters.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/resolvelib/resolvers.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/resolvelib/structs.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/six.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/_asyncio.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/_utils.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/after.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/before.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/before_sleep.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/nap.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/retry.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/stop.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/tornadoweb.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/tenacity/wait.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/tomli/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/tomli/_parser.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/tomli/_re.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/_collections.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/_version.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/connection.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/connectionpool.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/contrib/_securetransport/bindings.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/contrib/_securetransport/low_level.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/contrib/appengine.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/contrib/ntlmpool.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/contrib/pyopenssl.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/contrib/securetransport.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/packages/__init__.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/packages/six.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/packages/ssl_match_hostname/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/packages/ssl_match_hostname/_implementation.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/poolmanager.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/request.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/response.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/connection.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/proxy.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/request.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/retry.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/ssl_.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/ssltransport.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/timeout.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/url.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/urllib3/util/wait.py
 M .venv/lib/python3.9/site-packages/pip/_vendor/vendor.txt
 D .venv/lib/python3.9/site-packages/pip/_vendor/webencodings/__init__.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/webencodings/labels.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/webencodings/mklabels.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/webencodings/tests.py
 D .venv/lib/python3.9/site-packages/pip/_vendor/webencodings/x_user_defined.py
 M README.md
 D app_gpa/STRUCTURE.md
 M app_gpa/api/routers/agent.py
 M app_gpa/modules/agents/credentials.py
 M app_gpa/modules/agents/flow/contracts.py
 M app_gpa/modules/agents/flow/profile_handlers.py
 M app_gpa/modules/agents/gigachat_agent.py
 M app_gpa/modules/agents/governance/manifest.json
 M app_gpa/modules/agents/models/deepseek/__init__.py
 M app_gpa/modules/agents/models/deepseek/actions.py
 M app_gpa/modules/agents/models/deepseek/client.py
 M app_gpa/modules/agents/models/gigachat/client.py
 M app_gpa/modules/agents/models/groq/__init__.py
 M app_gpa/modules/agents/models/groq/actions.py
 M app_gpa/modules/agents/models/groq/client.py
 M app_gpa/modules/agents/models/openrouter/__init__.py
 M app_gpa/modules/agents/models/openrouter/actions.py
 M app_gpa/modules/agents/models/openrouter/client.py
 M app_gpa/modules/agents/orchestrator.py
 M app_gpa/modules/agents/providers/deepseek.py
 M app_gpa/modules/agents/providers/gigachat_provider.py
 M app_gpa/modules/agents/providers/groq_provider.py
 M app_gpa/modules/agents/providers/openrouter_provider.py
 M app_gpa/modules/agents/providers/registry.py
 M app_gpa/modules/agents/track.py
 M app_gpa/requirements.txt
 M app_gpa/services/agents/api.py
 M app_gpa/web/routes/pages.py
 M app_gpa/web/static/detailed.css
 M app_gpa/web/static/gpa-agent-setup.js
 M app_gpa/web/static/gpa-ui.js
 M app_gpa/web/static/ux.css
 M app_gpa/web/templates/analysis/detailed_input.html
 M app_gpa/web/templates/analysis/reset_cache_modal.html
 M app_gpa/web/templates/app/agent_context_modal.html
 M app_gpa/web/templates/app/app_footer.html
 M app_gpa/web/templates/app/apple_sidebar.html
 M app_gpa/web/templates/app/home.html
 M app_gpa/web/templates/app/result.html
 D pack_to_txt.py
 D pack_umpack.txt
 M scripts/dci-propagate.sh
 M scripts/dci-test.sh
 M scripts/dci-vector.sh
 M scripts/dci_vector_sync.py
 M scripts/rules-validate-all-projects.sh
 M todo.md
?? README_CUSTOM_RULES.md
?? app_gpa/config/groq_profiles.json
?? app_gpa/config/openrouter_profiles.json
?? app_gpa/web/templates/app/about.html
?? project_doc/
?? scripts/run-app.sh
?? tig_delta.md
?? tig_snapshot.md

=== LOG (12 oneline) ===
ffddf3c (HEAD -> add_ai_analize_opt) fix rules
60dd8c5 (origin/add_ai_analize_opt) add rules
1d33aa2 fast api refactoring
5180baa fast api refactoring
a6329d8 rem md
5b0107b ui + linter
4eb5b5f add agent func
7b7fb56 (master) update gitignore
f995ed4 Merge branch 'update-ui' into master
5999fb2 (origin/update-ui, update-ui) update gitignore
34753dc add files
ea8f099 add styles, add README, add LICENSE
```

## File index (compressed)

### Changed (vs base ref)
- `todo.md` (7350 bytes)
- `README.md` (46380 bytes)
- `README_CUSTOM_RULES.md` (3514 bytes)
- `app_gpa/requirements.txt` (1287 bytes)
- `app_gpa/config/openrouter_profiles.json` (177 bytes)
- `app_gpa/config/groq_profiles.json` (227 bytes)
- `app_gpa/web/static/detailed.css` (37265 bytes)
- `app_gpa/web/static/gpa-agent-setup.js` (13343 bytes)
- `app_gpa/web/static/ux.css` (15950 bytes)
- `app_gpa/web/static/gpa-ui.js` (12772 bytes)
- `app_gpa/web/templates/analysis/detailed_input.html` (199491 bytes)
- `app_gpa/web/templates/analysis/reset_cache_modal.html` (10919 bytes)
- `app_gpa/web/templates/app/agent_context_modal.html` (10200 bytes)
- `app_gpa/web/templates/app/home.html` (9642 bytes)
- `app_gpa/web/templates/app/about.html` (3184 bytes)
- `app_gpa/web/templates/app/apple_sidebar.html` (5708 bytes)
- `app_gpa/web/templates/app/app_footer.html` (4082 bytes)
- `app_gpa/web/templates/app/result.html` (4279 bytes)
- `app_gpa/web/routes/pages.py` (471 bytes)
- `app_gpa/api/routers/agent.py` (23528 bytes)
- `app_gpa/modules/agents/credentials.py` (7675 bytes)
- `app_gpa/modules/agents/track.py` (6111 bytes)
- `app_gpa/modules/agents/gigachat_agent.py` (91196 bytes)
- `app_gpa/modules/agents/orchestrator.py` (9090 bytes)
- `app_gpa/modules/agents/providers/registry.py` (977 bytes)
- `app_gpa/modules/agents/providers/openrouter_provider.py` (2839 bytes)
- `app_gpa/modules/agents/providers/deepseek.py` (2393 bytes)
- `app_gpa/modules/agents/providers/groq_provider.py` (2767 bytes)
- `app_gpa/modules/agents/providers/gigachat_provider.py` (3064 bytes)
- `app_gpa/modules/agents/models/openrouter/client.py` (7245 bytes)
- `app_gpa/modules/agents/models/openrouter/actions.py` (1112 bytes)
- `app_gpa/modules/agents/models/openrouter/__init__.py` (845 bytes)
- `app_gpa/modules/agents/models/groq/client.py` (5775 bytes)
- `app_gpa/modules/agents/models/groq/actions.py` (1076 bytes)
- `app_gpa/modules/agents/models/groq/__init__.py` (645 bytes)
- `app_gpa/modules/agents/models/deepseek/client.py` (5921 bytes)
- `app_gpa/modules/agents/models/deepseek/actions.py` (1190 bytes)
- `app_gpa/modules/agents/models/deepseek/__init__.py` (1207 bytes)
- `app_gpa/modules/agents/models/gigachat/client.py` (7878 bytes)
- `app_gpa/modules/agents/governance/manifest.json` (2460 bytes)
- `app_gpa/modules/agents/flow/contracts.py` (1853 bytes)
- `app_gpa/modules/agents/flow/profile_handlers.py` (4995 bytes)
- `app_gpa/services/agents/api.py` (9955 bytes)
- `scripts/run-app.sh` (559 bytes)
- `scripts/dci-vector.sh` (4915 bytes)
- `scripts/dci-propagate.sh` (11824 bytes)
- `scripts/dci-test.sh` (10769 bytes)
- `scripts/rules-validate-all-projects.sh` (7446 bytes)
- `scripts/dci_vector_sync.py` (90640 bytes)

### Notable files (largest / capped index)
- `gpa_project_struct.md` (1121732 bytes)

*+183 more files — see `tig_delta.md` git diff*
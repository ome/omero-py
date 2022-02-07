# 5.11.0 (February 2022)

## New features

-   Add implementation for `DatasetColumn`
    [#309](https://github.com/ome/omero-py/pull/309)
-   Add support for searching OMERO.tables by column which name is not a valid
    Python identifier [#309](https://github.com/ome/omero-py/pull/309)

## Bug fixes

-   Fix OMERO.table memory issue when using `table.read()` with large number of
    rows [#314](https://github.com/ome/omero-py/pull/314)
-   Deprecate `PropertyParser.black_list` in favor of
    `PropertyParser.is_excluded`
    [#313](https://github.com/ome/omero-py/pull/313)

# 5.10.3 (December 2021)

## Bug Fix

- Allow direct URL to be passed to `omero import --fetch-jars`
  [#303](https://github.com/ome/omero-py/pull/303)
- Exclude `omero.version` from output of `omero config parse` [#312](https://github.com/ome/omero-py/pull/312)

# 5.10.2 (December 2021)

## Bug Fix

- Decode script stdout/stderr before printing,
  thanks to [Jeremy Muhlich](https://github.com/jmuhlich)
  [#310](https://github.com/ome/omero-py/pull/310)
- Ensure we are using pyopenssl [#305](https://github.com/ome/omero-py/pull/305)

# 5.10.1 (October 2021)

## Bug Fix

- Fix UnbondLocalError in `omero tag list`,
  thanks to [Lucille Delisle](https://github.com/lldelisle)
  [#307](https://github.com/ome/omero-py/pull/307)

# 5.10.0 (September 2021)

## New feature

- omero.gateway: add new `getObjectsByMapAnnotations` API
  [#285](https://github.com/ome/omero-py/pull/285)
- CLI: Add support for downloading fileset and multi-file images [#298](https://github.com/ome/omero-py/pull/298)

The CLI feature also introduces a backwards-incompatible layout change for
the download of images to mitigate the risk of data corruption associated with
renaming files. The command now specifies a directory path under which all
files associated with the image are downloaded using the original file names
and structure.

## Bug Fix

- CLI: point users at [image.sc](https://forum.image.sc/) for reporting bugs
  [#297](https://github.com/ome/omero-py/pull/297)

# 5.9.3 (July 2021)

## Bug Fix

- Fix OMERO.tables to work with all column types
  [#288](https://github.com/ome/omero-py/pull/288)
- Fix race condition in OMERO.tables
  [#292](https://github.com/ome/omero-py/pull/292)
- Fix Python2-ism in omero.gateway findExperimenters method,
  thanks to [Alex Herbert](https://github.com/aherbert)
  [#293](https://github.com/ome/omero-py/pull/293)

# 5.9.2 (April 2021)

## New CLI option
- Add `--retry [RETRIES]` to `omero login`
  [#283](https://github.com/ome/omero-py/pull/283)

# 5.9.1 (March 2021)

## Bug Fix
- remove usage of deprecated method preventing usage on Python 3.9
  [#282](https://github.com/ome/omero-py/pull/282)
- CLI: obj update strips newlines [#279](https://github.com/ome/omero-py/pull/279)
- roi_utils: fix possible division by zero [#278](https://github.com/ome/omero-py/pull/278)


## Other updates
- download provider uses NamedTemporaryFile [#274](https://github.com/ome/omero-py/pull/274)

# 5.9.0 (January 2021)

- Admin: introduce `omero.server.nodedescriptors` configuration property
  for configuring services launched on start-up
  [#272](https://github.com/ome/omero-py/pull/272)

# 5.8.3 (October 2020)

## Bug fix

- CLI: fix `omero errors` command under Python 3
  [#264](https://github.com/ome/omero-py/pull/264)

# 5.8.2 (October 2020)

## Bug fix

- CLI: fail login when user input is required but stdout is not connected to
  a tty(-like) device [#256](https://github.com/ome/omero-py/pull/256)

## Other updates

- Import test: check stderr for output [#260](https://github.com/ome/omero-py/pull/260)
- Switch from Travis CI to GitHub actions ([#261](https://github.com/ome/omero-py/pull/261), [#262](https://github.com/ome/omero-py/pull/262))

# 5.8.1 (September 2020)

## Bug fixes

- CLI: improve description of `--include` and `--exclude` options ([#252](https://github.com/ome/omero-py/pull/252), [#254](https://github.com/ome/omero-py/pull/254))
- Restore Python 3.5 compatibility ([#257](https://github.com/ome/omero-py/pull/257))


# 5.8.0 (September 2020)

## New features
- `omero import` automatically downloads import jars if missing ([#162](https://github.com/ome/omero-py/pull/162))
- Use OS-specific application directories instead of `~/omero` for local cache ([#242](https://github.com/ome/omero-py/pull/242))
- `omero admin`: optionally check for system manager environment variable ([#246](https://github.com/ome/omero-py/pull/246))
- Add support for multiple Ice TLS protocols ([#251](https://github.com/ome/omero-py/pull/251))

## Bug fixes
- CLI UTF-8 Fixes ([#224](https://github.com/ome/omero-py/pull/224))
- Fix sessions logging attribute error ([#226](https://github.com/ome/omero-py/pull/226))
- `omero hql`: when querying masks, filter `bytes` field ([#230](https://github.com/ome/omero-py/pull/230))
- Fix CLI error handling when attempting to check log files ([#236](https://github.com/ome/omero-py/pull/236))
- `omero import`: fix `--logprefix` ([#238](https://github.com/ome/omero-py/pull/238))
- `fs usage`: don't overwrite size ([#245](https://github.com/ome/omero-py/pull/245))
- `omero.gateway`: always marshal tile metadata on presence of pyramid ([#239](https://github.com/ome/omero-py/pull/239))

## Other updates
- Add PyYAML as a dependency of omero-py ([#228](https://github.com/ome/omero-py/pull/228))
- `bin/omero` entrypoint ([#229](https://github.com/ome/omero-py/pull/229))
- Tox: Python 3.8, use travis bionic ice-py wheels ([#232](https://github.com/ome/omero-py/pull/232))
- Update release paragraph to mention downstream conda repository ([#234](https://github.com/ome/omero-py/pull/234))
- Remove long-deprecated module `functional.py` ([#237](https://github.com/ome/omero-py/pull/237))
- Use requests for HTTP/HTTPS calls in library ([#240](https://github.com/ome/omero-py/pull/240))
- Adds optional extra args to the `util/import_candidates.py`, thanks to [Guillaume Gay](https://github.com/glyg)  ([#241](https://github.com/ome/omero-py/pull/241))
- Link to source on PyPI homepage ([#247](https://github.com/ome/omero-py/pull/247))
- Deprecate CLI duplicate plugin in favor of [omero-cli-duplicate](https://pypi.org/project/omero-cli-duplicate) ([#249](https://github.com/ome/omero-py/pull/249))


# 5.7.1 (June 2020)

- Fix `import --log/--err` with bulk import ([#223](https://github.com/ome/omero-py/pull/223))

# 5.7.0 (June 2020)

- API changes:
  - Support use of CLI within OMERO.scripts ([#186](https://github.com/ome/omero-py/pull/186))
  - Add new conn.chownObjects() method ([#195](https://github.com/ome/omero-py/pull/195))
  - Loading options for Experimenters and Groups ([#196](https://github.com/ome/omero-py/pull/196))

- Other fixes and updates:
  - Fix pywin import in Python 3.7 ([#203](https://github.com/ome/omero-py/pull/203))
  - Don't unset ICE_CONFIG on Windows ([#193](https://github.com/ome/omero-py/pull/193))
  - Ignore owner in omero.data.dir check ([#208](https://github.com/ome/omero-py/pull/208))
  - Fix JSON parsing on Python 3.5 ([#213](https://github.com/ome/omero-py/pull/213))
  - Fix client.download() on Python 3.5 ([#215](https://github.com/ome/omero-py/pull/215))
  - Warn if omero.db.poolsize is not set ([#218](https://github.com/ome/omero-py/pull/218))
  - admin diagnostics shows jar versions ([#188](https://github.com/ome/omero-py/pull/188))

# 5.6.2 (March 2020)

- Doc: escape quotes in "Default:" sections ([#185](https://github.com/ome/omero-py/pull/185))
- Doc: List preferred conda installation first ([#190](https://github.com/ome/omero-py/pull/190))
- Fix: pass OMERODIR to processor ([#197](https://github.com/ome/omero-py/pull/197))
- Fix: Improve error message for 'fs usage' ([#192](https://github.com/ome/omero-py/pull/192))
- Fix: Get file size for download ([#181](https://github.com/ome/omero-py/pull/181))

# 5.6.1 (February 2020)

- travis jobs: enable Windows ([#134](https://github.com/ome/omero-py/pull/134))
- `CmdError`: implement `__str__` ([#151](https://github.com/ome/omero-py/pull/151))
- tables: call delete callback ([#152](https://github.com/ome/omero-py/pull/152))
- fix doc ([#170](https://github.com/ome/omero-py/pull/170))
- Add show-uuid option to `sessions who` ([#174](https://github.com/ome/omero-py/pull/174))
- `omero db password` should be a string ([#175](https://github.com/ome/omero-py/pull/175))
- Extend output of `omero version` ([#176](https://github.com/ome/omero-py/pull/176))
- Improve PyYAML error message ([#177](https://github.com/ome/omero-py/pull/177))

# 5.6.0 (January 2020)

- Remove `bin/omero` and `lib/python` ([#157](https://github.com/ome/omero-py/pull/157))
- Bump Blitz version 5.5.5 ([#158](https://github.com/ome/omero-py/pull/158))
- Processor passes locale to subprocess ([#150](https://github.com/ome/omero-py/pull/150))
- `omero.client` ensures args is not None ([#149](https://github.com/ome/omero-py/pull/149))
- Ignore `OMERO_HOME` with warning ([#148](https://github.com/ome/omero-py/pull/148))
- Retry flaky tests up to five times ([#144](https://github.com/ome/omero-py/pull/144))
- Disable new `testLoadGlob` when `OMERODIR` not set ([#140](https://github.com/ome/omero-py/pull/140))
- Add numpy to requirements ([#139](https://github.com/ome/omero-py/pull/139))
- `admin.py`: handle errors in `getdirsize` ([#135](https://github.com/ome/omero-py/pull/135))
- Fix tables `StringColumn` for strings containing Unicode characters ([#143](https://github.com/ome/omero-py/pull/143))
- Add `bin/omero load --glob` support ([#137](https://github.com/ome/omero-py/pull/137))
- Drop `hdfstorageV1` ([#136](https://github.com/ome/omero-py/pull/136))
- Require `OMERODIR` to be set ([#14](https://github.com/ome/omero-py/pull/14))
- Fix Windows build ([#132](https://github.com/ome/omero-py/pull/132))
- Fix `config parse` command ([#130](https://github.com/ome/omero-py/pull/130))
- Rename deprecated plugins ([#124](https://github.com/ome/omero-py/pull/124))
- Activate all unit tests ([#122](https://github.com/ome/omero-py/pull/122))
- Fix batch file annotation ([#127](https://github.com/ome/omero-py/pull/127))
- Declare Pillow as a mandatory dependency of omero-py ([#128](https://github.com/ome/omero-py/pull/128))
- Move external path module under `omero_ext` namespace ([#123](https://github.com/ome/omero-py/pull/123))
- Fix pyinotify for DropBox ([#119](https://github.com/ome/omero-py/pull/119))
- Fix DB creation script ([#110](https://github.com/ome/omero-py/pull/110))
- Fix `tables` and `getObjects`
- Fixes primarily focused on byte return types
- Activate Python 3.5 testing ([#68](https://github.com/ome/omero-py/pull/68))
- Add `devtarget` for developer friendliness ([#33](https://github.com/ome/omero-py/pull/33), [#55](https://github.com/ome/omero-py/pull/55))
- Remove more web vestiges ([#26](https://github.com/ome/omero-py/pull/26))

## API Changes

- `omero.gateway.FileAnnotationWrapper.getFileInChunks` returns bytes
- `omero.gateway.ImageWrapper.exportOmeTiff` returns bytes
- `omero.gateway.BlitzGateawy.createOriginalFileFromFileObj` takes `BytesIO`
- several return values should now be wrapped by `BytesIO`:
  - `image.renderSplitChannel()`
  - `image.renderBirdsEyeView()`
  - `image.renderJpegRegion()`
  - `image.renderJpeg()`
- `rlong` instances now require explicit mapping:
  - `omero_type(longValue)` defaults to `rint`
  - `omero.rtypes.wrap(longValue)` defaults to `rint`

# 5.5.1 (September 2019)

- Use omero-blitz 5.5.4 ([#24](https://github.com/ome/omero-py/pull/24))
- Fix unit tests ([#10](https://github.com/ome/omero-py/pull/10), [#17](https://github.com/ome/omero-py/pull/17))
- Improve PyPI deployment, add README, etc. ([#6](https://github.com/ome/omero-py/pull/6))
- Remove `web.py` ([#5](https://github.com/ome/omero-py/pull/5))
- Extract code from `ome/openmicroscopy`
- Make minimal changes for a functioning `python setup.py` ([#1](https://github.com/ome/omero-py/pull/1))

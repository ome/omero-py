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

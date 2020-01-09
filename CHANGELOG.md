# 5.6.0 (January 2020)

- Bump Blitz version 5.5.5 (#158)
- Processor passes locale to subprocess (#150)
- omero.client ensures args is not None (#149)
- Ignore OMERO_HOME with warning (#148)
- Retry flaky tests up to five times (#144)
- Disable new testLoadGlob when OMERODIR not set (#140)
- Add numpy to requirements (#139)
- admin.py: handle errors in getdirsize (#135)
- Fix tables StringColumn for strings containing Unicode characters (#143)
- Add `bin/omero load --glob` support (#137)
- Drop hdfstorageV1 (#136)
- Require OMERODIR to be set (#14)
- Fix Windows build (#132)
- Fix 'config parse' command (#130)
- Rename deprecated plugins (#124)
- Activate all unit tests (#122)
- Fix batch file annotation (#127)
- Declare Pillow as a mandatory dependency of omero-py (#128)
- Move external path module under `omero_ext` namespace (#123)
- Fix pyinotify for DropBox (#119)
- Fix DB creation script (#110)
- Fix tables and getObjects
- Fixes primarily focused on byte return types
- Activate Python 3.5 testing (#68)
- Add `devtarget` for developer friendliness (#33, #55)
- Remove more web vestiges (#26)

## API Changes

- omero.gateway.FileAnnotationWrapper.getFileInChunks returns bytes
- omero.gateway.ImageWrapper.exportOmeTiff returns bytes
- omero.gateway.BlitzGateawy.createOriginalFileFromFileObj takes BytesIO
- several return values should now be _wrapped_ by BytesIO:
  - image.renderSplitChannel()
  - image.renderBirdsEyeView()
  - image.renderJpegRegion()
  - image.renderJpeg()
- `rlong` instances now require explicit mapping:
  - `omero_type(longValue)` defaults to `rint`
  - `omero.rtypes.wrap(longValue)` defaults to `rint`

# 5.5.1 (September 2019)

- Use omero-blitz 5.5.4 (#24)
- Fix unit tests (#10, #17)
- Improve PyPI deployment, add README, etc. (#6)
- Remove web.py (#5)
- Extract code from ome/openmicroscopy
- Make minimal changes for a functioning `python setup.py` (#1)

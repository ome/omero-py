# 5.6.dev9 (December 2019)

- Fix tables StringColumn for strings containing Unicode characters (#133)

# 5.6.dev8 (December 2019)

- Add `bin/omero load --glob` support (#137)
- Drop hdfstorageV1 (#136)
- Require OMERODIR to be set (#14)

# 5.6.dev7 (November 2019)

- Fix Windows build (#132)
- Fix 'config parse' command (#130)
- Rename deprecated plugins (#124)
- Activate all unit tests (#122)

# 5.6.dev6 (November 2019)

- Fix batch file annotation (#127)

## Packaging Changes

- Declare Pillow as a mandatory dependency of omero-py (#128)
- Move external path module under `omero_ext` namespace (#123)

# 5.6.dev5 (November 2019)

- Fix pyinotify for DropBox (#119)

# 5.6.dev4 (November 2019)

- Fix DB creation script (#110)
- Fix tables and getObjects

# 5.6.dev3 (November 2019)

- Fixes primarily focused on byte return types

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

# 5.6.dev2 (October 2019)

- Even more Python 3 fixes
- Activate Python 3.5 testing (#68)

# 5.6.dev1 (October 2019)

- Numerous Python3 fixes
- Add `devtarget` for developer friendliness (#33, #55
- Remove more web vestiges (#26)

# 5.5.1 (September 2019)

- Use omero-blitz 5.5.4 (#24)
- Fix unit tests (#10, #17)

# 5.5.dev2 (August 2019)

- Improve PyPI deployment, add README, etc. (#6)
- Remove web.py (#5)

# 5.5.dev1 (August 2019)

- Extract code from ome/openmicroscopy
- Make minimal changes for a functioning `python setup.py` (#1)

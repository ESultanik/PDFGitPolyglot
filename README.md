# This Git Repository is a PDF

This repository contains the L<sup><big>A</big></sup>T<sub><big>E</big></sub>X source of the PDF, as well as all of the scripts necessary to rebuild the [polyglot](https://en.wikipedia.org/wiki/Polyglot_(computing)).

### Building the Polyglot

If you cloned this repository directly from the PDF,

```
$ git clone PDFGitPolyglot.pdf PDFGitPolyglot
Cloning into 'PDFGitPolyglot'...
Receiving objects: 100% (174/174), 103.48 KiB | 0 bytes/s, done.
Resolving deltas: 100% (100/100), done.
```
then you will need to do some cleanup before running `make`:
```
git checkout master && git branch -d PolyglotBranch
```
After that, or if you cloned the repo from elsewhere (*e.g.*, [GitHub](https://github.com/ESultanik/PDFGitPolyglot)), then you will be able to run `make`, which will automatically build `PDFGitPolyglot.pdf` from the document contained in `article.tex`.

The first time you run `make`, the sources to [a patched version of Git](https://github.com/ESultanik/git/tree/UncompressedPack) will be downloaded and compiled. This can be time consuming, so I suggest you use `make -j8`, or whatever is appropriate for your system.

### Dependencies

* a relatively full install of a T<sub><big>E</big></sub>X distro, such as [TeX Live](https://www.tug.org/texlive/)
* autoconf and a C99 compiler for compiling git; I've found that git likes clang more than gcc
* all of git's sourcecode dependencies (openssl, curl, gettext, *&c.*)
* Python 2.7
* bash
* ImageMagick
* qpdf, used by the `verify_xrefs.py` script for sanity checking; this dependency can be removed by commenting out the call to `verify_xrefs.py` in the `Makefile`

### Caveats

The polyglot will fail to build if your document has any PDF objects (*e.g.*, images) that are larger than `0xFFFF` bytes. Read the article for more details.

### License

Copyright © 2017 [Evan A. Sultanik](https://www.sultanik.com/)

Permission is hereby granted, free of charge, to any person obtaining a copy of this document and associated source files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice, this permission notice, and the entire contents and history of its associated git repository shall be included in all copies or substantial portions of the Software.

The Software is provided “as is”, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement. In no event shall the authors or copyright holders be liable for any claim, damages or liability, whether in an action of contract, tort or otherwise, arising from, out of or in connection with the Software or the use or other dealings in the software.
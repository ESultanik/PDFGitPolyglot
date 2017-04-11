ifeq ($(shell uname), Darwin)
CC=clang
CXX=clang++
AR=ar
endif

.PHONY : all
all : article_bundle.pdf

.PHONY : clean
clean : git-submodule
	$(MAKE) -C git clean
	rm article_bundle.pdf article.pdf article.log article.aux *~

.PHONY : git-submodule
git-submodule :
	git submodule init
	git submodule update --recursive

git/configure : git-submodule
	$(MAKE) -C git configure
	cd git && ./configure

.PHONY : build-git
build-git : git/configure
	$(MAKE) CC=$(CC) CXX=$(CXX) AR=$(AR) -C git

article.pdf : article.tex
	pdflatex $<
	pdflatex $<
	test `wc -c <$@` -lt 65536 # The resulting PDF must be smaller than a DEFLATE block (0xFFFF bytes)!

article_bundle.pdf : article.pdf build-git
	CURRENT_BRANCH=`git rev-parse --abbrev-ref HEAD`
	git checkout -b PolyglotBranch
	PDF_HASH=`git hash-object -w $@`
	git checkout $(CURRENT_BRANCH)
	git branch -D PolyglotBranch

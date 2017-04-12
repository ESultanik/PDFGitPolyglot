ifeq ($(shell uname), Darwin)
CC=clang
CXX=clang++
AR=ar
endif

CURRENT_BRANCH=$(shell git rev-parse --abbrev-ref HEAD)

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

git/configure : | git-submodule
	$(MAKE) -C git configure
	cd git && ./configure

git/git : | git/configure
	$(MAKE) CC=$(CC) CXX=$(CXX) AR=$(AR) -C git

article.pdf : article.tex
	pdflatex $<
	pdflatex $<
	test `wc -c <$@` -lt 65536 # The resulting PDF must be smaller than a DEFLATE block (0xFFFF bytes)!
	@echo "$@ successfully created"

article_bundle.pdf : article.pdf git/git
	cp article.pdf $@
	git stash save MAKINGPOLYGLOT
	git stash list | grep -q MAKINGPOLYGLOT ; $(eval HAS_STASH=$$?)
	echo "HAS STASH: $(HAS_STASH)"
	git checkout -b PolyglotBranch
	git update-index --add --cacheinfo 100644 `git hash-object -w $@` $@
	$(eval TREE_HASH=$(shell git write-tree))
	echo 'Polyglot PDF' | git commit-tree $(TREE_HASH)
	git commit -a -m 'Creating the Polyglot'
	PATH=$(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))/git:$(PATH) git bundle create article.bundle --do-not-compress `git hash-object $@` --all
	git checkout $(CURRENT_BRANCH)
	git branch -D PolyglotBranch
	mv article.bundle $@
